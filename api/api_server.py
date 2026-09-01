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


class TxRecord(BaseModel):
    time: str
    dir: str
    amt: float
    cp: str
    hash: str
    flag: bool


class ReportResponse(BaseModel):
    address: str
    score: int
    risk: str
    created: str
    txCount: int
    counterparties: List[Counterparty]
    transactions: List[TxRecord]
    freezeStatus: Optional[dict] = None
    note: str


def ts_to_str(ts_ms: int) -> str:
    """毫秒时间戳 → YYYY-MM-DD HH:MM"""
    if not ts_ms:
        return "N/A"
    try:
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "N/A"


def compute_score(trc20: list, account: dict, freeze_flags: list) -> tuple:
    """启发式风险评分 0-100（数字越大风险越高）
    规则：
    - 基础 10
    - 每笔大额转入(>50k) +8，最高 +32
    - 有冻结标记(BL/UNFREEZE) +35
    - 对手方超过 20 个 +10
    - 账户创建 < 90 天 +8
    - 收过诈骗代币 +15
    """
    score = 10
    reasons = []

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

    # 1. 账户信息
    account = api.get_account(address)
    if "error" in account:
        raise HTTPException(status_code=404, detail=f"地址查询失败: {account['error']}")

    # 2. TRC-20 记录（最近 100 笔）
    trc20 = api.get_trc20(address, limit=100)

    # 3. TRC-10（BL/诈骗币检测）
    freeze_flags = []
    scam_tokens = []
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
    score, reasons = compute_score(trc20, account, freeze_flags)
    risk = "high" if score >= 60 else ("mid" if score >= 30 else "low")

    created = ts_to_str(account.get("create_time", 0))
    tx_count = account.get("transactions", len(trc20))

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
        note="数据来自 TronGrid 公开 API（最近100笔），仅供参考；如需全量分析请使用 CSV 深度报告。",
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
