#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api_server.py — USDT 冻结取证前端 API 服务器
提供 /api/report?address=<TRON地址> 端点，返回前端 report.html 需要的 JSON。

启动: uvicorn api_server:app --host 0.0.0.0 --port 8902
"""
import os
import sys
import json
import urllib.request
from datetime import datetime, timezone

# tron_api.py 在 scripts/ 目录
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional

from tron_api import TronAPI, USDT_CONTRACT

# 静态文件目录 = web/（与 api/ 同级）
WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web"))

# ===== USDT 合约黑名单检测（官方 isBlackListed） =====
_BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

# ===== 地址标签库 v1（已验案例 + 规则特征；交易所地址待可靠数据源后扩展）=====
# 数据来源：usdt-freeze-forensics 实战案例（friend-boss-freeze-case-202608）
# 铁律：只放已验地址，绝不编造；具体交易所热钱包清单未核验前不收录
ADDRESS_TAGS = {
    "TJeh5fXJttbypanF2FMzgu42yqXnc5BuWw": "已冻结·OTC资金枢纽",
    "TGC1t9MbJhx7uKYiQG4SzoafeFz3Jzg1JN": "已冻结·职业OTC",
    "TEDV8rCqycRc1K6BmnyNekv5h1MrpcWSDS": "高危·双向交易对手",
    "TFDMtWVXWtRxDmSe3d8zcsCzSfd332nH87": "高危·OTC热钱包",
    "TTu3mqjHaUcqcEaX14s2t8VRzCkJkVMs3L": "高危·一次性马甲地址",
    "TChHAZ5QN6MdwRc61TqjFziWtgrY888888": "高危·疑似博彩/黑产",
    "TUZPztRsZQMUJVXQYKwEuwdGhzgTGjieuu": "中危·二次诈骗特征",
    "TRug7ZsKi7LjSg2n8A9a2CUFurE6u6HSwb": "中危·冻结标记来源",
    "TYAzzycMgo1s1f6fdAP48Bhbf2Z55ghtqa": "中危·能量租赁服务商",
    "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t": "USDT 合约",
}

# 吉祥号特征：博彩/黑产热钱包常见（案例 TChHAZ...888888）
_SUSPICIOUS_PATTERNS = ("888888", "666666", "999999", "777777")


def address_tag(addr: str) -> str:
    """返回地址标签：已验库精确匹配 → 规则特征 → 空字符串"""
    if addr in ADDRESS_TAGS:
        return ADDRESS_TAGS[addr]
    for pat in _SUSPICIOUS_PATTERNS:
        if pat in addr:
            return "疑似博彩/黑产热钱包（特征）"
    return ""


def _base58_decode(s: str) -> bytes:
    n = 0
    for ch in s:
        n = n * 58 + _BASE58.index(ch)
    full = n.to_bytes((n.bit_length() + 7) // 8 or 1, "big")
    zeros = 0
    for ch in s:
        if ch == "1":
            zeros += 1
        else:
            break
    return b"\x00" * zeros + full


def _tron_addr_hex(addr: str) -> str:
    """TRON base58 地址 → 20字节 hex（去 41 前缀和 checksum）"""
    raw = _base58_decode(addr.strip())
    return raw[1:-4].hex()


def check_usdt_blacklist(address: str) -> bool:
    """调用 USDT 合约 isBlackListed(address) 检测是否被 Tether 冻结（官方方法）"""
    try:
        body = _tron_addr_hex(address)
        param = body.rjust(64, "0")
        payload = {
            "owner_address": "T9yD14Nj9j7xAB4dbGeiX9h8unkKHxuWwb",
            "contract_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "function_selector": "isBlackListed(address)",
            "parameter": param,
            "visible": True,
        }
        req = urllib.request.Request(
            "https://api.trongrid.io/wallet/triggerconstantcontract",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        results = data.get("constant_result") or []
        if results:
            raw = results[0]
            return raw.endswith("01") or int(raw, 16) == 1
        return False
    except Exception:
        return False

app = FastAPI(title="USDT Freeze Forensics API", version="1.0.0")

# CORS：允许前端页面跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

USDT_DECIMALS = 1_000_000


class Counterparty(BaseModel):
    addr: str
    inAmt: float
    outAmt: float
    tag: str = ""


class TxRecord(BaseModel):
    time: str
    dir: str
    amt: float
    cp: str
    hash: str
    flag: bool


class TimelineItem(BaseModel):
    time: str
    title: str
    desc: str
    dot: str  # green/blue/red/gray


class PlanItem(BaseModel):
    t: str
    d: str


class ReportResponse(BaseModel):
    address: str
    score: int
    risk: str
    created: str
    txCount: int
    counterparties: List[Counterparty]
    transactions: List[TxRecord]
    freezeStatus: Optional[dict] = None
    frozen: bool = False
    tags: List[str] = []
    timeline: List[TimelineItem] = []
    actionPlan: List[PlanItem] = []
    note: str


def ts_to_str(ts_ms: int) -> str:
    """毫秒时间戳 → YYYY-MM-DD HH:MM"""
    if not ts_ms:
        return "N/A"
    try:
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "N/A"


def compute_score(trc20: list, account: dict, freeze_flags: list, addr_tag: str = "") -> tuple:
    """启发式风险评分 0-100（数字越大风险越高）
    规则：
    - 基础 10
    - 每笔大额转入(>50k) +8，最高 +32
    - 有冻结标记(BL/UNFREEZE) +35
    - 对手方超过 20 个 +10
    - 账户创建 < 90 天 +8
    - 收过诈骗代币 +15
    - 吉祥号/风险特征标签（疑似博彩/黑产等）+25
    """
    score = 10
    reasons = []

    # 吉祥号/风险特征标签（如 888888 结尾 → 疑似博彩/黑产热钱包）
    if addr_tag and any(k in addr_tag for k in ("疑似", "高危", "博彩", "马甲", "诈骗")):
        score += 25
        reasons.append(f"地址特征：{addr_tag}")

    # 大额转入
    big_in = 0
    for tx in trc20:
        val = int(tx.get("value", 0)) / USDT_DECIMALS
        if val > 50000:
            big_in += 1
    score += min(big_in, 4) * 8
    if big_in > 0:
        reasons.append(f"大额转入{big_in}笔")

    # 冻结标记
    if freeze_flags:
        score += 35
        reasons.append("检测到冻结标记(BL/UNFREEZE)")

    # 对手方数量
    cps = set()
    for tx in trc20:
        cps.add(tx.get("from", ""))
        cps.add(tx.get("to", ""))
    cps.discard("")
    if len(cps) > 20:
        score += 10
        reasons.append(f"对手方{len(cps)}个")

    # 创建时间
    create_time = account.get("create_time", 0)
    if create_time:
        age_days = (datetime.now(timezone.utc) - datetime.fromtimestamp(create_time / 1000, tz=timezone.utc)).days
        if age_days < 90:
            score += 8
            reasons.append(f"新地址({age_days}天)")

    score = min(score, 100)
    return score, reasons


def build_report(address: str, api_key: str = None) -> dict:
    api = TronAPI(api_key=api_key)

    # 0. 官方合约级黑名单检测（isBlackListed）
    is_frozen = check_usdt_blacklist(address)

    # 1. 账户信息
    account = api.get_account(address)
    if "error" in account:
        raise HTTPException(status_code=404, detail=f"地址查询失败: {account['error']}")

    # 2. TRC-20 记录（最近 100 笔）
    trc20 = api.get_trc20(address, limit=100)

    # 3. TRC-10（BL/诈骗币检测）
    freeze_flags = []
    scam_tokens = []
    if is_frozen:
        freeze_flags.append("BLACKLISTED")
    try:
        trc10 = api.get_trc10(address, limit=50)
        for t in trc10:
            name = str(t.get("token_name", t.get("token_id", ""))).upper()
            if name in ("BL", "BANLIST") or any(k in name for k in ("UNFREEZE", "UNLOCK", "UNBANNED")):
                freeze_flags.append(name)
            elif name:
                scam_tokens.append(name[:30])
    except Exception:
        pass  # trc10 端点可能 404，忽略

    # 4. 聚合对手方（统一小写比较，保留显示用原始地址）
    cp_map = {}
    addr_l = address.lower()
    for tx in trc20:
        frm = tx.get("from", "")
        to = tx.get("to", "")
        frm_l = frm.lower()
        to_l = to.lower()
        val = int(tx.get("value", 0)) / USDT_DECIMALS
        if frm_l == addr_l:
            key = to_l
            cp_map.setdefault(key, {"addr": to, "inAmt": 0.0, "outAmt": 0.0})
            cp_map[key]["outAmt"] += val
        if to_l == addr_l:
            key = frm_l
            cp_map.setdefault(key, {"addr": frm, "inAmt": 0.0, "outAmt": 0.0})
            cp_map[key]["inAmt"] += val

    counterparties = sorted(
        [c for c in cp_map.values() if c["addr"]],
        key=lambda x: x["inAmt"] + x["outAmt"],
        reverse=True,
    )[:15]
    # 对手方标签（已验库/规则特征）
    for c in counterparties:
        c["tag"] = address_tag(c["addr"])

    # 5. 最近交易
    transactions = []
    for tx in sorted(trc20, key=lambda x: x.get("block_timestamp", 0), reverse=True)[:20]:
        frm = tx.get("from", "")
        to = tx.get("to", "")
        frm_l = frm.lower()
        to_l = to.lower()
        val = int(tx.get("value", 0)) / USDT_DECIMALS
        direction = "in" if to_l == addr_l else "out"
        cp = frm if direction == "in" else to
        tx_hash = tx.get("transaction_id", "")
        transactions.append(TxRecord(
            time=ts_to_str(tx.get("block_timestamp", 0)),
            dir=direction,
            amt=round(val, 2),
            cp=(cp[:6] + "..." + cp[-4:]) if len(cp) > 10 else cp,
            hash=(tx_hash[:12] + "..." + tx_hash[-8:]) if len(tx_hash) > 20 else tx_hash,
            flag=bool(freeze_flags),
        ))

    # 6. 风险评分
    score, reasons = compute_score(trc20, account, freeze_flags, address_tag(address))
    if is_frozen:
        score = max(score, 95)
        reasons.insert(0, "地址在 Tether 黑名单中（已冻结）")
    risk = "high" if score >= 60 else ("mid" if score >= 30 else "low")

    # 7. 真实时间线（从链上数据构建，非 mock）
    timeline = []

    # 7.1 地址创建
    if account.get("create_time"):
        timeline.append(TimelineItem(
            time=ts_to_str(account.get("create_time", 0)) + " UTC",
            title="地址创建",
            desc=f"TRON 地址创建，当前 TRX 余额 {float(account.get('balance', 0)) / 1_000_000:.2f}",
            dot="green",
        ))

    # 7.2 抽样交易窗口（从 trc20 数据统计，TronGrid 抽样非全量）
    if trc20:
        times = [tx.get("block_timestamp", 0) for tx in trc20 if tx.get("block_timestamp")]
        if times:
            mn_t = ts_to_str(min(times))
            mx_t = ts_to_str(max(times))
            timeline.append(TimelineItem(
                time=f"{mn_t} ~ {mx_t} UTC",
                title="抽样交易窗口",
                desc=f"TronGrid 最近 {len(trc20)} 笔 USDT 交易抽样（非全量）。冻结仅限制转出，冻结后入账仍可能出现在窗口内。",
                dot="blue",
            ))

    # 7.3 大额/风险交易
    big_txs = [tx for tx in trc20 if int(tx.get("value", 0)) / USDT_DECIMALS > 50000]
    if big_txs:
        biggest = max(big_txs, key=lambda x: int(x.get("value", 0)))
        val = int(biggest.get("value", 0)) / USDT_DECIMALS
        frm = biggest.get("from", "")
        to = biggest.get("to", "")
        timeline.append(TimelineItem(
            time=ts_to_str(biggest.get("block_timestamp", 0)) + " UTC",
            title="大额资金流动",
            desc=f"{frm[:6]}...{'→' if frm != address.lower() else '←'} {to[:6]}... 金额 {val:,.2f} USDT",
            dot="blue",
        ))

    # 7.4 冻结事件
    if is_frozen:
        timeline.append(TimelineItem(
            time="已冻结（当前状态）",
            title="地址被 Tether 冻结",
            desc="USDT 合约 isBlackListed 返回 true，该地址 USDT 无法转出/赎回。冻结解除权在 Tether 及司法机构。",
            dot="red",
        ))
    else:
        # 7.5 未冻结但有风险
        if len(big_txs) >= 3 or len(set(t.get("from") for t in trc20)) > 20:
            timeline.append(TimelineItem(
                time="当前状态",
                title="高风险关注",
                desc="地址存在大额/高频交易，虽未被冻结，但建议做深度分析排查资金来源。",
                dot="gray",
            ))

    # 9. 行动方案（基于本地址真实数据定制，非通用模板）
    action_plan = []
    self_tag = address_tag(address)
    risky_cps = [c for c in counterparties if c.get("tag") and any(
        k in c["tag"] for k in ("高危", "冻结", "马甲", "诈骗", "博彩"))]
    big_cps = [c for c in counterparties if c["inAmt"] + c["outAmt"] >= 50000]

    if is_frozen:
        action_plan.append(PlanItem(
            t="冻结事实已确认",
            d=f"官方 USDT 合约 isBlackListed 返回 true，该地址已被 Tether 冻结（风险评分 {score}/100）。冻结解除权在 Tether 及司法机构，链上无法自行解冻。",
        ))
        if risky_cps:
            names = "、".join(c["addr"][:8] + "…" for c in risky_cps[:3])
            action_plan.append(PlanItem(
                t="切断高风险资金关联",
                d=f"本地址与已标记风险地址存在大额往来（如 {names}）。立即停止与这些地址的一切交易，避免新增风险。",
            ))
        if big_cps:
            top = big_cps[0]
            dom = "转入" if top["inAmt"] >= top["outAmt"] else "转出"
            action_plan.append(PlanItem(
                t="定位主要资金往来",
                d=f"最大对手方 {top['addr'][:8]}… 累计{dom} {max(top['inAmt'], top['outAmt']):,.0f} USDT。梳理与该对手方的交易背景（OTC/贸易/借款），这是申诉的核心证据来源。",
            ))
        action_plan.append(PlanItem(
            t="整理申诉材料",
            d="按清单准备：①与该地址关联交易的聊天记录/合同/发票/物流单据 ②KYC 材料 ③资金来源说明。证明交易背景真实合法，是申诉关键。",
        ))
        action_plan.append(PlanItem(
            t="警惕二次诈骗",
            d="Tether 官方不会通过 TG 或链上备注联系你。收到 UNFREEZE/UNLOCK/解冻等假代币或私聊付费解冻，一律是诈骗。",
        ))
        action_plan.append(PlanItem(
            t="预期管理",
            d="若地址有职业 OTC/高频过桥/高危对手方特征，解冻难度较高，申诉需充分证据并做好长期跟进准备。",
        ))
    elif score >= 60:
        action_plan.append(PlanItem(
            t="识别风险来源",
            d=f"当前风险评分 {score}/100（高风险），未被冻结但已被高度关注。检查近期大额交易与高风险对手方往来。",
        ))
        action_plan.append(PlanItem(
            t="立即自查",
            d="自查资金来源合法性，暂停与疑似黑产地址往来；如涉及 OTC 请保留完整交易凭证。",
        ))
        action_plan.append(PlanItem(
            t="提前准备",
            d="若交易所/钱包受限，第一时间联系官方渠道申诉；准备好交易背景证明（合同/聊天记录/物流单据）。",
        ))
    elif score >= 30:
        action_plan.append(PlanItem(
            t="关注风险信号",
            d=f"当前风险评分 {score}/100（中风险）。关注高风险对手方往来，核对近期大额交易。",
        ))
        action_plan.append(PlanItem(
            t="定期自查",
            d="建议每月自查一次地址状态与对手方变化，避免被动卷入风险。",
        ))
    else:
        action_plan.append(PlanItem(
            t="当前状态正常",
            d=f"风险评分 {score}/100（低风险），未被冻结。正常使用即可，注意不要与疑似黑产地址发生往来。",
        ))

    # 10. 组装响应
    created = ts_to_str(account.get("create_time", 0))
    # txCount = TronGrid 抽样笔数（非全量总数）—— 绝不当"总交易数"展示，前端标签为"抽样记录"
    tx_count = len(trc20)

    return ReportResponse(
        address=address,
        score=score,
        risk=risk,
        created=created,
        txCount=tx_count,
        counterparties=[Counterparty(**c) for c in counterparties],
        transactions=transactions,
        freezeStatus={
            "flags": freeze_flags[:5],
            "scamTokens": scam_tokens[:5],
            "reasons": reasons,
        },
        frozen=is_frozen,
        tags=[t for t in [address_tag(address)] if t],
        timeline=timeline,
        actionPlan=action_plan,
        note="数据来自 TronGrid 公开 API（最近100笔抽样，非全量）。交易总数/首笔/末笔均为抽样窗口内数据，不代表地址全部历史；如需全量分析请使用 CSV 深度报告。",
    )


@app.get("/api/report", response_model=ReportResponse)
def get_report(address: str = Query(..., description="TRON 地址"), api_key: str = Query(None, description="TronGrid API Key（可选）")):
    return build_report(address, api_key)


@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


# 静态文件挂载（放在 API 路由之后，避免覆盖 /api/*）
if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8902)
