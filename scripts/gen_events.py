#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_events.py — 生成测试事件（对齐 collect.js 上报 schema，POST /api/collect text/plain）。

事件白名单（collector.py EVENTS，与线上一致）:
  page_view / page_leave / query_start / query_done / query_error /
  tip_copy / share_click / lang_switch / report_expand

用法:
  python3 gen_events.py -n 20 [--api-url http://localhost:8902/api/collect]
只发合法事件；地址用真实已验案例（数据铁律：测试数据也不编造地址）。
"""
import argparse
import json
import random
import sys
import time
import urllib.request

API_URL = "http://localhost:8902/api/collect"

# 真实已验地址（usdt-freeze-forensics 活库）
SAMPLE_ADDRESSES = [
    "TJeh5fXJttbypanF2FMzgu42yqXnc5BuWw",
    "TGC1t9MbJhx7uKYiQG4SzoafeFz3Jzg1JN",
    "TChHAZ5QN6MdwRc61TqjFziWtgrY888888",
    "TUZPztRsZQMUJVXQYKwEuwdGhzgTGjieuu",
    "TTu3mqHaUcqcEaX14s2t8VRzCkJkVMs3L",
]
PATHS = ["/usdt-check/report.html", "/usdt-check/index.html", "/usdt-check/deep.html"]
LANGS = ["zh", "vi", "en"]


def gen_event():
    """随机生成一条合法埋点事件（collect.js 格式：{ev,path,lang,...}）"""
    ev = random.choice(("page_view", "page_leave", "query_start", "query_done",
                       "query_error", "tip_copy", "share_click", "lang_switch", "report_expand"))
    e = {"ev": ev, "path": random.choice(PATHS), "lang": random.choice(LANGS)}
    if ev == "page_leave":
        e["dwell_ms"] = random.randint(3000, 300000)
    elif ev == "query_start":
        pass
    elif ev == "query_done":
        score = random.randint(5, 100)
        frozen = random.random() < 0.2
        e["score"] = score
        e["frozen"] = frozen
        e["dur_ms"] = random.randint(200, 8000)
        e["addr"] = random.choice(SAMPLE_ADDRESSES)
    elif ev == "query_error":
        e["status"] = random.choice((400, 429, 500))
        e["dur_ms"] = random.randint(100, 3000)
    elif ev == "lang_switch":
        e["to"] = random.choice(LANGS)
    return e


def send_event(event, api_url):
    """POST text/plain（与 collect.js sendBeacon Blob 同格式）"""
    body = json.dumps(event, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(api_url, data=body, method="POST",
                                 headers={"Content-Type": "text/plain", "User-Agent": "gen_events/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode()[:120]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:120]
    except Exception as e:
        return 0, str(e)[:120]


def main():
    ap = argparse.ArgumentParser(description="Generate test analytics events")
    ap.add_argument("-n", "--count", type=int, default=10)
    ap.add_argument("--api-url", default=API_URL)
    args = ap.parse_args()

    ok = fail = 0
    print(f"生成 {args.count} 条事件 → {args.api_url}")
    for i in range(args.count):
        ev = gen_event()
        code, resp = send_event(ev, args.api_url)
        tag = "OK" if code == 200 else "FAIL"
        if code == 200:
            ok += 1
        else:
            fail += 1
        print(f"  [{i+1}] {tag} {code} ev={ev['ev']} -> {resp[:80]}")
    print(f"\n完成: {ok} 成功 / {fail} 失败")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
