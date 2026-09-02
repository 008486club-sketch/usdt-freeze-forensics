#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
router_fastapi.py — 埋点采集路由（挂到 api_server 现有 FastAPI app，不新起进程/不抢 8902）。

端点:
  POST /api/collect  接收 text/plain body（collect.js sendBeacon/Blob 格式，非 JSON content-type）
                     → Collector.normalize（白名单/隐私指纹/钳位）→ allow（限流）→ write（JSONL）
  GET  /api/stats    校验 UA_STATS_TOKEN → Collector.stats（漏斗/UV/风险分布）

全部处理逻辑复用 api/collector.py（已独立验证 49/49）：
  - 事件 schema: {ev,path,lang,uv,device,ref,score,level,dur_ms,dwell_ms,status,addr_fp}
  - 隐私: 地址 sha256 前8指纹(addr_fp)；IP+UA 当日 HMAC 桶(uv)；原文不落盘
  - 存储: events-YYYY-MM-DD.jsonl（按日单文件追加）
env（与任务卡约定一致）: UA_DATA_DIR / UA_SECRET / UA_STATS_TOKEN / UA_TRUST_PROXY
"""
import os
import time

from fastapi import APIRouter, Request, HTTPException, Query

from collector import Collector

router = APIRouter()

_COL = None


def get_collector() -> Collector:
    """单例 Collector；env 每次重启读取（改 env 需 restart usdt-forensics）"""
    global _COL
    if _COL is None:
        data_dir = os.environ.get("UA_DATA_DIR", "/var/lib/usdt-forensics/analytics")
        secret = os.environ.get("UA_SECRET", "ua-secret-change-me")
        trust = os.environ.get("UA_TRUST_PROXY", "1") not in ("0", "false", "no")
        _COL = Collector(data_dir, secret, trust_proxy=trust, rate_limit_per_min=30)
    return _COL


@router.post("/api/collect")
async def collect_event(request: Request):
    c = get_collector()
    raw = (await request.body()).decode("utf-8", "replace")
    peer = request.client.host if request.client else ""
    headers = {k: v for k, v in request.headers.items()}
    event, err = c.normalize(raw, headers=headers, peer=peer)
    if err:
        # 固定错误码，绝不回显用户提交的原文（collector.py 铁律 #2）
        raise HTTPException(status_code=400, detail={"error": err})
    if not c.allow(event["uv"]):
        raise HTTPException(status_code=429, detail={"error": "rate-limit"})
    c.write(event)
    return {"ok": True, "id": "%d-%s" % (event["ts"], event["uv"][:6])}


@router.get("/api/stats")
async def get_stats(token: str = Query(None, description="UA_STATS_TOKEN"),
                    days: int = Query(7, ge=1, le=90)):
    expect = os.environ.get("UA_STATS_TOKEN", "")
    if not expect or token is None or token != expect:
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})
    return get_collector().stats(days=days)


@router.get("/api/ua-health")
async def ua_health():
    return {"ok": True, "service": "usdt-ua-collector", "ts": int(time.time())}
