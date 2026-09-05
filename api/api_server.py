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
import re
import tempfile
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from collections import defaultdict

# tron_api.py 在 scripts/ 目录
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
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
    "TTu3mqjHaUcqcEaX14s2t8VRzCkJkVMs3L": "冻结前重要上游资金对手方（非冻因）",
    "TChHAZ5QN6MdwRc61TqjFziWtgrY888888": "高危·疑似博彩/黑产",
    "TUZPztRsZQMUJVXQYKwEuwdGhzgTGjieuu": "中危·二次诈骗特征",
    "TRug7ZsKi7LjSg2n8A9a2CUFurE6u6HSwb": "中危·冻结标记来源",
    "TYAzzycMgo1s1f6fdAP48Bhbf2Z55ghtqa": "中危·能量租赁服务商",
    "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t": "USDT 合约",
}

# 已知案例确切冻结时间（深度报告 CSV 全量分析的 BL 标记，证据等级 E3 强关联；官方 isBlackListed 仅给当前状态）
# 格式: {"地址大写": "YYYY-MM-DD HH:MM:SS"}；时间戳来自 TronScan 导出 CSV 的 BL 标记行
# 2026-09-02 v2: 主数据源改为链上 USDT 合约 AddedBlackList 事件索引（sync_freeze_index.py 全量同步），
# 本表仅作索引未同步完成时的回退（链上事件证据等级更高：E1 链上事实）
FROZEN_AT = {
    "TJeh5fXJttbypanF2FMzgu42yqXnc5BuWw": "2026-08-08 21:20:36",  # 老板：链上 AddedBlackList @ 2026-08-08 21:20:36
    "TGC1t9MbJhx7uKYiQG4SzoafeFz3Jzg1JN": "2026-07-01 18:04:00",  # 朋友：链上 AddedBlackList @ 2026-07-01 18:04:00（修正 CSV 18:04:03）
}

# SQLite 冻结事件索引（sync_freeze_index.py 维护）：addr_hex(40) -> 冻结/解冻时间
FREEZE_DB = os.environ.get("FREEZE_DB", "/opt/usdt-forensics/freeze_index.db")

# base58 TRON 地址 → 20字节 hex（去 41 版本 + checksum）
_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def _base58_to_hex20(addr: str) -> str:
    """TRON base58 地址 → 20 字节 hex（40 字符小写），用于匹配合约事件 _user 参数"""
    n = 0
    for c in addr:
        n = n * 58 + _ALPHABET.index(c)
    raw = n.to_bytes(25, "big")
    return raw[1:21].hex()


def freeze_evidence(address: str) -> dict:
    """查询本地冻结事件索引（freeze_index.db，链上 AddedBlackList/RemovedBlackList 副本）。
    返回证据字典：
      found           首次 AddedBlackList 是否命中
      first_added_ts_ms 首次冻结事件毫秒时间戳
      first_added_time 首次冻结时间（YYYY-MM-DD HH:MM:SS UTC）
      tx_id           首次冻结证据交易（64 hex，可跳 TronScan）
      last_ev         该地址最后一条事件：AddedBlackList/RemovedBlackList/None（None=索引无记录）
    """
    out = {"found": False, "first_added_ts_ms": 0, "first_added_time": "", "tx_id": "", "last_ev": None}
    try:
        import sqlite3
        if os.path.exists(FREEZE_DB):
            hex20 = _base58_to_hex20(address)
            conn = sqlite3.connect(FREEZE_DB)
            row = conn.execute(
                "SELECT block_ts, tx_id FROM freeze_events WHERE addr_hex=? AND event_name='AddedBlackList' ORDER BY block_ts ASC LIMIT 1",
                (hex20,)).fetchone()
            if row:
                out["found"] = True
                out["first_added_ts_ms"] = int(row[0])
                out["first_added_time"] = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S") + " UTC"
                out["tx_id"] = str(row[1] or "")
            lrow = conn.execute(
                "SELECT event_name FROM freeze_events WHERE addr_hex=? ORDER BY block_ts DESC LIMIT 1",
                (hex20,)).fetchone()
            if lrow:
                out["last_ev"] = lrow[0]
            conn.close()
    except Exception:
        # 冻结索引不可用（DB 未同步/损坏）→ 返回空证据，不阻塞查询
        pass
    return out


def get_frozen_at(address: str) -> str:
    """返回地址确切冻结时间（YYYY-MM-DD HH:MM:SS UTC）或空串。
    顺序: SQLite 索引（链上 AddedBlackList E1）→ FROZEN_AT 回退（已知案例）"""
    # 1) 链上事件索引（对所有用户）
    ev = freeze_evidence(address)
    if ev["found"]:
        return ev["first_added_time"]
    # 2) 静态回退（索引未同步/未收录）
    fat = FROZEN_AT.get(address)
    if fat:
        return fat + " UTC"
    return ""


def get_freeze_index_updated() -> str:
    """返回冻结索引已同步的最新链上事件时间（YYYY-MM-DD HH:MM UTC）或空串。
    用于页面"数据新鲜度"展示（2026-09-05 GPT 建议）。"""
    try:
        import sqlite3
        if os.path.exists(FREEZE_DB):
            conn = sqlite3.connect(FREEZE_DB)
            row = conn.execute("SELECT MAX(block_ts) FROM freeze_events").fetchone()
            conn.close()
            if row and row[0]:
                return datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") + " UTC"
    except Exception:
        pass
    return ""


def cp_freeze_state(address: str):
    """查询对手方当前冻结状态（用 freeze_index 最后一条事件）。
    返回 (is_frozen_now: bool|None, last_added_ts_ms: int|None)。
    None = 索引无记录（未冻结过）；最后事件 AddedBlackList = 冻结中；RemovedBlackList = 已解冻。"""
    try:
        import sqlite3
        if os.path.exists(FREEZE_DB):
            hex20 = _base58_to_hex20(address)
            conn = sqlite3.connect(FREEZE_DB)
            row = conn.execute(
                "SELECT event_name, block_ts FROM freeze_events WHERE addr_hex=? ORDER BY block_ts DESC LIMIT 1",
                (hex20,)).fetchone()
            conn.close()
            if row:
                ev, ts = row
                return (ev == "AddedBlackList"), int(ts)
    except Exception:
        # 索引不可用 → 返回 (None, None)（未知），不视为已解冻/已冻结
        pass
    return None, None


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


def check_usdt_blacklist(address: str):
    """调用 USDT 合约 isBlackListed(address) 检测是否被 Tether 冻结（官方方法）。
    返回三态：True=冻结中 / False=官方确认未冻结 / None=实时状态未知（TronGrid 调用失败）。
    2026-09-06 GPT 审查修复：原 except 返回 False 造成假阴性（冻结地址显示未冻结）——
    调用方必须用 None 区分\"未知\"，失败时禁止报\"未冻结\"。"""
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
        # TronGrid 调用失败（429/网络超时）→ None=实时状态未知（假阴性比未知更危险：用户会误以为未冻结而继续使用）
        return None

app = FastAPI(title="USDT Freeze Forensics API", version="1.0.0")

# 埋点采集路由（复用 collector.py 已验逻辑；不新起进程）
try:
    from router_fastapi import router as ua_router
    app.include_router(ua_router)
except Exception:
    pass  # collector 不可用时不影响报告主功能

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
    flagNote: str = ""  # 交易级异常原因（三语，后端生成；flag=True 时必填）


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
    frozenAt: str = ""  # 确切冻结时间（AddedBlackList 链上事件；未冻结/未知为空），前端申诉材料取用
    trxBalance: float = 0.0  # 当前 TRX 余额（sun/1e6，2026-09-06 用户需求：查询报告显示余额）
    usdtBalance: float = 0.0  # 当前 USDT TRC-20 余额（1e6，冻结地址为冻结时冻结的存量，仅显示不可动）
    frozenAtTx: str = ""  # 冻结证据交易（AddedBlackList 事件的 64-hex tx_id，2026-09-06 证据链强化）
    frozenUnknown: bool = False  # True = 实时 isBlackListed 查询失败（TronGrid 波动），不得显示"未冻结"
    indexFrozen: bool = False  # frozenUnknown 时本地索引辅助：最后事件为 AddedBlackList
    frozenIndexAt: str = ""  # indexFrozen 时索引显示的首次冻结时间
    frozenIndexTx: str = ""  # indexFrozen 时索引显示的首次冻结证据交易
    dbUpdatedAt: str = ""  # 冻结索引已同步的最新链上事件时间（数据新鲜度展示）
    tags: List[str] = []
    timeline: List[TimelineItem] = []
    actionPlan: List[PlanItem] = []
    scoreBreakdown: List[dict] = []  # 评分依据：[{label, points}]，前端展示"为什么是这个分数"
    note: str


def ts_to_str(ts_ms: int) -> str:
    """毫秒时间戳 → YYYY-MM-DD HH:MM"""
    if not ts_ms:
        return "N/A"
    try:
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    except Exception:
        # 时间戳解析失败（非数值/超范围）→ 返回占位 N/A，前端显示"--"
        return "N/A"


# ===== TronScan 辅助信息（补充 TronGrid 缺失的链上活动口径，2026-09-01 教训：TE7jHEK 有 418 笔 TRX 但 0 笔 USDT） =====
def get_tronscan_activity(address: str) -> dict:
    """调用 TronScan 官方 API 获取链上活动统计（不替代 USDT 交易源）。
    用途：当 USDT 交易为 0 时，向用户解释"0 笔 USDT ≠ 地址无活动"——链上可能有 TRX/TRC-10 等其他交易。
    返回 {total_tx: 链上总交易数, balance: TRX 余额, trc20: 持有的 TRC-20 列表}
    """
    try:
        req = urllib.request.Request(
            "https://apilist.tronscanapi.com/api/account?address=" + address,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        return {
            "total_tx": data.get("totalTransactionCount", 0),
            "balance": data.get("balance", 0),
            "trc20": data.get("trc20token_balances") or [],
        }
    except Exception:
        # TronScan 辅助接口失败 → 返回空 dict（USDT 主数据不受影响）
        return {}


# ===== 后端文案三语（2026-09-02 修复：时间线/行动方案/评分依据曾全中文，越南语页面显示混乱） =====
def i18n_texts(lang: str = "zh") -> dict:
    """返回后端动态文案的三语字典（timeline/actionPlan/scoreBreakdown/note）。
    lang: zh / vi / en；未知语言回退 zh。"""
    lang = lang if lang in ("vi", "en") else "zh"
    T = {
        "zh": {
            "addr_created": "地址创建",
            "addr_created_desc": "TRON 地址创建，当前 TRX 余额 {bal:.2f}",
            "sample_window": "抽样交易窗口",
            "sample_window_desc": "TronGrid 最近 {n} 笔 USDT 交易抽样（非全量）。冻结仅限制转出，冻结后入账仍可能出现在窗口内。",
            "big_flow": "大额资金流动",
            "big_flow_desc": "{frm}...{arrow} {to}... 金额 {amt:,.2f} USDT",
            "frozen_now": "已冻结（当前状态）",
            "frozen_title": "地址被 Tether 冻结",
            "frozen_desc": "USDT 合约 isBlackListed 返回 true，该地址 USDT 无法转出/赎回。冻结解除权在 Tether 及司法机构。",
            "frozen_at_title": "冻结标记出现",
            "frozen_at_desc": "USDT 合约于 {time} 将该地址加入黑名单（AddedBlackList 链上事件），当前 isBlackListed 仍为 true。冻结解除权在 Tether 及司法机构。",
            "frozen_time_unknown": "（确切冻结时间未收录；可上传 CSV 生成深度报告交叉验证）",
            "flag_cp_frozen": "对手方已被 Tether 冻结",
            "flag_cp_tag": "对手方高风险标签：{tag}",
            "cur_status": "当前状态",
            "high_risk_attention": "高风险关注",
            "high_risk_attention_desc": "地址存在大额/高频交易，虽未被冻结，但建议做深度分析排查资金来源。",
            "plan_frozen_confirmed": "冻结事实已确认",
            "plan_frozen_confirmed_desc": "官方 USDT 合约 isBlackListed 返回 true，该地址已被 Tether 冻结（风险评分 {score}/100）。冻结解除权在 Tether 及司法机构，链上无法自行解冻。",
            "plan_cut_risky": "切断高风险资金关联",
            "plan_cut_risky_desc": "本地址与已标记风险地址存在大额往来（如 {names}）。立即停止与这些地址的一切交易，避免新增风险。",
            "plan_locate_main": "定位主要资金往来",
            "plan_locate_main_desc": "最大对手方 {addr}… 累计{dom} {amt:,.0f} USDT。梳理与该对手方的交易背景（OTC/贸易/借款），这是申诉的核心证据来源。",
            "dom_in": "转入",
            "dom_out": "转出",
            "plan_appeal_materials": "整理申诉材料",
            "plan_appeal_materials_desc": "按清单准备：①与该地址关联交易的聊天记录/合同/发票/物流单据 ②KYC 材料 ③资金来源说明。证明交易背景真实合法，是申诉关键。",
            "plan_warn_scam": "警惕二次诈骗",
            "plan_warn_scam_desc": "Tether 官方不会通过 TG 或链上备注联系你。收到 UNFREEZE/UNLOCK/解冻等假代币或私聊付费解冻，一律是诈骗。",
            "plan_expect": "预期管理",
            "plan_expect_desc": "若地址有职业 OTC/高频过桥/高危对手方特征，解冻难度较高，申诉需充分证据并做好长期跟进准备。",
            "plan_find_source": "识别风险来源",
            "plan_find_source_desc": "当前风险评分 {score}/100（高风险），未被冻结但已被高度关注。检查近期大额交易与高风险对手方往来。",
            "plan_self_check": "立即自查",
            "plan_self_check_desc": "自查资金来源合法性，暂停与疑似黑产地址往来；如涉及 OTC 请保留完整交易凭证。",
            "plan_prepare": "提前准备",
            "plan_prepare_desc": "若交易所/钱包受限，第一时间联系官方渠道申诉；准备好交易背景证明（合同/聊天记录/物流单据）。",
            "plan_addr_hint": "地址特征提示",
            "plan_addr_hint_desc": "该地址暂无 USDT 交易记录（TronGrid 最近100笔为空），风险来自地址特征：{tag}。此类吉祥号地址常见于博彩/黑产收款渠道，建议不要使用该地址接收/转出大额资金。",
            "plan_watch_signals": "关注风险信号",
            "plan_watch_signals_desc": "当前风险评分 {score}/100（中风险）。关注高风险对手方往来，核对近期大额交易。",
            "plan_periodic": "定期自查",
            "plan_periodic_desc": "建议每月自查一次地址状态与对手方变化，避免被动卷入风险。",
            "plan_normal": "当前状态正常",
            "plan_normal_desc": "风险评分 {score}/100（低风险），未被冻结。正常使用即可，注意不要与疑似黑产地址发生往来。",
            "note_sample": "数据来自 TronGrid 公开 API（最近100笔 USDT 抽样，非全量）。交易总数/首笔/末笔均为抽样窗口内数据，不代表地址全部历史；如需全量分析请使用 CSV 深度报告。",
            "note_no_usdt": "该地址 USDT (TRC-20) 交易为 0 笔；链上总交易 {n} 笔（TRX 转账/合约交互等，非 USDT）。USDT 冻结检测只统计 USDT，0 笔为真实状态。",
            "note_trc20_down": "TRC-20 交易查询暂不可用（链上服务波动），冻结状态与账户信息仍有效。请稍后重试，或上传 CSV 生成深度报告。",
            "note_window_full": "⚠️ 该地址交易活跃，最近 100 笔已占满抽样窗口，更早历史中可能存在未检查的关联（含与被冻结/高危地址的往来）。如需全量核查，请上传 TronScan CSV 生成深度报告，或查看 TronScan 完整交易记录。",
            "bd_base": "基础分",
            "bd_addr_feat": "地址特征：{tag}",
            "bd_big_in": "大额转入{n}笔",
            "bd_freeze_flag": "检测到冻结标记(BL/UNFREEZE)",
            "bd_cps": "对手方{n}个",
            "bd_new_addr": "新地址({n}天)",
            "bd_blacklisted": "地址在 Tether 黑名单中（已冻结）",
            "note_bl_unknown": "⚠️ 实时冻结状态暂时无法验证（链上服务波动）。以下结果基于本地索引与历史数据，请稍后重试；也可上传 TronScan CSV 生成深度报告核对。",
            "note_bl_unknown_idx": "⚠️ 实时冻结状态暂时无法验证（链上服务波动）。本地链上索引显示该地址曾于 {time} 被加入黑名单（AddedBlackList，索引同步至 {db}），请稍后重试以官方实时状态为准。",
            "tr_in": "收到",
            "tr_out": "转出",
            "tr_vs": "对手方 {cp}",
            "tl_causal_t": "时间先后 ≠ 因果关系",
            "tl_causal_d": "以上事件仅按链上时间顺序排列。时间上的先后不代表因果关系，本报告不构成法律意见。",
            "tl_unknown_t": "冻结状态待确认",
            "tl_unknown_d": "实时合约状态暂无法验证（链上服务波动）。未发现本地索引冻结记录；请稍后重试，或上传 CSV 生成深度报告核对。",
            "tl_unknown_idx_t": "冻结状态待确认（本地索引命中）",
            "tl_unknown_idx_d": "实时合约状态暂无法验证（链上服务波动）。本地链上索引显示该地址曾于 {time} 被加入黑名单（AddedBlackList，索引同步至 {db}），请以官方实时状态为准。",
        },
        "vi": {
            "addr_created": "Tạo địa chỉ",
            "addr_created_desc": "Tạo địa chỉ TRON, số dư TRX hiện tại {bal:.2f}",
            "sample_window": "Cửa sổ giao dịch mẫu",
            "sample_window_desc": "TronGrid {n} GD USDT gần nhất (mẫu, không đầy đủ). Đóng băng chỉ chặn chuyển ra; tiền vào sau khi đóng băng vẫn có thể xuất hiện.",
            "big_flow": "Dòng tiền lớn",
            "big_flow_desc": "{frm}...{arrow} {to}... Số tiền {amt:,.2f} USDT",
            "frozen_now": "Đã đóng băng (hiện tại)",
            "frozen_title": "Địa chỉ bị Tether đóng băng",
            "frozen_desc": "Hợp đồng USDT isBlackListed trả true, USDT của địa chỉ này không thể chuyển ra/chuộc. Quyền mở khóa thuộc Tether và cơ quan tư pháp.",
            "frozen_at_title": "Xuất hiện dấu đóng băng",
            "frozen_at_desc": "Hợp đồng USDT đưa địa chỉ này vào danh sách đen lúc {time} (sự kiện trên chuỗi AddedBlackList), isBlackListed hiện vẫn true. Quyền mở khóa thuộc Tether và cơ quan tư pháp.",
            "frozen_time_unknown": " (Chưa ghi nhận thời điểm đóng băng chính xác; có thể tải CSV để đối chiếu trong báo cáo chuyên sâu.)",
            "flag_cp_frozen": "Đối tác đã bị Tether đóng băng",
            "flag_cp_tag": "Đối tác có nhãn rủi ro cao: {tag}",
            "cur_status": "Trạng thái hiện tại",
            "high_risk_attention": "Chú ý rủi ro cao",
            "high_risk_attention_desc": "Địa chỉ có giao dịch lớn/tần suất cao, chưa bị đóng băng nhưng nên phân tích sâu nguồn tiền.",
            "plan_frozen_confirmed": "Xác nhận đóng băng",
            "plan_frozen_confirmed_desc": "Hợp đồng USDT isBlackListed trả true, địa chỉ đã bị Tether đóng băng (điểm rủi ro {score}/100). Quyền mở khóa thuộc Tether và cơ quan tư pháp.",
            "plan_cut_risky": "Cắt liên hệ rủi ro",
            "plan_cut_risky_desc": "Địa chỉ này có giao dịch lớn với các địa chỉ rủi ro đã đánh dấu (như {names}). Dừng mọi giao dịch với chúng ngay.",
            "plan_locate_main": "Xác định đối tác chính",
            "plan_locate_main_desc": "Đối tác lớn nhất {addr}… tổng {dom} {amt:,.0f} USDT. Làm rõ bối cảnh giao dịch (OTC/thương mại/vay) - bằng chứng cốt lõi khi khiếu nại.",
            "dom_in": "nhận",
            "dom_out": "chuyển",
            "plan_appeal_materials": "Chuẩn bị hồ sơ khiếu nại",
            "plan_appeal_materials_desc": "Chuẩn bị: ①tin nhắn/hợp đồng/hóa đơn/chứng từ vận chuyển ②KYC ③giải trình nguồn tiền. Chứng minh giao dịch hợp pháp là chìa khóa.",
            "plan_warn_scam": "Cảnh giác lừa đảo thứ cấp",
            "plan_warn_scam_desc": "Tether không liên hệ qua TG hay ghi chú trên chuỗi. UNFREEZE/UNLOCK/giải đóng băng giả hoặc nhắn tin đòi phí là lừa đảo.",
            "plan_expect": "Quản lý kỳ vọng",
            "plan_expect_desc": "Nếu địa chỉ có đặc điểm OTC chuyên nghiệp/trung chuyển nhanh/đối tác rủi ro, khả năng mở khóa thấp hơn, cần bằng chứng đầy đủ và kiên trì.",
            "plan_find_source": "Xác định nguồn rủi ro",
            "plan_find_source_desc": "Điểm rủi ro {score}/100 (cao), chưa bị đóng băng nhưng đang bị chú ý. Kiểm tra giao dịch lớn và đối tác rủi ro gần đây.",
            "plan_self_check": "Tự kiểm tra ngay",
            "plan_self_check_desc": "Kiểm tra tính hợp pháp nguồn tiền, tạm dừng giao dịch với địa chỉ đen; nếu OTC hãy giữ chứng từ đầy đủ.",
            "plan_prepare": "Chuẩn bị trước",
            "plan_prepare_desc": "Nếu sàn/ví hạn chế, liên hệ kênh chính thức ngay; chuẩn bị chứng minh giao dịch (hợp đồng/tin nhắn/chứng từ).",
            "plan_addr_hint": "Gợi ý đặc điểm địa chỉ",
            "plan_addr_hint_desc": "Địa chỉ chưa có giao dịch USDT (TronGrid 100 GD gần nhất trống), rủi ro từ đặc điểm: {tag}. Số đẹp thường dùng cho kênh cờ bạc/rửa tiền, không nên nhận/chuyển tiền lớn.",
            "plan_watch_signals": "Theo dõi tín hiệu rủi ro",
            "plan_watch_signals_desc": "Điểm rủi ro {score}/100 (trung bình). Theo dõi đối tác rủi ro cao, đối chiếu giao dịch lớn gần đây.",
            "plan_periodic": "Tự kiểm tra định kỳ",
            "plan_periodic_desc": "Kiểm tra trạng thái địa chỉ và đối tác mỗi tháng, tránh bị cuốn vào rủi ro.",
            "plan_normal": "Trạng thái bình thường",
            "plan_normal_desc": "Điểm rủi ro {score}/100 (thấp), chưa bị đóng băng. Sử dụng bình thường, tránh giao dịch với địa chỉ đen.",
            "note_sample": "Dữ liệu từ TronGrid công khai (mẫu 100 GD USDT gần nhất, không đầy đủ). Tổng/đầu/cuối chỉ là cửa sổ mẫu; cần phân tích đầy đủ dùng báo cáo chuyên sâu (CSV).",
            "note_no_usdt": "Địa chỉ có 0 giao dịch USDT (TRC-20); tổng giao dịch trên chuỗi {n} (TRX/hợp đồng, không phải USDT). Công cụ chỉ thống kê USDT, 0 là trạng thái thật.",
            "note_trc20_down": "Truy vấn giao dịch TRC-20 tạm không khả dụng (dịch vụ chuỗi dao động), trạng thái đóng băng và thông tin tài khoản vẫn có hiệu lực. Vui lòng thử lại sau, hoặc tải CSV để tạo báo cáo chuyên sâu.",
            "note_window_full": "⚠️ Địa chỉ này giao dịch sôi động, 100 GD gần nhất đã lấp đầy cửa sổ mẫu; trong lịch sử sớm hơn có thể tồn tại mối liên hệ chưa được kiểm tra (kể cả với địa chỉ bị đóng băng/rủi ro cao). Để rà soát đầy đủ, vui lòng tải CSV TronScan tạo báo cáo chuyên sâu hoặc xem toàn bộ giao dịch trên TronScan.",
            "bd_base": "Điểm cơ bản",
            "bd_addr_feat": "Đặc điểm địa chỉ: {tag}",
            "bd_big_in": "Chuyển vào lớn {n} GD",
            "bd_freeze_flag": "Phát hiện dấu hiệu đóng băng (BL/UNFREEZE)",
            "bd_cps": "{n} đối tác",
            "bd_new_addr": "Địa chỉ mới ({n} ngày)",
            "bd_blacklisted": "Địa chỉ trong danh sách đen Tether (đã đóng băng)",
            "note_bl_unknown": "⚠️ Trạng thái đóng băng theo thời gian thực tạm thời không xác minh được (dịch vụ mạng lưới dao động). Kết quả dưới đây dựa trên chỉ mục cục bộ và dữ liệu lịch sử, vui lòng thử lại sau; hoặc tải CSV từ TronScan để tạo báo cáo chuyên sâu đối chiếu.",
            "note_bl_unknown_idx": "⚠️ Trạng thái đóng băng theo thời gian thực tạm thời không xác minh được (dịch vụ mạng lưới dao động). Chỉ mục cục bộ cho thấy địa chỉ này từng bị thêm vào danh sách đen lúc {time} (AddedBlackList, chỉ mục cập nhật đến {db}), vui lòng thử lại sau để xác nhận theo trạng thái chính thức.",
            "tr_in": "Nhận",
            "tr_out": "Gửi",
            "tr_vs": "Đối tác {cp}",
            "tl_causal_t": "Thứ tự thời gian ≠ quan hệ nhân quả",
            "tl_causal_d": "Các sự kiện trên chỉ được sắp xếp theo thời gian trên chuỗi. Thứ tự thời gian không đồng nghĩa với quan hệ nhân quả, báo cáo này không phải là ý kiến pháp lý.",
            "tl_unknown_t": "Trạng thái đóng băng cần xác nhận",
            "tl_unknown_d": "Trạng thái hợp đồng thời gian thực tạm thời không xác minh được (dịch vụ mạng lưới dao động). Không tìm thấy ghi nhận đóng băng trong chỉ mục cục bộ; vui lòng thử lại sau, hoặc tải CSV để tạo báo cáo chuyên sâu đối chiếu.",
            "tl_unknown_idx_t": "Trạng thái đóng băng cần xác nhận (chỉ mục cục bộ trúng)",
            "tl_unknown_idx_d": "Trạng thái hợp đồng thời gian thực tạm thời không xác minh được (dịch vụ mạng lưới dao động). Chỉ mục cục bộ cho thấy địa chỉ này từng bị thêm vào danh sách đen lúc {time} (AddedBlackList, chỉ mục cập nhật đến {db}), vui lòng lấy trạng thái chính thức khi thử lại.",
        },
        "en": {
            "addr_created": "Address Created",
            "addr_created_desc": "TRON address created, current TRX balance {bal:.2f}",
            "sample_window": "Sampled Trading Window",
            "sample_window_desc": "TronGrid recent {n} USDT transactions (sampled, not full). Freeze only blocks outgoing; incoming after freeze may still appear.",
            "big_flow": "Large Fund Movement",
            "big_flow_desc": "{frm}...{arrow} {to}... Amount {amt:,.2f} USDT",
            "frozen_now": "Frozen (current)",
            "frozen_title": "Address frozen by Tether",
            "frozen_desc": "USDT contract isBlackListed returned true; USDT cannot be transferred out/redeemed. Unfreeze authority rests with Tether and judicial bodies.",
            "frozen_at_title": "Freeze Flag Appeared",
            "frozen_at_desc": "USDT contract added this address to the blacklist at {time} (on-chain AddedBlackList event); isBlackListed is still true. Unfreeze authority rests with Tether and judicial bodies.",
            "frozen_time_unknown": " (Exact freeze time not recorded; upload a CSV for cross-checking in the deep report.)",
            "flag_cp_frozen": "Counterparty is frozen by Tether",
            "flag_cp_tag": "Counterparty high-risk tag: {tag}",
            "cur_status": "Current Status",
            "high_risk_attention": "High-risk Attention",
            "high_risk_attention_desc": "Address shows large/high-frequency transactions; not frozen, but deep source analysis is recommended.",
            "plan_frozen_confirmed": "Freeze Confirmed",
            "plan_frozen_confirmed_desc": "USDT contract isBlackListed returned true; address frozen by Tether (risk score {score}/100). Unfreeze authority rests with Tether and judicial bodies.",
            "plan_cut_risky": "Cut High-risk Connections",
            "plan_cut_risky_desc": "This address has large dealings with flagged risk addresses (e.g. {names}). Stop all transactions with them immediately.",
            "plan_locate_main": "Identify Main Counterparty",
            "plan_locate_main_desc": "Largest counterparty {addr}… total {dom} {amt:,.0f} USDT. Clarify transaction background (OTC/trade/loan) - core evidence for appeal.",
            "dom_in": "in",
            "dom_out": "out",
            "plan_appeal_materials": "Prepare Appeal Materials",
            "plan_appeal_materials_desc": "Prepare: ①chat/contract/invoice/shipping docs for related transactions ②KYC ③fund source statement. Proving legitimate background is key.",
            "plan_warn_scam": "Beware Secondary Scams",
            "plan_warn_scam_desc": "Tether never contacts via TG or on-chain notes. UNFREEZE/UNLOCK/fake tokens or paid-unfreeze DMs are scams.",
            "plan_expect": "Expectation Management",
            "plan_expect_desc": "If address shows professional OTC/high-frequency relay/high-risk counterparty traits, unfreeze is harder; appeal needs solid evidence and patience.",
            "plan_find_source": "Identify Risk Source",
            "plan_find_source_desc": "Risk score {score}/100 (high), not frozen but under scrutiny. Review recent large transactions and high-risk counterparties.",
            "plan_self_check": "Self-check Now",
            "plan_self_check_desc": "Verify fund source legality, pause dealings with suspected black-market addresses; keep full OTC records.",
            "plan_prepare": "Prepare Ahead",
            "plan_prepare_desc": "If exchange/wallet restricts you, contact official channels immediately; prepare transaction background proof.",
            "plan_addr_hint": "Address Trait Notice",
            "plan_addr_hint_desc": "No USDT transactions found (TronGrid recent 100 empty); risk comes from address trait: {tag}. Lucky-number addresses are common in gambling/black-market channels; avoid large funds on this address.",
            "plan_watch_signals": "Monitor Risk Signals",
            "plan_watch_signals_desc": "Risk score {score}/100 (medium). Monitor high-risk counterparties and verify recent large transactions.",
            "plan_periodic": "Periodic Self-check",
            "plan_periodic_desc": "Re-check address status and counterparties monthly to avoid passive risk involvement.",
            "plan_normal": "Normal Status",
            "plan_normal_desc": "Risk score {score}/100 (low), not frozen. Normal use; just avoid dealings with suspected black-market addresses.",
            "note_sample": "Data from TronGrid public API (sampled last 100 USDT, not full). Totals/first/last are sampled-window only; use CSV deep report for full analysis.",
            "note_no_usdt": "This address has 0 USDT (TRC-20) transactions; on-chain total {n} (TRX/contract interactions, not USDT). Tool only counts USDT; 0 is the true state.",
            "note_trc20_down": "TRC-20 transaction query is temporarily unavailable (chain service fluctuation); frozen status and account info remain valid. Please retry shortly, or upload a CSV for a deep report.",
            "note_window_full": "⚠️ This address is actively trading and the 100-tx sample window is full — earlier history may contain unchecked links (including to frozen/high-risk addresses). For a full check, upload a TronScan CSV for a deep report, or view the complete history on TronScan.",
            "bd_base": "Base Score",
            "bd_addr_feat": "Address trait: {tag}",
            "bd_big_in": "Large inflow x{n}",
            "bd_freeze_flag": "Freeze flag detected (BL/UNFREEZE)",
            "bd_cps": "{n} counterparties",
            "bd_new_addr": "New address ({n} days)",
            "bd_blacklisted": "Address on Tether blacklist (frozen)",
            "note_bl_unknown": "⚠️ Real-time frozen status is temporarily unverifiable (chain service fluctuation). Results below are based on the local index and historical data — please retry shortly; or upload a TronScan CSV for a deep cross-check report.",
            "note_bl_unknown_idx": "⚠️ Real-time frozen status is temporarily unverifiable (chain service fluctuation). The local on-chain index shows this address was blacklisted at {time} (AddedBlackList, index synced to {db}) — please retry to confirm with the official real-time status.",
            "tr_in": "Received",
            "tr_out": "Sent",
            "tr_vs": "Counterparty {cp}",
            "tl_causal_t": "Time order ≠ causation",
            "tl_causal_d": "Events above are ordered by on-chain time only. Chronological order does not imply causation; this report is not legal advice.",
            "tl_unknown_t": "Frozen status pending",
            "tl_unknown_d": "Real-time contract status is temporarily unverifiable (chain service fluctuation). No freeze record found in the local index — please retry shortly, or upload a CSV for a deep cross-check report.",
            "tl_unknown_idx_t": "Frozen status pending (local index hit)",
            "tl_unknown_idx_d": "Real-time contract status is temporarily unverifiable (chain service fluctuation). The local on-chain index shows this address was blacklisted at {time} (AddedBlackList, index synced to {db}) — please confirm with the official real-time status when retrying.",
        },
    }
    return T[lang]


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
    返回 (score, breakdown)：breakdown 为 [{label, points}] 供前端展示"为什么是这个分数"。
    """
    breakdown = [{"label": "基础分", "points": 10}]
    score = 10

    # 吉祥号/风险特征标签（如 888888 结尾 → 疑似博彩/黑产热钱包）
    if addr_tag and any(k in addr_tag for k in ("疑似", "高危", "博彩", "马甲", "诈骗")):
        score += 25
        breakdown.append({"label": f"地址特征：{addr_tag}", "points": 25})

    # 大额转入
    big_in = 0
    for tx in trc20:
        val = int(tx.get("value", 0)) / USDT_DECIMALS
        if val > 50000:
            big_in += 1
    add_big = min(big_in, 4) * 8
    if add_big:
        score += add_big
        breakdown.append({"label": f"大额转入{big_in}笔", "points": add_big})

    # 冻结标记
    if freeze_flags:
        score += 35
        breakdown.append({"label": "检测到冻结标记(BL/UNFREEZE)", "points": 35})

    # 对手方数量
    cps = set()
    for tx in trc20:
        cps.add(tx.get("from", ""))
        cps.add(tx.get("to", ""))
    cps.discard("")
    if len(cps) > 20:
        score += 10
        breakdown.append({"label": f"对手方{len(cps)}个", "points": 10})

    # 创建时间
    create_time = account.get("create_time", 0)
    if create_time:
        age_days = (datetime.now(timezone.utc) - datetime.fromtimestamp(create_time / 1000, tz=timezone.utc)).days
        if age_days < 90:
            score += 8
            breakdown.append({"label": f"新地址({age_days}天)", "points": 8})

    score = min(score, 100)
    return score, breakdown


def build_report(address: str, api_key: str = None, lang: str = "zh") -> dict:
    api = TronAPI(api_key=api_key)
    T = i18n_texts(lang)

    # 0. 官方合约级黑名单检测（isBlackListed）— 三态：True 冻结 / False 官方确认未冻结 / None 实时未知（TronGrid 失败）
    # 2026-09-06 GPT 审查：网络失败不再静默当"未冻结"（假阴性）；frozenUnknown 由前端显示琥珀警示
    _bl = check_usdt_blacklist(address)
    bl_unknown = _bl is None
    is_frozen = _bl is True
    # 冻结证据（本地链上事件索引：首次 AddedBlackList 时间 + 证据交易 tx_id）——全查询共用
    ev = freeze_evidence(address)

    # 1. 账户信息
    account = api.get_account(address)
    if "error" in account:
        raise HTTPException(status_code=404, detail=f"地址查询失败: {account['error']}")
    # 当前余额（TRX = balance sun/1e6；USDT = account.trc20 中 USDT 合约余额/1e6）
    # 2026-09-06 用户需求：报告显示地址当前余额（冻结地址的 USDT 为冻结存量，仅展示不可动）
    trx_balance = 0.0
    usdt_balance = 0.0
    try:
        trx_balance = float(account.get("balance", 0)) / 1_000_000
        for _t in account.get("trc20", []) or []:
            if USDT_CONTRACT in _t:
                usdt_balance = float(_t[USDT_CONTRACT]) / 1_000_000
                break
    except (TypeError, ValueError):
        pass  # 余额解析失败不阻塞报告（保持 0）

    # 2. TRC-20 记录（最近 100 笔 USDT；TronGrid 为权威 USDT 交易源）
    # 2026-09-01 教训：TE7jHEK 有 418 笔链上交易但全部是 TRX(contractType=2)，USDT=0 是真实状态
    # —— 不要用 TronScan transfers 回退（其 address 参数不按地址过滤，会混入无关交易）
    # 2026-09-05 审查：TronGrid 故障时降级返回空（附 note 说明），不整体 500
    trc20 = []
    trc20_error = False
    try:
        trc20 = api.get_trc20(address, limit=100)
    except Exception:
        trc20 = []
        trc20_error = True  # 查询失败（区别于真 0 笔），note 单独提示
    chain_activity = {}
    if not trc20 and not trc20_error:
        # USDT 0 笔时，补充链上活动口径（TRX/TRC-10 等），解释"0 笔 USDT ≠ 地址无活动"
        chain_activity = get_tronscan_activity(address)

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

    # 5. 最近交易（交易级异常标记：flag = 对手方被冻结 或 对手方高危标签，附 flagNote 原因）
    # 2026-09-02 修正：旧逻辑 flag=bool(freeze_flags) 把"地址被冻结"连坐到每一笔交易，
    # 连 10 USDT 小额都标"涉案"，且 TTu3mq(非冻因) 被误标——违反交易级依据与合规口径
    _HOT_TAG_KWS = ("高危", "博彩", "诈骗", "马甲", "黑产")  # 注意不含"冻结"（"冻结前重要上游资金对手方（非冻因）"不触发）
    transactions = []
    for tx in sorted(trc20, key=lambda x: x.get("block_timestamp", 0), reverse=True)[:20]:
        frm = tx.get("from", "")
        to = tx.get("to", "")
        frm_l = frm.lower()
        to_l = to.lower()
        val = int(tx.get("value", 0)) / USDT_DECIMALS
        direction = "in" if to_l == addr_l else "out"
        cp_full = frm if direction == "in" else to
        tx_hash = tx.get("transaction_id", "")
        # 交易级判定
        flag = False
        flag_note = ""
        cp_tag = address_tag(cp_full)
        if cp_tag and any(k in cp_tag for k in _HOT_TAG_KWS):
            flag = True
            flag_note = T["flag_cp_tag"].format(tag=cp_tag)
        else:
            cp_frozen, _ = cp_freeze_state(cp_full)
            if cp_frozen:
                flag = True
                flag_note = T["flag_cp_frozen"]
        transactions.append(TxRecord(
            time=ts_to_str(tx.get("block_timestamp", 0)),
            dir=direction,
            amt=round(val, 2),
            cp=(cp_full[:6] + "..." + cp_full[-4:]) if len(cp_full) > 10 else cp_full,
            hash=(tx_hash[:12] + "..." + tx_hash[-8:]) if len(tx_hash) > 20 else tx_hash,
            flag=flag,
            flagNote=flag_note,
        ))

    # 6. 风险评分
    score, score_breakdown = compute_score(trc20, account, freeze_flags, address_tag(address))
    # 评分依据标签本地化（compute_score 内部为中文，按 lang 翻译）
    if lang != "zh":
        def _bd_label(label: str) -> str:
            if label == "基础分":
                return T["bd_base"]
            if label.startswith("地址特征："):
                return T["bd_addr_feat"].format(tag=label.split("：", 1)[1])
            if label.startswith("大额转入") and label.endswith("笔"):
                return T["bd_big_in"].format(n=label[4:-1])
            if label == "检测到冻结标记(BL/UNFREEZE)":
                return T["bd_freeze_flag"]
            if label.startswith("对手方") and label.endswith("个"):
                return T["bd_cps"].format(n=label[3:-1])
            if label.startswith("新地址(") and label.endswith("天)"):
                return T["bd_new_addr"].format(n=label[4:-2])
            return label
        score_breakdown = [{"label": _bd_label(b["label"]), "points": b["points"]} for b in score_breakdown]
    if is_frozen:
        score = max(score, 95)
        score_breakdown.insert(0, {"label": T["bd_blacklisted"], "points": score})
    risk = "high" if score >= 60 else ("mid" if score >= 30 else "low")

    # 7. 真实时间线（从链上数据构建，非 mock）
    timeline = []

    # 7.1 地址创建
    if account.get("create_time"):
        timeline.append(TimelineItem(
            time=ts_to_str(account.get("create_time", 0)) + " UTC",
            title=T["addr_created"],
            desc=T["addr_created_desc"].format(bal=float(account.get('balance', 0)) / 1_000_000),
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
                title=T["sample_window"],
                desc=T["sample_window_desc"].format(n=len(trc20)),
                dot="blue",
            ))

    # 7.3 大额/风险交易
    big_txs = [tx for tx in trc20 if int(tx.get("value", 0)) / USDT_DECIMALS > 50000]
    if big_txs:
        biggest = max(big_txs, key=lambda x: int(x.get("value", 0)))
        val = int(biggest.get("value", 0)) / USDT_DECIMALS
        frm = biggest.get("from", "")
        to = biggest.get("to", "")
        arrow = "→" if frm != address.lower() else "←"
        timeline.append(TimelineItem(
            time=ts_to_str(biggest.get("block_timestamp", 0)) + " UTC",
            title=T["big_flow"],
            desc=T["big_flow_desc"].format(frm=frm[:6], arrow=arrow, to=to[:6], amt=val),
            dot="blue",
        ))

    # 7.4 冻结事件（确切冻结时间：链上 USDT 合约 AddedBlackList 事件索引 E1 → FROZEN_AT 回退）
    # 2026-09-02 v2: get_frozen_at 对所有用户查 SQLite 冻结索引（sync_freeze_index.py 全量同步 AddedBlackList）
    # 注意: 不能用 addr_l.upper() —— TRON base58 地址大小写敏感，lower()/upper() 会改变字符
    if is_frozen:
        fat_ts = get_frozen_at(address)
        if fat_ts:
            # 7.4a 冻结前最近交易（抽样窗口内 ≤ 冻结时间；证据展示，禁止因果推断——铁律 #8）
            pre_txs = []
            if ev.get("found"):
                pre_txs = [tx for tx in trc20 if tx.get("block_timestamp") and int(tx.get("block_timestamp", 0)) <= ev["first_added_ts_ms"]]
                pre_txs.sort(key=lambda x: int(x.get("block_timestamp", 0)), reverse=True)
            for tx in pre_txs[:5]:
                val = int(tx.get("value", 0)) / USDT_DECIMALS
                frm = str(tx.get("from", ""))
                to = str(tx.get("to", ""))
                is_in = to.lower() == address.lower()
                cp_full = frm if is_in else to
                cp_disp = (cp_full[:6] + "..." + cp_full[-4:]) if len(cp_full) > 10 else cp_full
                txh = str(tx.get("transaction_id") or tx.get("hash") or "")
                txh_disp = (txh[:12] + "..." + txh[-8:]) if len(txh) > 20 else txh
                timeline.append(TimelineItem(
                    time=ts_to_str(int(tx.get("block_timestamp", 0))) + " UTC",
                    title=(T["tr_in"] if is_in else T["tr_out"]) + " {:,.2f} USDT".format(val),
                    desc=T["tr_vs"].format(cp=cp_disp) + (" · " + txh_disp if txh_disp else ""),
                    dot="blue",
                ))
            timeline.append(TimelineItem(
                time=fat_ts,
                title=T["frozen_at_title"],
                desc=T["frozen_at_desc"].format(time=fat_ts),
                dot="red",
            ))
            # 7.4b 合规警示：时间先后 ≠ 因果（铁律 #8）
            timeline.append(TimelineItem(
                time="",
                title=T["tl_causal_t"],
                desc=T["tl_causal_d"],
                dot="gray",
            ))
        else:
            timeline.append(TimelineItem(
                time=T["frozen_now"],
                title=T["frozen_title"],
                desc=T["frozen_desc"] + T["frozen_time_unknown"],
                dot="red",
            ))
    elif bl_unknown:
        # 7.5x 实时合约状态未知（TronGrid 波动）——不显示"未冻结"；本地索引辅助提示
        idx_hit = ev.get("found") and ev.get("last_ev") == "AddedBlackList"
        if idx_hit:
            timeline.append(TimelineItem(
                time=ev["first_added_time"],
                title=T["tl_unknown_idx_t"],
                desc=T["tl_unknown_idx_d"].format(time=ev["first_added_time"], db=get_freeze_index_updated() or "--"),
                dot="gray",
            ))
        else:
            timeline.append(TimelineItem(
                time=T["cur_status"],
                title=T["tl_unknown_t"],
                desc=T["tl_unknown_d"],
                dot="gray",
            ))
    else:
        # 7.5 未冻结但有风险
        if len(big_txs) >= 3 or len(set(t.get("from") for t in trc20)) > 20:
            timeline.append(TimelineItem(
                time=T["cur_status"],
                title=T["high_risk_attention"],
                desc=T["high_risk_attention_desc"],
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
            t=T["plan_frozen_confirmed"],
            d=T["plan_frozen_confirmed_desc"].format(score=score),
        ))
        if risky_cps:
            names = ("、" if lang == "zh" else ", ").join(c["addr"][:8] + "…" for c in risky_cps[:3])
            action_plan.append(PlanItem(
                t=T["plan_cut_risky"],
                d=T["plan_cut_risky_desc"].format(names=names),
            ))
        if big_cps:
            top = big_cps[0]
            dom = T["dom_in"] if top["inAmt"] >= top["outAmt"] else T["dom_out"]
            action_plan.append(PlanItem(
                t=T["plan_locate_main"],
                d=T["plan_locate_main_desc"].format(addr=top["addr"][:8], dom=dom, amt=max(top["inAmt"], top["outAmt"])),
            ))
        action_plan.append(PlanItem(
            t=T["plan_appeal_materials"],
            d=T["plan_appeal_materials_desc"],
        ))
        action_plan.append(PlanItem(
            t=T["plan_warn_scam"],
            d=T["plan_warn_scam_desc"],
        ))
        action_plan.append(PlanItem(
            t=T["plan_expect"],
            d=T["plan_expect_desc"],
        ))
    elif score >= 60:
        action_plan.append(PlanItem(
            t=T["plan_find_source"],
            d=T["plan_find_source_desc"].format(score=score),
        ))
        action_plan.append(PlanItem(
            t=T["plan_self_check"],
            d=T["plan_self_check_desc"],
        ))
        action_plan.append(PlanItem(
            t=T["plan_prepare"],
            d=T["plan_prepare_desc"],
        ))
    elif score >= 30:
        if not trc20 and self_tag:
            action_plan.append(PlanItem(
                t=T["plan_addr_hint"],
                d=T["plan_addr_hint_desc"].format(tag=self_tag),
            ))
        else:
            action_plan.append(PlanItem(
                t=T["plan_watch_signals"],
                d=T["plan_watch_signals_desc"].format(score=score),
            ))
        action_plan.append(PlanItem(
            t=T["plan_periodic"],
            d=T["plan_periodic_desc"],
        ))
    else:
        action_plan.append(PlanItem(
            t=T["plan_normal"],
            d=T["plan_normal_desc"].format(score=score),
        ))

    # 10. 组装响应
    created = ts_to_str(account.get("create_time", 0))
    # txCount = USDT 抽样笔数（非全量总数；TronGrid 权威 USDT 源，0 就是真 0）
    tx_count = len(trc20)

    note = T["note_sample"]
    if bl_unknown:
        # 实时冻结状态未知（最高优先级提示，2026-09-06）——不得让用户误读为"未冻结"
        if ev.get("found") and ev.get("last_ev") == "AddedBlackList":
            note = T["note_bl_unknown_idx"].format(time=ev["first_added_time"], db=get_freeze_index_updated() or "--")
        else:
            note = T["note_bl_unknown"]
    elif trc20_error:
        # TRC-20 查询失败（非真 0 笔）：覆盖 note 说明降级状态（2026-09-05 审查）
        note = T["note_trc20_down"]
    elif not trc20 and chain_activity.get("total_tx"):
        note = T["note_no_usdt"].format(n=chain_activity.get("total_tx"))

    # 2026-09-06 方案1（用户拍板）：抽样窗口被占满（=必有更早历史未被检查）→ 追加引导提示
    # 防止活跃地址（如 TDtyzAk 3000+ 笔/高频）显示"看起来干净"而实际更早存在被冻/高危往来
    if trc20 and len(trc20) >= 100:
        note += " " + T["note_window_full"]

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
            "reasons": [b["label"] for b in score_breakdown],
        },
        frozen=is_frozen,
        frozenAt=(get_frozen_at(address) if is_frozen else ""),
        trxBalance=trx_balance,
        usdtBalance=usdt_balance,
        frozenAtTx=(ev.get("tx_id", "") if (is_frozen and ev.get("found")) else ""),
        frozenUnknown=bl_unknown,
        indexFrozen=bool(bl_unknown and ev.get("found") and ev.get("last_ev") == "AddedBlackList"),
        frozenIndexAt=(ev["first_added_time"] if (bl_unknown and ev.get("found") and ev.get("last_ev") == "AddedBlackList") else ""),
        frozenIndexTx=(ev.get("tx_id", "") if (bl_unknown and ev.get("found") and ev.get("last_ev") == "AddedBlackList") else ""),
        dbUpdatedAt=get_freeze_index_updated(),
        tags=[t for t in [address_tag(address)] if t],
        timeline=timeline,
        actionPlan=action_plan,
        scoreBreakdown=score_breakdown,
        note=note,
    )


@app.get("/api/report", response_model=ReportResponse)
def get_report(address: str = Query(..., description="TRON 地址"),
               api_key: str = Query(None, description="TronGrid API Key（可选）"),
               lang: str = Query("zh", description="响应文案语言: zh/vi/en")):
    return build_report(address, api_key, lang=lang)


@app.get("/api/health")
def health():
    idx_n = 0
    idx_upd = ""
    try:
        import sqlite3
        if os.path.exists(FREEZE_DB):
            conn = sqlite3.connect(FREEZE_DB)
            row = conn.execute("SELECT COUNT(*), MAX(block_ts) FROM freeze_events").fetchone()
            conn.close()
            if row and row[0]:
                idx_n = int(row[0])
                idx_upd = datetime.fromtimestamp(int(row[1]) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") + " UTC"
    except Exception:
        pass
    # index_records/index_updated：双节点数据版本/条数/同步时间（2026-09-06 GPT 建议，运维对比广州 vs 雅加达）
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat(),
            "index_records": idx_n, "index_updated": idx_upd}


# ===== 深度报告（CSV 全量分析，2026-09-01 上线：免费查询 + 上传 CSV 出深度报告） =====
# 复用 scripts/csv_analyzer.py 的 CsvAnalyzer（全量统计）+ report_generator.py 的 Markdown 生成
from fastapi import UploadFile, File

MAX_CSV_BYTES = 10 * 1024 * 1024  # 10MB


def _md_escape(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def _deep_forensics(raw: bytes, target_addr: str = "") -> dict:
    """深度取证报告（2026-09-06 GPT 建议升级版）：CsvAnalyzer 解析 → report_engine 取证分析
    （含链上官方冻结证据/资金源去向/冻结邻近/行为分级/证据清单）→ Markdown。
    保留返回契约字段（ok/rows/fmt/target/start/end/usdt_*/marked_n/scam_n/dlg_n/markdown）供 deep.html 复用。"""
    from csv_analyzer import CsvAnalyzer
    from report_engine import analyze_csv_bytes
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        tf.write(raw)
        tmp_path = tf.name
    try:
        az = CsvAnalyzer(tmp_path, target_address=target_addr or None)
        az.read()
        az.process()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV 解析失败: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass  # 临时文件清理失败无害（系统临时目录会自回收）

    fmt = az.fmt  # 'token_transfer' | 'transaction'
    rows_n = len(az.rows)

    # 目标地址：未指定时取出现最多的地址
    if not target_addr:
        cnt = defaultdict(int)
        for r in az.rows:
            cnt[r.get("from", "")] += 1
            cnt[r.get("to", "")] += 1
        target_addr = max(cnt, key=cnt.get) if cnt else ""
    tgt_l = target_addr.lower()

    # 时间范围（全行）
    times = sorted([r.get("blockTime(UTC)", "") for r in az.rows if r.get("blockTime(UTC)")])
    start = times[0] if times else "?"
    end = times[-1] if times else "?"

    # ===== 链上事实（外部调用全部 try 降级：失败不阻塞报告生成） =====
    chain = {"is_blacklisted": None, "index_frozen": False, "cp_status": {}, "account_age_days": None}
    # 1) 第一遍快速分析取对手方列表（纯本地计算）
    from report_engine import analyze as eng_analyze
    rep0 = eng_analyze(az.rows, fmt, target_addr)
    top_cps = set()
    for d in rep0.get("funding", [])[:10] + rep0.get("dest", [])[:10]:
        a = (d.get("addr") or "").lower()
        if len(a) == 34 and a != tgt_l:
            top_cps.add(a)
    # 2) 官方冻结状态 + 冻结证据（本地索引优先；实时合约尝试）
    try:
        bl = check_usdt_blacklist(target_addr)  # True/False/None
        chain["is_blacklisted"] = bl
    except Exception:
        chain["is_blacklisted"] = None
    ev = freeze_evidence(target_addr)
    if ev.get("found"):
        chain["freeze_time"] = ev["first_added_time"]
        chain["freeze_tx"] = ev.get("tx_id", "")
        if ev.get("last_ev") == "AddedBlackList":
            chain["index_frozen"] = True
    else:
        # 静态已知案例回退（FROZEN_AT）
        fat = FROZEN_AT.get(target_addr)
        if fat:
            chain["freeze_time"] = fat + " UTC"
            chain["index_frozen"] = True
    chain["db_updated"] = get_freeze_index_updated()
    # 3) 对手方冻结状态（本地索引 cp_freeze_state，最多 20 个；SQLite 快）
    for a in top_cps:
        try:
            st = cp_freeze_state(a)
            if st is not None:
                chain["cp_status"][a] = st
        except Exception:
            pass
    # 4) 账户年龄（TronGrid 可选；失败跳过）
    try:
        acc = TronAPI().get_account(target_addr)
        if acc and "error" not in acc and acc.get("create_time"):
            age_days = (datetime.now(timezone.utc) - datetime.fromtimestamp(int(acc["create_time"]) / 1000, tz=timezone.utc)).days
            chain["account_age_days"] = age_days
            chain["created"] = ts_to_str(acc.get("create_time", 0))
    except Exception:
        pass

    # ===== 引擎分析 + 渲染 =====
    rep, md = analyze_csv_bytes(az.rows, fmt, target_addr, chain=chain)

    # 契约字段（deep.html 复用）
    usdt_n = len(rep["flow"]["usdt"])
    usdt_in = rep["flow"]["usdt_in"]
    usdt_out = rep["flow"]["usdt_out"]
    return {
        "ok": True,
        "rows": rows_n,
        "fmt": fmt,
        "target": target_addr,
        "start": start,
        "end": end,
        "usdt_n": usdt_n,
        "usdt_in": usdt_in,
        "usdt_out": usdt_out,
        "marked_n": 0,  # 2026-09-06: symbol=BL 为垃圾币非冻结标记（铁律#2），冻结标记概念废弃 → 恒 0
        "scam_n": len(rep["scam"]),
        "dlg_n": rep["dlg"]["delegate"] + rep["dlg"]["undelegate"],
        "frozen": bool(chain["is_blacklisted"] is True or chain["index_frozen"]),
        "frozenUnknown": chain["is_blacklisted"] is None and not chain["index_frozen"],
        "frozenAt": chain.get("freeze_time", ""),
        "frozenTx": chain.get("freeze_tx", ""),
        "score": rep["risk"]["total"],
        "risk": "high" if rep["risk"]["total"] >= 60 else ("mid" if rep["risk"]["total"] >= 30 else "low"),
        "markdown": md,
    }


def _analyze_csv_bytes(raw: bytes, target_addr: str = "") -> dict:
    """已废弃（2026-09-06 由 _deep_forensics 取代）——保留仅供旧引用，勿新增调用。
    历史实现：CsvAnalyzer 直写 Markdown（曾致 BL 垃圾币误标为冻结，现由 report_engine 修正）。"""
    from csv_analyzer import CsvAnalyzer
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        tf.write(raw)
        tmp_path = tf.name
    try:
        az = CsvAnalyzer(tmp_path, target_address=target_addr or None)
        az.read()
        az.process()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV 解析失败: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass  # 临时文件清理失败无害（系统临时目录会自回收）

    fmt = az.fmt  # 'token_transfer' | 'transaction'
    rows_n = len(az.rows)

    # 目标地址：未指定时取出现最多的地址
    if not target_addr:
        cnt = defaultdict(int)
        for r in az.rows:
            cnt[r.get("from", "")] += 1
            cnt[r.get("to", "")] += 1
        target_addr = max(cnt, key=cnt.get) if cnt else ""
    tgt_l = target_addr.lower()

    # 时间范围
    times = sorted([r.get("blockTime(UTC)", "") for r in az.rows if r.get("blockTime(UTC)")])
    start = times[0] if times else "?"
    end = times[-1] if times else "?"

    # ===== 组装 Markdown =====
    L = []
    a = L.append
    a("# USDT 冻结检测 · 深度报告")
    a("")
    a(f"**生成时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    a(f"**数据来源**: 用户上传 TronScan CSV（{rows_n} 行）")
    a(f"**时间范围**: {start} ~ {end}")
    a(f"**目标地址**: {target_addr}")
    a(f"**CSV 类型**: {'tokenTransfer（资金流）' if fmt == 'token_transfer' else 'transaction（区块交易）'}")
    a("")
    a("---")
    a("")

    # 1. USDT 资金流（token CSV）
    usdt_rows = [r for r in az.rows if r.get("symbol") == "USDT"
                 and r.get("tokenAddress", "").strip() == USDT_CONTRACT]
    a("## 1. USDT 资金流汇总")
    a("")
    if usdt_rows:
        inflow = sum(r["_value"] for r in usdt_rows if r.get("to", "").lower() == tgt_l)
        outflow = sum(r["_value"] for r in usdt_rows if r.get("from", "").lower() == tgt_l)
        a(f"| 指标 | 数值 |")
        a(f"| --- | --- |")
        a(f"| USDT 交易笔数 | {len(usdt_rows)} |")
        a(f"| 转入总额 | {inflow:,.2f} USDT |")
        a(f"| 转出总额 | {outflow:,.2f} USDT |")
        a(f"| 净额 | {inflow - outflow:,.2f} USDT |")
        a("")
        # 双向对手方 TOP10
        in_c, out_c = defaultdict(float), defaultdict(float)
        in_n, out_n = defaultdict(int), defaultdict(int)
        for r in usdt_rows:
            if r.get("to", "").lower() == tgt_l:
                f = r.get("from", "")
                in_c[f] += r["_value"]; in_n[f] += 1
            if r.get("from", "").lower() == tgt_l:
                t = r.get("to", "")
                out_c[t] += r["_value"]; out_n[t] += 1
        a("### 对手方 TOP10（转入）")
        a("")
        a("| 地址 | 笔数 | 金额 (USDT) |")
        a("| --- | --- | --- |")
        for addr, v in sorted(in_c.items(), key=lambda x: -x[1])[:10]:
            a(f"| `{_md_escape(addr)}` | {in_n[addr]} | {v:,.2f} |")
        a("")
        a("### 对手方 TOP10（转出）")
        a("")
        a("| 地址 | 笔数 | 金额 (USDT) |")
        a("| --- | --- | --- |")
        for addr, v in sorted(out_c.items(), key=lambda x: -x[1])[:10]:
            a(f"| `{_md_escape(addr)}` | {out_n[addr]} | {v:,.2f} |")
        a("")
    else:
        a("本 CSV 未发现 USDT TRC-20 转账（仅统计 `TR7NHqje...` 合约）。")
        a("")

    # 2. 冻结/诈骗标记
    a("## 2. 冻结/诈骗标记扫描")
    a("")
    marked = {addr: d for addr, d in az.addr_tags.items() if d["freeze_n"] > 0 or d["tags"]}
    if marked:
        a(f"发现 **{len(marked)}** 个地址有冻结/BL 标记：")
        a("")
        a("| 地址 | BL 次数 | 标签 |")
        a("| --- | --- | --- |")
        for addr, d in sorted(marked.items(), key=lambda x: -x[1]["freeze_n"])[:10]:
            tags = ", ".join(sorted(d["tags"]))
            a(f"| `{_md_escape(addr)}` | {d['freeze_n']} | {tags} |")
        a("")
    else:
        a("未发现冻结/BL 标记。")
        a("")
    if az.scam:
        a("### 疑似诈骗/解冻代币")
        a("")
        a("| 代币 | 笔数 | 金额 |")
        a("| --- | --- | --- |")
        for name, d in sorted(az.scam.items(), key=lambda x: -x[1]["cnt"])[:10]:
            a(f"| `{_md_escape(name)}` | {d['cnt']} | {d['amt']:,.2f} |")
        a("")
        a("> ⚠️ UNFREEZE/UNLOCK/UNBANNED 等代币全是骗子空投，**Tether 官方不会用链上备注或 TG 联系你**。")
        a("")

    # 3. TRC-10 代币
    if az.trc10:
        a("## 3. 其他 TRC-10 代币（非 USDT）")
        a("")
        a("| 代币 | 笔数 | 金额 |")
        a("| --- | --- | --- |")
        for name, d in sorted(az.trc10.items(), key=lambda x: -x[1]["cnt"])[:10]:
            a(f"| `{_md_escape(name)}` | {d['cnt']} | {d['amt']:,.2f} |")
        a("")

    # 4. 能量委托（transaction CSV）
    if fmt == "transaction" and az.dlg["total_n"]:
        a("## 4. 能量/带宽委托")
        a("")
        a(f"- 委托: {az.dlg['freeze_n']} 次")
        a(f"- 解除: {az.dlg['unfreeze_n']} 次")
        a(f"- 合计: {az.dlg['total_n']} 次（职业 OTC 特征信号）")
        a("")

    # 5. 风险提示
    a("## 5. 风险提示")
    a("")
    a("- 本报告基于用户上传的 CSV 全量统计（非抽样），**可复核**。")
    a("- 结论区分「链上事实」与「推断」：金额/笔数/时间均为链上事实；触发原因等为推断。")
    a("- **时间邻近 ≠ 冻结因果**：冻结前大额入账 ≠ 冻结原因。")
    a("- 如需申诉协助，请勿相信任何付费解冻服务；**付费解冻=诈骗**。")
    a("")
    a("---")
    a("")
    a("*USDT Freeze Check*")

    return {
        "ok": True,
        "rows": rows_n,
        "fmt": fmt,
        "target": target_addr,
        "start": start,
        "end": end,
        "usdt_n": len(usdt_rows),
        "usdt_in": sum(r["_value"] for r in usdt_rows if r.get("to", "").lower() == tgt_l) if usdt_rows else 0,
        "usdt_out": sum(r["_value"] for r in usdt_rows if r.get("from", "").lower() == tgt_l) if usdt_rows else 0,
        "marked_n": len(marked),
        "scam_n": len(az.scam),
        "dlg_n": az.dlg["total_n"],
        "markdown": "\n".join(L),
    }


@app.post("/api/deep-report")
async def deep_report(file: UploadFile = File(...), address: str = Query(None, description="目标地址（可选，默认取出现最多的地址）")):
    """上传 TronScan CSV → 全量深度分析 → 返回结构化摘要 + Markdown 报告。
    免费使用；报告含打赏指引。"""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(status_code=400, detail="文件超过 10MB 限制")
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="请上传 .csv 文件（TronScan 导出格式）")
    # CSV 解析/分析是同步重活：丢线程池执行，避免阻塞 async 事件循环（2026-09-05 审查发现）
    # 2026-09-06 升级：_deep_forensics 取证报告引擎（官方证据/资金源去向/冻结邻近/证据清单）
    return await run_in_threadpool(lambda: _deep_forensics(raw, target_addr=address or ""))


# 静态文件挂载（放在 API 路由之后，避免覆盖 /api/*）
if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8902)
