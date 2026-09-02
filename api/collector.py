#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""collector.py - USDT 冻结检测站点埋点采集核心（纯 stdlib，无第三方依赖）。

设计约束（对应这个产品的命门）：
  1) 不落任何可识别用户的信息：IP/UA 只进当日 HMAC 桶，查询地址只存 8 位指纹。
  2) 事件白名单 + 字段强校验；错误响应不回显用户提交的原文。
  3) 单一 JSONL 事件文件为准，统计靠扫描（日活万级以内不需要数据库）。

被 router_fastapi.py（线上）与 test_flask_app.py（本地验证）共同复用。
"""
import hashlib
import hmac
import json
import math
import os
import re
import threading
import time
from collections import Counter, defaultdict

EVENTS = (
    "page_view", "page_leave", "query_start", "query_done", "query_error",
    "tip_copy", "share_click", "lang_switch", "report_expand",
)
LANGS = ("zh", "vi", "en")
ADDR_RE = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")
INVALID_ADDR = "invalid-format"
UA_MAX = 200
REF_MAX = 120


def level_from_score(score, frozen=None):
    """与前端 verdict 阈值一致：>=60 高危，>=30 中危，其余低危；冻结状态优先于评分。"""
    if frozen:
        return "frozen"
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "unknown"
    if s >= 60:
        return "high"
    if s >= 30:
        return "medium"
    if s >= 0:
        return "low"
    return "unknown"


def addr_fp(addr):
    """地址指纹：sha256 前 8 位，不可反推原文；格式非法返回固定占位值。"""
    if not addr or not isinstance(addr, str):
        return None
    a = addr.strip()
    if not ADDR_RE.match(a):
        return INVALID_ADDR
    return hashlib.sha256(("addr:" + a).encode("utf-8")).hexdigest()[:8]


def uv_bucket(ip, ua, secret, day=None):
    """按天轮换的匿名访客 id：同 IP+UA 当天恒定，跨天变化，不可反查。"""
    if day is None:
        day = time.strftime("%Y%m%d", time.gmtime())
    msg = "%s|%s|%s" % (day, ip or "?", (ua or "")[:UA_MAX])
    return hmac.new(secret, msg.encode("utf-8"), hashlib.sha256).hexdigest()[:10], day


def percentile_summary(vals):
    if not vals:
        return {"n": 0, "p50": None, "p90": None, "max": None}
    s = sorted(vals)

    def pct(p):
        return s[min(len(s) - 1, int(math.ceil(p / 100.0 * len(s)) - 1))]
    return {"n": len(s), "p50": pct(50), "p90": pct(90), "max": s[-1]}


class Collector(object):
    def __init__(self, data_dir, secret, trust_proxy=True, rate_limit_per_min=60, now=None):
        self.data_dir = data_dir
        self.secret = secret if isinstance(secret, bytes) else str(secret).encode("utf-8")
        self.trust_proxy = trust_proxy
        self.rate = rate_limit_per_min
        self._now = now or time.time
        self._lock = threading.Lock()
        self._hits = defaultdict(list)
        os.makedirs(data_dir, exist_ok=True)

    # ---------- 入站 ----------
    def client_ip(self, headers, peer):
        if self.trust_proxy:
            xff = headers.get("X-Forwarded-For") or headers.get("X-Real-IP")
            if xff:
                return xff.split(",")[0].strip()[:64]
        return (peer or "")[:64]

    def normalize(self, raw, headers=None, peer=""):
        """任意输入 -> 一条安全事件；返回 (event 或 None, 错误码 或 None)。"""
        headers = headers or {}
        if isinstance(raw, (bytes, bytearray)):
            try:
                raw = raw.decode("utf-8", "replace")
            except Exception:
                return None, "bad-bytes"
        if isinstance(raw, str):
            if len(raw) > 4096:
                return None, "too-large"
            if raw.strip() == "":
                return None, "empty"
            try:
                obj = json.loads(raw)
            except ValueError:
                return None, "bad-json"
        else:
            obj = raw
        if not isinstance(obj, dict):
            return None, "not-object"
        ev = str(obj.get("ev", ""))[:24]
        if ev not in EVENTS:
            # 固定错误码，绝不把用户提交的内容写进响应
            return None, "unknown-event"
        ts = self._now()
        e = {
            "ts": int(ts),
            "day": time.strftime("%Y-%m-%d", time.gmtime(ts)),
            "ev": ev,
            "path": str(obj.get("path", ""))[:80],
        }
        lang = str(obj.get("lang", ""))[:2]
        e["lang"] = lang if lang in LANGS else "zh"
        uv, _ = uv_bucket(self.client_ip(headers, peer), headers.get("User-Agent", ""), self.secret)
        e["uv"] = uv
        ua = str(headers.get("User-Agent", ""))[:UA_MAX]
        e["device"] = "mobile" if re.search(r"android|iphone|ipad|mobile", ua, re.I) else ("desktop" if ua else "unknown")
        ref = str(headers.get("Referer", ""))[:REF_MAX]
        e["ref"] = (re.sub(r"^https?://", "", ref).split("/")[0][:80] or "-")
        score = obj.get("score")
        if score is not None:
            try:
                e["score"] = max(0.0, min(100.0, float(score)))
            except (TypeError, ValueError):
                e["score"] = None
        if e.get("score") is not None:
            e["level"] = level_from_score(e["score"], obj.get("frozen"))
        elif obj.get("frozen") is True:
            e["level"] = "frozen"
        dw = obj.get("dwell_ms")
        if dw is not None:
            try:
                e["dwell_ms"] = int(max(0, min(3600000, float(dw))))
            except (TypeError, ValueError):
                pass
        dur = obj.get("dur_ms")
        if dur is not None:
            try:
                e["dur_ms"] = int(max(0, min(120000, float(dur))))
            except (TypeError, ValueError):
                pass
        st = obj.get("status")
        if st is not None:
            try:
                e["status"] = int(st)
            except (TypeError, ValueError):
                pass
        if obj.get("addr"):
            fp = addr_fp(obj.get("addr"))
            if fp:
                e["addr_fp"] = fp
        return e, None

    def allow(self, uv):
        """匿名访客级每分钟限流，防止事件文件被刷。"""
        with self._lock:
            now = self._now()
            keep = [t for t in self._hits[uv] if now - t < 60]
            if len(keep) >= self.rate:
                self._hits[uv] = keep
                return False
            keep.append(now)
            self._hits[uv] = keep
            return True

    def write(self, event):
        p = os.path.join(self.data_dir, "events-%s.jsonl" % event["day"])
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock:
            with open(p, "a", encoding="utf-8") as f:
                f.write(line)
        return p

    # ---------- 统计 ----------
    def files(self, days=7):
        today = time.time()
        out = []
        for i in range(days):
            d = time.strftime("%Y-%m-%d", time.gmtime(today - i * 86400))
            p = os.path.join(self.data_dir, "events-%s.jsonl" % d)
            if os.path.exists(p):
                out.append(p)
        return sorted(out)

    def stats(self, days=7):
        days = max(1, min(90, int(days)))
        """口径写死在这里：漏斗=page_view→query_start→query_done；
        风险分布/来源/设备只按各自锚点事件计，避免重复计数。"""
        evs = Counter()
        uv_by_day = defaultdict(set)
        levels = Counter()
        langs = Counter()
        devices = Counter()
        refs = Counter()
        tips = Counter()
        dur = []
        dwell = []
        addr_done = Counter()
        started = done = errors = 0
        for p in self.files(days):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    name = e.get("ev")
                    evs[name] += 1
                    uv_by_day[e.get("day", "?")].add(e.get("uv"))
                    if name == "query_start":
                        started += 1
                    elif name == "query_done":
                        done += 1
                        if e.get("level"):
                            levels[e["level"]] += 1
                        if e.get("dur_ms") is not None:
                            dur.append(e["dur_ms"])
                        fp = e.get("addr_fp")
                        if fp and fp != INVALID_ADDR:
                            addr_done[fp] += 1
                    elif name == "query_error":
                        errors += 1
                    elif name == "page_leave":
                        if e.get("dwell_ms") is not None:
                            dwell.append(int(e["dwell_ms"]))
                    elif name == "page_view":
                        langs[e.get("lang", "zh")] += 1
                        devices[e.get("device", "unknown")] += 1
                        if e.get("ref", "-") != "-":
                            refs[e["ref"]] += 1
                    elif name in ("tip_copy", "share_click"):
                        tips[name] += 1
        return {
            "window_days": days,
            "events": dict(evs),
            "funnel": {"page_view": evs.get("page_view", 0), "query_start": started,
                       "query_done": done, "query_error": errors,
                       "tip_copy": tips.get("tip_copy", 0), "share_click": tips.get("share_click", 0)},
            "queries_started": started,
            "queries_done": done,
            "queries_failed": errors,
            "success_rate": round(done / started, 4) if started else None,
            "conversion_done_over_view": round(done / evs.get("page_view", 0), 4) if evs.get("page_view") else None,
            "unique_visitors_total": len(set().union(*uv_by_day.values())) if uv_by_day else 0,
            "uv_by_day": {k: len(v) for k, v in sorted(uv_by_day.items())},
            "risk_levels": dict(levels),
            "langs": dict(langs),
            "devices": dict(devices),
            "top_refs": refs.most_common(10),
            "unique_addresses": len(addr_done),
            "repeat_checks": sum(1 for v in addr_done.values() if v >= 2),
            "dur_ms": percentile_summary(dur),
            "dwell_ms": percentile_summary(dwell),
        }
