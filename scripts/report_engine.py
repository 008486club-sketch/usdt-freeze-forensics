#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report_engine.py — USDT Freeze Forensics Report Engine（深度取证报告引擎）
2026-09-06 GPT 建议升级：把"CSV 统计摘要"升级为"USDT 冻结与资金流取证分析报告"。

设计：
  分析阶段 produce 结构化 report dict（subject/freeze/flow/funding/destinations/adjacent/anomaly/
  risk/causes/evidence/limitations）→ 渲染阶段 render_markdown() 按数据动态出章节。
  未来 Web/PDF 可复用同一 dict（GPT 建议的 Report JSON 数据层雏形）。

合规铁律（SKILL v2.4）：
  - 证据分级：A 链上事实（合约状态/事件/交易记录）/ B 数据推导（统计模式）/ C 风险推断（行为解释）
  - symbol=BL 是 TRC-10 垃圾币，不是 Tether 冻结标记（铁律 #2）
  - 时间邻近 ≠ 冻结因果（铁律 #8）：只能"资金路径特征"，不能说"犯罪资金"
  - 资源委托等行为：只描述特征 + C 级推断，不武断"职业 OTC 定论"
  - 动态模块：无数据不出章节，不硬凑页数

用法（供 api_server._analyze_csv_bytes 调用）：
  from report_engine import analyze_csv_bytes, render_markdown
  rep = analyze_csv_bytes(rows, fmt, target_addr, chain=chain)
  md = render_markdown(rep)
"""
import os
from collections import defaultdict
from datetime import datetime, timezone

USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


def _esc(s):
    """Markdown 转义（表格内 | 与换行）"""
    return str(s or "").replace("|", "\\|").replace("\n", " ")


def _fmt_amt(v, d=2):
    if v is None:
        return "-"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(v) >= 1:
        return "{:,.{p}f}".format(v, p=d)
    return "{:.6f}".format(v)


def _addr_short(a, n=6, m=4):
    a = str(a or "")
    if len(a) <= n + m + 3:
        return a or "-"
    return a[:n] + "..." + a[-m:]


def _tx_short(tx):
    tx = str(tx or "")
    if len(tx) <= 20:
        return tx or "-"
    return tx[:12] + "..." + tx[-8:]


def _rank(items, key, top=10):
    """items: iterable of (name, dict)；key: dict 字段。返回排序后列表[(name, dict)]"""
    return sorted(items, key=lambda x: x[1].get(key, 0), reverse=True)[:top]


def analyze(rows, fmt, target_addr, chain=None):
    """主分析：rows 为 csv.DictReader 已读行（含 _value），fmt=token_transfer|transaction。
    chain: dict 链上事实（is_blacklisted True/False/None、freeze_time/freeze_tx/db_updated/
           created/balance、cp_status {addr_lower: True|False|None}）
    返回结构化 report dict。"""
    chain = chain or {}
    tgt = (target_addr or "").lower()
    rep = {
        "meta": {"fmt": fmt, "target": target_addr or "", "target_l": tgt, "rows_n": len(rows),
                 "gen_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")},
        "chain": chain,
        "freeze": {"blacklisted": chain.get("is_blacklisted"), "time": chain.get("freeze_time", ""),
                   "tx": chain.get("freeze_tx", ""), "db_updated": chain.get("db_updated", ""),
                   "source": "USDT 合约 isBlackListed / AddedBlackList 事件索引"},
        "flow": {"usdt": [], "trx": [], "usdt_in": 0.0, "usdt_out": 0.0, "usdt_n": 0,
                 "trx_in": 0.0, "trx_out": 0.0, "trx_n": 0, "biggest_in": None, "biggest_out": None},
        "funding": [], "dest": [], "cp_freeze": {},
        "adjacent": [], "rapid": [],
        "anomaly": [], "dlg": {"delegate": 0, "undelegate": 0},
        "risk": {"official": 0, "behavior": 0, "relation": 0, "other": 0, "total": 10},
        "causes": [], "evidence": [], "trc10": [], "scam": [], "limitations": [],
    }
    now_ts = datetime.now(timezone.utc).timestamp() * 1000

    # ---- 资金流原始行 ----
    for r in rows:
        sym = r.get("symbol", "")
        val = r.get("_value", 0.0) or 0.0
        frm = r.get("from", "")
        to = r.get("to", "")
        ct = r.get("contractType", "")
        ts = r.get("blockTime(UTC)", "")
        # 统一毫秒（token CSV 有 blockTs? transaction CSV 无毫秒——用字符串近似排序即可）
        if fmt == "token_transfer":
            if sym == "USDT" and r.get("tokenAddress", "").strip() == USDT_CONTRACT:
                rec = {"time": ts, "from": frm, "to": to, "val": float(val), "hash": r.get("Tx Hash", "") or r.get("transaction_id", "")}
                rep["flow"]["usdt"].append(rec)
        else:
            if ct == "TransferContract":  # TRX 转账
                rec = {"time": ts, "from": frm, "to": to, "val": float(val), "hash": r.get("Tx Hash", "")}
                rep["flow"]["trx"].append(rec)

    # ---- USDT 汇总（token CSV） ----
    us = rep["flow"]["usdt"]
    if us:
        for rec in us:
            if rec["to"].lower() == tgt:
                rep["flow"]["usdt_in"] += rec["val"]
            if rec["from"].lower() == tgt:
                rep["flow"]["usdt_out"] += rec["val"]
        rep["flow"]["usdt_n"] = len(us)
        # 时间排序（字符串 YYYY/MM/DD HH:MM:SS 可直接字典序）
        us_sorted = sorted(us, key=lambda x: x["time"] or "")
        rep["flow"]["usdt_ordered"] = us_sorted
        rep["flow"]["start"], rep["flow"]["end"] = us_sorted[0]["time"], us_sorted[-1]["time"]
        # 单笔最大
        if rep["flow"]["usdt_in"] > 0:
            rep["flow"]["biggest_in"] = max((x for x in us if x["to"].lower() == tgt), key=lambda x: x["val"])
        if rep["flow"]["usdt_out"] > 0:
            rep["flow"]["biggest_out"] = max((x for x in us if x["from"].lower() == tgt), key=lambda x: x["val"])
        # 资金来源 / 去向 TOP
        in_c = defaultdict(lambda: {"amt": 0.0, "n": 0})
        out_c = defaultdict(lambda: {"amt": 0.0, "n": 0})
        for rec in us:
            if rec["to"].lower() == tgt:
                in_c[rec["from"]]["amt"] += rec["val"]
                in_c[rec["from"]]["n"] += 1
            if rec["from"].lower() == tgt:
                out_c[rec["to"]]["amt"] += rec["val"]
                out_c[rec["to"]]["n"] += 1
        total_in = rep["flow"]["usdt_in"] or 1
        total_out = rep["flow"]["usdt_out"] or 1
        for addr, d in sorted(in_c.items(), key=lambda x: -x[1]["amt"])[:10]:
            rep["funding"].append({"addr": addr, "amt": d["amt"], "n": d["n"], "pct": d["amt"] / total_in * 100})
        for addr, d in sorted(out_c.items(), key=lambda x: -x[1]["amt"])[:10]:
            rep["dest"].append({"addr": addr, "amt": d["amt"], "n": d["n"], "pct": d["amt"] / total_out * 100})
        # 快速转移（收到 X 内转出；同一对手方出现 in+out 且间隔小 → pass-through 特征）
        for rec in us:
            if rec["from"].lower() != tgt and rec["to"].lower() == tgt:
                # 找该 from 稍后转出记录
                later = [o for o in us if o["from"].lower() == tgt and o["to"].lower() == rec["from"].lower()
                         and o["time"] and rec["time"] and o["time"] >= rec["time"]]
                if later:
                    o = min(later, key=lambda x: x["time"])
                    rep["rapid"].append({"in": rec, "out": o, "cp": rec["from"]})

    # ---- TRX 汇总（transaction CSV） ----
    tx = rep["flow"]["trx"]
    if tx:
        rep["flow"]["trx_n"] = len(tx)
        for rec in tx:
            if rec["to"].lower() == tgt:
                rep["flow"]["trx_in"] += rec["val"]
            if rec["from"].lower() == tgt:
                rep["flow"]["trx_out"] += rec["val"]
        tx_sorted = sorted(tx, key=lambda x: x["time"] or "")
        rep["flow"]["trx_ordered"] = tx_sorted
        rep["flow"]["trx_start"], rep["flow"]["trx_end"] = tx_sorted[0]["time"], tx_sorted[-1]["time"]
        if rep["flow"]["trx_in"] > 0:
            rep["flow"]["biggest_in"] = max((x for x in tx if x["to"].lower() == tgt), key=lambda x: x["val"])
        if rep["flow"]["trx_out"] > 0:
            rep["flow"]["biggest_out"] = max((x for x in tx if x["from"].lower() == tgt), key=lambda x: x["val"])
        # TRX 来源/去向 TOP（TRX 尘模式检测：集中来源高频小额）
        in_c = defaultdict(lambda: {"amt": 0.0, "n": 0})
        out_c = defaultdict(lambda: {"amt": 0.0, "n": 0})
        for rec in tx:
            if rec["to"].lower() == tgt:
                in_c[rec["from"]]["amt"] += rec["val"]
                in_c[rec["from"]]["n"] += 1
            if rec["from"].lower() == tgt:
                out_c[rec["to"]]["amt"] += rec["val"]
                out_c[rec["to"]]["n"] += 1
        total_in = rep["flow"]["trx_in"] or 1
        total_out = rep["flow"]["trx_out"] or 1
        for addr, d in sorted(in_c.items(), key=lambda x: -x[1]["amt"])[:10]:
            rep["funding"].append({"addr": addr, "amt": d["amt"], "n": d["n"], "pct": d["amt"] / total_in * 100, "asset": "TRX"})
        for addr, d in sorted(out_c.items(), key=lambda x: -x[1]["amt"])[:10]:
            rep["dest"].append({"addr": addr, "amt": d["amt"], "n": d["n"], "pct": d["amt"] / total_out * 100, "asset": "TRX"})
        # 尘交易模式（C 级特征描述）
        dust_src = [(a, d) for a, d in in_c.items() if d["amt"] < 1.0 and d["n"] >= 10]
        if dust_src:
            top_dust = max(dust_src, key=lambda x: x[1]["n"])
            rep["anomaly"].append({
                "grade": "C", "title": "高频微量 TRX 入账（尘交易模式）",
                "desc": "来自 {src} 的 {n} 笔微量 TRX（合计 {amt} TRX）高频入账。该模式常见于空投/批量运营/防追踪拆单等场景，也可能为地址活跃度制造信号；仅凭该模式无法判定资金性质。".format(
                    src=_addr_short(top_dust[0]), n=top_dust[1]["n"], amt=_fmt_amt(top_dust[1]["amt"], 6))})

    # ---- 异常行为（transaction CSV：能量委托） ----
    dlg_delegate = dlg_undelegate = 0
    for r in rows:
        ct = r.get("contractType", "")
        if ct == "DelegateResourceContract":
            dlg_delegate += 1
        elif ct == "UnDelegateResourceContract":
            dlg_undelegate += 1
    rep["dlg"] = {"delegate": dlg_delegate, "undelegate": dlg_undelegate}
    if dlg_delegate + dlg_undelegate > 0:
        rep["anomaly"].append({
            "grade": "C", "title": "高频资源委托/解除",
            "desc": "共 {de} 次委托 + {un} 次解除（合计 {n} 次）。该行为模式可能与高频交易、资金管理、自动化运营或场外兑换(OTC)等场景相符；**无法仅凭资源委托行为证明该地址属于 OTC 或从事特定业务**。".format(
                de=dlg_delegate, un=dlg_undelegate, n=dlg_delegate + dlg_undelegate)})

    # ---- 冻结前 24h 活动（有确切冻结时间才统计） ----
    ft = chain.get("freeze_time", "")
    if ft and len(ft) >= 19 and ft[-3:] == "UTC":
        # freeze_time 形如 2026-08-08 21:20:36 UTC
        try:
            ft_dt = datetime.strptime(ft[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            ft_ms = ft_dt.timestamp() * 1000
        except ValueError:
            ft_dt, ft_ms = None, None
        # CSV 时间字符串 YYYY/MM/DD HH:MM:SS (UTC+8 或 UTC 列?) ——transaction CSV 用 blockTime(UTC)
        # 2026-09-06：transaction CSV 无 USDT 时只用 TRX ≥1 的行做邻近（尘交易 1e-6 无调查价值且易误导）
        pool = us if us else [x for x in tx if x.get("val", 0) >= 1.0]
        if pool and ft_dt:
            pre24 = [x for x in pool if x["time"]]
            # 找冻结前 24h 窗口：把 CSV 时间字符串解析（UTC）
            import datetime as _dt
            def _cvt(t):
                try:
                    return _dt.datetime.strptime(t, "%Y/%m/%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except Exception:
                    return None
            pre24 = []
            for x in pool:
                xd = _cvt(x["time"])
                if xd is not None and xd <= ft_dt:
                    pre24.append(x)
            if pre24:
                recent = sorted(pre24, key=lambda x: x["time"] or "", reverse=True)[:8]
                for x in recent:
                    xd = _cvt(x["time"])
                    rel = (ft_dt - xd).total_seconds() / 3600 if xd else None
                    x["hours_before"] = rel
                    rep["adjacent"].append(x)

    # ---- 对手方冻结状态（chain.cp_status 注入） ----
    for a in list({(x.get("addr") or "").lower() for x in rep["funding"] + rep["dest"] if x.get("addr")}):
        st = chain.get("cp_status", {}).get(a)
        if st is True:
            rep["cp_freeze"][a] = True
        elif st is False:
            rep["cp_freeze"][a] = False
        elif st is None:
            pass

    # ---- TRC-10 垃圾币 / 疑似诈骗代币（扫描全部行） ----
    trc10_c = defaultdict(lambda: {"cnt": 0, "amt": 0.0})
    scam_c = defaultdict(lambda: {"cnt": 0, "amt": 0.0})
    for r in rows:
        sym = r.get("symbol", "")
        if fmt == "transaction":
            ct = r.get("contractType", "")
            if ct == "TransferAssetContract" and sym:
                # BL 等 TRC-10 垃圾币：非冻结标记（铁律 #2）
                trc10_c[sym]["cnt"] += 1
                trc10_c[sym]["amt"] += r.get("_value", 0.0) or 0.0
                up = sym.upper()
                if any(k in up for k in ("UNFREEZE", "UNLOCK", "UNBANNED")) or "解封" in sym:
                    scam_c[sym]["cnt"] += 1
                    scam_c[sym]["amt"] += r.get("_value", 0.0) or 0.0
        else:
            if sym and sym != "USDT":
                trc10_c[sym]["cnt"] += 1
                trc10_c[sym]["amt"] += r.get("_value", 0.0) or 0.0
    rep["trc10"] = sorted(trc10_c.items(), key=lambda x: -x[1]["cnt"])[:10]
    rep["scam"] = sorted(scam_c.items(), key=lambda x: -x[1]["cnt"])[:10]

    # ---- 风险构成（口径与 API 报告 60/30 对齐；C 级推断） ----
    rk = rep["risk"]
    if rep["freeze"]["blacklisted"] is True or (chain.get("index_frozen") and rep["freeze"]["blacklisted"] is not False):
        rk["official"] = 40
    # 行为因子
    if rep["dlg"]["delegate"] + rep["dlg"]["undelegate"] >= 50:
        rk["behavior"] += 5
    if len(rep["anomaly"]) >= 2:
        rk["behavior"] += 5
    if us and rep["flow"]["usdt_in"] > 0:
        # 冻结前 24h 大额流入（B 级）
        pass
    # 关系因子
    frozen_cp = sum(1 for v in rep["cp_freeze"].values() if v is True)
    if frozen_cp:
        rk["relation"] += 10
    # 新地址（chain.created <90d）(B)
    if chain.get("account_age_days") is not None and chain["account_age_days"] < 90:
        rk["behavior"] += 8
    # 2026-09-06 修：先加因子再冻结封顶 95（原顺序致 145 超 100）
    rk["total"] = 10 + rk["official"] + rk["behavior"] + rk["relation"] + rk["other"]
    if chain.get("is_blacklisted") is True:
        rk["total"] = max(95, rk["total"])

    # ---- 冻结原因可能性（合规：A/B/C 标注，无法证明单笔因果） ----
    cs = rep["causes"]
    if rep["freeze"]["blacklisted"] is True or chain.get("index_frozen"):
        cs.append({"title": "地址被加入 Tether 黑名单（事实）", "like": "已确认",
                   "grade": "A", "ev": "USDT 合约 isBlackListed=true；AddedBlackList 事件"})
    if rep["dlg"]["delegate"] + rep["dlg"]["undelegate"] >= 50:
        cs.append({"title": "高频资源委托/解除行为", "like": "中", "grade": "C",
                   "ev": "委托 {d} 次 + 解除 {u} 次（{n} 次总操作）".format(d=rep["dlg"]["delegate"], u=rep["dlg"]["undelegate"], n=rep["dlg"]["delegate"] + rep["dlg"]["undelegate"])})
    if us and rep["adjacent"]:
        big = max((x for x in rep["adjacent"] if x["val"] > 0), key=lambda x: x["val"], default=None)
        if big:
            cs.append({"title": "冻结前出现资金活动", "like": "低-中", "grade": "C",
                       "ev": "冻结前 {h:.1f} 小时 {dir} {amt}（对手方 {cp}）".format(
                           h=big.get("hours_before", 0), dir="收到" if big["to"].lower() == tgt else "转出",
                           amt=_fmt_amt(big["val"]), cp=_addr_short(big["from"] if big["to"].lower() == tgt else big["to"]))})
    cs.append({"title": "单一交易直接导致冻结", "like": "无法证明", "grade": "-",
               "ev": "链上公开数据不足以确认 Tether 因哪一笔交易执行冻结。时间上的先后不代表因果关系。"})

    # ---- 证据清单 ----
    ev = rep["evidence"]
    if rep["freeze"]["blacklisted"] is not None or chain.get("index_frozen"):
        ev.append({"id": "E01", "grade": "A", "title": "官方冻结状态",
                   "detail": "USDT 合约 isBlackListed = {}（{}）".format(
                       "TRUE" if rep["freeze"]["blacklisted"] is True else ("FALSE" if rep["freeze"]["blacklisted"] is False else "暂无法实时确认"),
                       "本地索引辅助" if rep["freeze"]["blacklisted"] is None and chain.get("index_frozen") else "链上实时")})
    if rep["freeze"]["tx"]:
        ev.append({"id": "E02", "grade": "A", "title": "AddedBlackList 事件（冻结证据交易）",
                   "detail": "TX {tx} @ {t} · tronscan.org/#/transaction/{tx}".format(
                       tx=rep["freeze"]["tx"], t=rep["freeze"]["time"])})
    if us:
        if rep["flow"]["biggest_in"]:
            b = rep["flow"]["biggest_in"]
            ev.append({"id": "E03", "grade": "A", "title": "最大单笔 USDT 流入",
                       "detail": "{amt} USDT @ {t} from {f} · TX {h}".format(
                           amt=_fmt_amt(b["val"]), t=b["time"], f=_addr_short(b["from"]), h=_tx_short(b["hash"]))})
        if rep["rapid"]:
            rp = rep["rapid"][0]
            ev.append({"id": "E04", "grade": "B", "title": "快速转出（Pass-through 特征）",
                       "detail": "{a} → {cp} → {b}（{amt} USDT）".format(
                           a=_addr_short(rp["in"]["from"]), cp=_addr_short(rp["cp"]),
                           b=_addr_short(rp["out"]["to"]), amt=_fmt_amt(rp["in"]["val"]))})
    if frozen_cp:
        ev.append({"id": "E05", "grade": "A", "title": "对手方已被冻结",
                   "detail": "共 {n} 个对手方命中本地冻结索引（AddedBlackList）".format(n=frozen_cp)})

    return rep


def render_markdown(rep):
    """把分析 dict 渲染为 Markdown 取证报告（动态模块）。"""
    L = []
    a = L.append
    meta = rep["meta"]
    tgt = meta["target"]
    us = rep["flow"]["usdt"]
    tx = rep["flow"]["trx"]
    usdt_fmt = meta["fmt"] == "token_transfer"
    fmt_label = "tokenTransfer（USDT 资金流）" if usdt_fmt else "transaction（区块交易·无 USDT 明细）"
    fmt_type = "token_transfer" if usdt_fmt else "transaction"

    a("# USDT 冻结与资金流取证分析报告")
    a("")
    a("> USDT Freeze Forensics Report · 由 USDT Freeze Check 基于公开链上数据自动生成")
    a("")
    a("**生成时间**: {t}  **CSV 类型**: {f}  **总行数**: {n}".format(t=meta["gen_time"], f=fmt_label, n=meta["rows_n"]))
    a("**目标地址**: `{t}`".format(t=tgt))
    a("")
    a("---")
    a("")

    # ===== 0/1. 执行摘要 =====
    bl = rep["freeze"]["blacklisted"]
    idx_frozen = rep["chain"].get("index_frozen")
    frozen_state = "未确认"
    if bl is True:
        frozen_state = "🔴 BLACKLISTED（已冻结）"
    elif bl is False:
        frozen_state = "🟢 未冻结（官方确认）"
    elif idx_frozen:
        frozen_state = "🟠 冻结状态待确认（本地索引显示曾冻结）"
    a("## 0. 调查结论（Executive Summary）")
    a("")
    a("| 项目 | 结论 |")
    a("| --- | --- |")
    a("| 地址 | `{t}` |".format(t=tgt))
    a("| Tether 官方状态 | {s} |".format(s=frozen_state))
    a("| 确切冻结时间 | {f} |".format(f=rep["freeze"]["time"] or "-（未确认/未收录）"))
    a("| 冻结证据交易 | {f} |".format(f=rep["freeze"]["tx"] and "`" + rep["freeze"]["tx"] + "`" or "-"))
    a("| CSV 行数 | {n} |".format(n=meta["rows_n"]))
    if rep["flow"].get("start"):
        a("| 时间范围 | {s} → {e} |".format(s=rep["flow"]["start"], e=rep["flow"]["end"]))
    if us:
        a("| USDT 流入 | {v} USDT（{n} 笔）|".format(v=_fmt_amt(rep["flow"]["usdt_in"]), n=len([x for x in us if x["to"].lower() == tgt])))
        a("| USDT 流出 | {v} USDT（{n} 笔）|".format(v=_fmt_amt(rep["flow"]["usdt_out"]), n=len([x for x in us if x["from"].lower() == tgt])))
    if tx:
        a("| TRX 转账 | {n} 笔（净 {net:+.4f} TRX）|".format(n=len(tx), net=rep["flow"]["trx_in"] - rep["flow"]["trx_out"]))
    a("| 风险评分 | **{s} / 100** |".format(s=rep["risk"]["total"]))
    a("")
    a("**最重要发现**：")
    a("")
    finds = []
    if bl is True:
        finds.append("① 官方黑名单状态确认（isBlackListed = TRUE）")
    elif idx_frozen:
        finds.append("① 本地索引显示该地址曾被加入黑名单（实时状态待复核）")
    if us and rep["flow"].get("biggest_in"):
        b = rep["flow"]["biggest_in"]
        finds.append("② 最大单笔资金{inout} {amt}（对手方 {cp}）".format(
            inout="流入" if b["to"].lower() == tgt else "流出", amt=_fmt_amt(b["val"]), cp=_addr_short(b["from"] if b["to"].lower() == tgt else b["to"])))
    if rep["funding"]:
        finds.append("③ 资金主要来自 {n} 个地址（最大来源占比 {p:.1f}%）".format(
            n=len(rep["funding"]), p=rep["funding"][0]["pct"] if rep["funding"][0]["pct"] <= 100 else 100))
    if rep["dlg"]["delegate"] + rep["dlg"]["undelegate"] > 0:
        finds.append("④ 存在 {n} 次资源委托/解除操作".format(n=rep["dlg"]["delegate"] + rep["dlg"]["undelegate"]))
    if rep["adjacent"]:
        finds.append("⑤ 冻结前存在邻近资金活动（{n} 笔；先后≠因果）".format(n=len(rep["adjacent"])))
    if not finds:
        finds.append("① CSV 内未发现显著异常信号；结论详见以下章节。")
    for f in finds:
        a("> " + f)
    a("")
    a("---")
    a("")

    # ===== 2. 官方冻结证据 =====
    a("## 1. 官方冻结证据（Official Freeze Evidence）")
    a("")
    a("| 项目 | 结果 |")
    a("| --- | --- |")
    a("| USDT Contract | `{c}` |".format(c=USDT_CONTRACT))
    a("| isBlackListed | {v} |".format(v="**TRUE**" if bl is True else ("**FALSE**" if bl is False else "暂无法实时确认（链上服务波动）")))
    a("| Freeze event | {v} |".format(v="`AddedBlackList`" if (bl is True or idx_frozen) else "-"))
    a("| Freeze time | {v} |".format(v=rep["freeze"]["time"] or "-"))
    a("| Event TX | {v} |".format(v="`" + rep["freeze"]["tx"] + "`" if rep["freeze"]["tx"] else "-"))
    a("| Index source | USDT Freeze Index（AddedBlackList/RemovedBlackList 链上事件索引）|")
    a("| Index updated | {v} |".format(v=rep["freeze"]["db_updated"] or "-"))
    a("")
    a("> **证据等级：A — 链上直接证据**（来自 USDT 合约状态 / AddedBlackList 事件，非推断）")
    a("")
    if bl is None and not idx_frozen:
        a("> ⚠️ 实时合约状态暂无法验证。若需确认，请稍后重试或使用上方免费诊断工具输入地址复核。")
        a("")
    a("---")
    a("")

    # ===== 3. 资金流概况 =====
    a("## 2. 资金流概况（Flow Overview）")
    a("")
    if us:
        a("**USDT（TRC-20）** · 链上事实：")
        a("")
        a("| 指标 | 数值 |")
        a("| --- | --- |")
        a("| 笔数 | {n} |".format(n=rep["flow"]["usdt_n"]))
        a("| 流入总额 | {v} USDT |".format(v=_fmt_amt(rep["flow"]["usdt_in"])))
        a("| 流出总额 | {v} USDT |".format(v=_fmt_amt(rep["flow"]["usdt_out"])))
        a("| 净额 | {v:+.2f} USDT |".format(v=rep["flow"]["usdt_in"] - rep["flow"]["usdt_out"]))
        if rep["flow"].get("biggest_in"):
            b = rep["flow"]["biggest_in"]
            a("| 最大单笔流入 | {v} USDT（{t} · {cp}）|".format(v=_fmt_amt(b["val"]), t=b["time"], cp=_addr_short(b["from"])))
        if rep["flow"].get("biggest_out"):
            b = rep["flow"]["biggest_out"]
            a("| 最大单笔流出 | {v} USDT（{t} · {cp}）|".format(v=_fmt_amt(b["val"]), t=b["time"], cp=_addr_short(b["to"])))
        a("")
    if tx:
        a("**TRX 转账** · 链上事实：")
        a("")
        a("| 指标 | 数值 |")
        a("| --- | --- |")
        a("| 笔数 | {n} |".format(n=rep["flow"]["trx_n"]))
        a("| 收入总额 | {v:.6f} TRX |".format(v=rep["flow"]["trx_in"]))
        a("| 支出总额 | {v:.6f} TRX |".format(v=rep["flow"]["trx_out"]))
        a("| 净额 | {v:+.6f} TRX |".format(v=rep["flow"]["trx_in"] - rep["flow"]["trx_out"]))
        a("")
    if not us and not tx:
        a("本 CSV 未发现 USDT TRC-20 转账与 TRX TransferContract 记录。")
        a("")
    if not us and fmt_type == "transaction":
        a("> ⚠️ **CSV 类型限制**：transaction CSV 不包含 USDT TRC-20 转账明细。如需完整 USDT 资金流/来源/去向分析，请在 TronScan 导出 **tokenTransfer CSV** 后重新生成。")
        a("")
    a("---")
    a("")

    # ===== 4. 资金来源 TOP =====
    if rep["funding"]:
        asset = rep["funding"][0].get("asset", "USDT")
        a("## 3. 资金来源（Top Funding Sources）")
        a("")
        a("| 来源地址 | 金额 | 占比 | 笔数 | 冻结状态 |")
        a("| --- | --- | --- | --- | --- |")
        for d in rep["funding"][:10]:
            cpf = rep["cp_freeze"].get((d["addr"] or "").lower())
            cpf_s = "🔴 冻结" if cpf is True else ("🟢 未冻结" if cpf is False else "-")
            a("| `{a}` | {v} {asset} | {p:.1f}% | {n} | {s} |".format(
                a=_esc(d["addr"]), v=_fmt_amt(d["amt"]), asset=asset, p=d["pct"], n=d["n"], s=cpf_s))
        a("")
        a("**来源集中度（B — 数据推导）**：最大资金来源占{asset}总流入 **{p:.1f}%**。".format(asset=asset, p=rep["funding"][0]["pct"]))
        a("")
        a("---")
        a("")

    # ===== 5. 资金去向 TOP =====
    if rep["dest"]:
        asset = rep["dest"][0].get("asset", "USDT")
        a("## 4. 资金去向（Top Destinations）")
        a("")
        a("| 去向地址 | 金额 | 占比 | 笔数 | 冻结状态 |")
        a("| --- | --- | --- | --- | --- |")
        for d in rep["dest"][:10]:
            cpf = rep["cp_freeze"].get((d["addr"] or "").lower())
            cpf_s = "🔴 冻结" if cpf is True else ("🟢 未冻结" if cpf is False else "-")
            a("| `{a}` | {v} {asset} | {p:.1f}% | {n} | {s} |".format(
                a=_esc(d["addr"]), v=_fmt_amt(d["amt"]), asset=asset, p=d["pct"], n=d["n"], s=cpf_s))
        a("")
        a("---")
        a("")

    # ===== 6. 冻结邻近交易 =====
    if rep["adjacent"]:
        a("## 5. 冻结前邻近资金活动（Freeze-adjacent）")
        a("")
        a("> ⚠️ **时间上的先后不代表因果关系**（铁律）。以下仅按链上时间列出冻结前活动。")
        a("")
        a("| 时间 | 方向 | 金额 | 对手方 | 距冻结 |")
        a("| --- | --- | --- | --- | --- |")
        for x in rep["adjacent"]:
            is_in = x["to"].lower() == tgt
            hb = x.get("hours_before")
            hb_s = "{h:.1f}h".format(h=hb) if hb is not None else "-"
            a("| {t} | {dir} | {v} | {cp} | {hb} |".format(
                t=x["time"], dir="IN" if is_in else "OUT", v=_fmt_amt(x["val"]),
                cp=_addr_short(x["from"] if is_in else x["to"]), hb=hb_s))
        a("")
        a("---")
        a("")

    # ===== 7. 快速转移 =====
    if rep["rapid"]:
        a("## 6. 快速转移检测（Pass-through 特征 · C 级推断）")
        a("")
        a("> 检测到「收到后短时间内转出至同一对手方」的资金路径特征。**只能说资金路径特征，不能断定资金性质。**")
        a("")
        for rp in rep["rapid"][:8]:
            a("- `{a}` → {amt} USDT @ {ti} → {cp} → {amt2} USDT @ {to} → `{b}`".format(
                a=_addr_short(rp["in"]["from"]), amt=_fmt_amt(rp["in"]["val"]), ti=rp["in"]["time"],
                cp=_addr_short(rp["cp"]), amt2=_fmt_amt(rp["out"]["val"]), to=rp["out"]["time"], b=_addr_short(rp["out"]["to"])))
        a("")
        a("---")
        a("")

    # ===== 8. 异常行为 =====
    if rep["anomaly"]:
        a("## 7. 行为特征分析（Behavior Analysis）")
        a("")
        for an in rep["anomaly"]:
            a("- **{t}**（证据等级 {g} — {grade_desc}）：{d}".format(
                t=an["title"], g=an["grade"],
                grade_desc={"A": "链上事实", "B": "数据推导", "C": "风险推断"}.get(an["grade"], "风险推断"),
                d=an["desc"]))
        a("")
        if rep["dlg"]["delegate"] + rep["dlg"]["undelegate"] > 0:
            a("**资源委托行为**：Delegate {de} / Undelegate {un} / 总操作 {n} 次。".format(
                de=rep["dlg"]["delegate"], un=rep["dlg"]["undelegate"], n=rep["dlg"]["delegate"] + rep["dlg"]["undelegate"]))
            a("")
        a("> 该行为模式可能与高频交易、资金管理、自动化运营或 OTC 等场景相符；**无法仅凭行为特征证明该地址从事特定业务**。")
        a("")
        a("---")
        a("")

    # ===== 9. 风险构成 =====
    rk = rep["risk"]
    a("## 8. 风险评分与构成（Risk Score）")
    a("")
    a("**风险评分：{s} / 100**（口径与免费诊断一致：≥60 高风险 / ≥30 中风险 / <30 低风险）".format(s=rk["total"]))
    a("")
    a("| 因子 | 分数 | 证据分级 |")
    a("| --- | --- | --- |")
    a("| 官方冻结状态 | +{v} | A 链上事实 |".format(v=rk["official"]))
    a("| 行为因子（委托/尘交易/异常） | +{v} | B/C |".format(v=rk["behavior"]))
    a("| 关联因子（对手方冻结） | +{v} | A/B |".format(v=rk["relation"]))
    a("| 其他 | +{v} | - |".format(v=rk["other"]))
    a("| 基础分 | +10 | - |")
    a("")
    a("> 评分由本站基于公开链上数据分析计算，**不代表 Tether、TRON 或任何司法机构的认定**。")
    a("")
    a("---")
    a("")

    # ===== 10. 冻结原因可能性 =====
    if rep["causes"]:
        a("## 9. 冻结原因可能性评估（Freeze Cause Assessment）")
        a("")
        a("| 可能性 | 因素 | 证据分级 | 证据 |")
        a("| --- | --- | --- | --- |")
        for c in rep["causes"]:
            a("| {like} | {t} | {g} | {ev} |".format(like=c["like"], t=c["title"], g=c["grade"], ev=_esc(c["ev"])))
        a("")
        a("> **重要**：以上为基于公开数据的可能性分析，**不是对冻结原因的官方认定**。链上公开数据通常不足以确认 Tether 因哪一笔交易执行冻结。")
        a("")
        a("---")
        a("")

    # ===== 11. 证据清单 =====
    if rep["evidence"]:
        a("## 10. 证据清单（Evidence Index）")
        a("")
        a("可将以下编号证据直接提供给律师/交易所/合规人员：")
        a("")
        for e in rep["evidence"]:
            a("- **{id}** [{g}] {t}：{d}".format(id=e["id"], g=e["grade"], t=e["title"], d=_esc(e["detail"])))
        a("")
        a("---")
        a("")

    # ===== 12. 垃圾币/诈骗代币 =====
    if rep["scam"]:
        a("## 11. 疑似诈骗/解冻代币（Scam Tokens）")
        a("")
        a("| 代币 | 笔数 | 金额 |")
        a("| --- | --- | --- |")
        for name, d in rep["scam"]:
            a("| `{n}` | {c} | {a} |".format(n=_esc(name), c=d["cnt"], a=_fmt_amt(d["amt"])))
        a("")
        a("> ⚠️ UNFREEZE/UNLOCK/UNBANNED 等代币全是骗子空投，**Tether 官方不会用链上备注或 TG 联系你**。")
        a("")
        a("---")
        a("")

    # ===== 13. TRC-10 垃圾币 =====
    if rep["trc10"]:
        a("## 12. 其他 TRC-10 代币（非 USDT）")
        a("")
        a("| 代币 | 笔数 | 金额 |")
        a("| --- | --- | --- |")
        for name, d in rep["trc10"]:
            a("| `{n}` | {c} | {a} |".format(n=_esc(name), c=d["cnt"], a=_fmt_amt(d["amt"])))
        a("")
        a("> ℹ️ symbol=BL 等 TRC-10 代币为链上任意发行的垃圾币，**不是 Tether 冻结标记**（官方冻结证据见第 1 章 isBlackListed/AddedBlackList）。")
        a("")
        a("---")
        a("")

    # ===== 14. 申诉建议 =====
    a("## 13. 申诉建议（Appeal Guidance）")
    a("")
    a("1. **收集交易凭证**：整理与高风险对手方交易的完整记录（聊天记录、合同、发票、物流单据），证明交易背景真实合法。")
    a("2. **准备 KYC 材料**：更新交易所 KYC 信息，提供身份证明、地址证明、资金来源说明。")
    a("3. **提交申诉工单**：通过交易所官方渠道申诉，附本报告与证据清单（第 10 章 E01 起）。")
    a("4. **寻求法律支持**：如申诉被拒，考虑委托专业律师发函或向监管机构投诉。")
    a("")
    a("> ⚠️ 本工具不承诺任何解冻结果，是否解冻取决于发行方及具体情况。**声称付费即可保证解冻的多为诈骗**。")
    a("")
    a("---")
    a("")

    # ===== 15. 方法论与免责 =====
    a("## 14. 方法论与免责声明（Methodology & Disclaimer）")
    a("")
    a("- 本报告基于用户上传的 TronScan CSV 全量统计 + 链上公开数据（USDT 合约/TronGrid/事件索引），**可复核**。")
    a("- 证据分级：**A 链上事实**（合约状态/事件/交易记录） / **B 数据推导**（统计模式） / **C 风险推断**（行为解释）。")
    a("- 金额/笔数/时间为链上事实；触发原因等为推断。**时间邻近 ≠ 冻结因果**。")
    a("- 动态模块：本报告只展示有数据的章节；如数据不足，相关模块自动省略。")
    a("- 本服务不提供法律建议，不接触、不转移用户资产。")
    a("")
    a("---")
    a("")
    a("*USDT Freeze Check*")

    return "\n".join(L)


def analyze_csv_bytes(rows, fmt, target_addr, chain=None):
    """便捷入口：rows 已 load_csv（含 _value），fmt 已 detect。返回 render_markdown 需要的 rep + md"""
    rep = analyze(rows, fmt, target_addr, chain=chain)
    md = render_markdown(rep)
    return rep, md
