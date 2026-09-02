#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_freeze_index.py — 同步 USDT 合约 AddedBlackList/RemovedBlackList 事件到 SQLite 冻结索引。

冻结本质：Tether 通过 USDT 合约 addBlackList(addr) 冻结地址，产生链上事件 AddedBlackList(addr)。
本脚本把全量历史事件拉下来存 SQLite，供 api_server.get_frozen_at() 对任意地址返回确切冻结时间（E1 链上事实）。

用法:
  python3 sync_freeze_index.py               # 增量（断点续传）
  python3 sync_freeze_index.py --reset       # 全量重扫（重置断点，2019-06 起）
  python3 sync_freeze_index.py --from 1780000000000 --until 1787450000000   # 自定义范围（测试用）
环境: FREEZE_DB 覆盖 db 路径（默认 /opt/usdt-forensics/freeze_index.db）
"""
import os, sys, json, time, sqlite3, urllib.request
from datetime import datetime, timezone

USDT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
EVENTS = ("AddedBlackList", "RemovedBlackList")
START_MS = int(datetime(2019, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
DB = os.environ.get("FREEZE_DB", "/opt/usdt-forensics/freeze_index.db")
BASE_URL = "https://api.trongrid.io"


def tg_events(event, min_ts, max_ts, fingerprint=None, retries=4):
    url = (f"{BASE_URL}/v1/contracts/{USDT}/events?event_name={event}&limit=200"
           f"&min_block_timestamp={min_ts}&max_block_timestamp={max_ts}")
    if fingerprint:
        url += f"&fingerprint={fingerprint}"
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sync_freeze_index/1.0"})
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except Exception as e:
            if "429" in str(e) and i < retries - 1:
                time.sleep(4 * (i + 1))
            else:
                raise
    return {"data": []}


def get_cursor(conn, event):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (f"last_ts_{event}",)).fetchone()
    return int(row[0]) if row else START_MS


def sync_event(conn, event, lo_ms, hi_ms):
    cur = lo_ms
    total = 0
    while cur < hi_ms:
        end = min(cur + 30 * 86400 * 1000, hi_ms)  # 30 天/段，防单请求范围过大
        fp = None
        page = 0
        while True:
            d = tg_events(event, cur, end, fp)
            data = d.get("data", [])
            for e in data:
                user = str(e.get("result", {}).get("_user") or e.get("result", {}).get("0") or "").lower().replace("0x", "")
                if len(user) != 40:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO freeze_events(addr_hex, event_name, block_ts, tx_id) VALUES(?,?,?,?)",
                    (user, event, int(e.get("block_timestamp", 0)), e.get("transaction_id", "")))
            total += len(data)
            fp = d.get("meta", {}).get("fingerprint")
            page += 1
            if not fp or not data:
                break
            time.sleep(0.8)  # 限流防 429
            if page >= 800:
                print(f"  ! {event} {datetime.fromtimestamp(cur/1000, tz=timezone.utc).date()} 单段超页数上限，跳过")
                break
        cur = end
        set_cursor(conn, event, cur)
        conn.commit()
        dt = datetime.fromtimestamp(cur / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        print(f"  {event}: 推进到 {dt} | 段内 {total} 条")
        time.sleep(0.5)
    return total


def set_cursor(conn, event, ts):
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)", (f"last_ts_{event}", str(ts)))


def main():
    reset = "--reset" in sys.argv
    until = None
    start = None
    if "--until" in sys.argv:
        until = int(sys.argv[sys.argv.index("--until") + 1])
    if "--from" in sys.argv:
        start = int(sys.argv[sys.argv.index("--from") + 1])

    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS freeze_events(
        addr_hex TEXT NOT NULL, event_name TEXT NOT NULL, block_ts INTEGER NOT NULL, tx_id TEXT,
        PRIMARY KEY (addr_hex, event_name, block_ts))""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_addr ON freeze_events(addr_hex)")
    conn.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()

    now_ms = int(time.time() * 1000)
    hi_ms = until or now_ms
    for ev in EVENTS:
        lo = start if start is not None else (START_MS if reset else get_cursor(conn, ev))
        if lo >= hi_ms:
            print(f"{ev}: 已是最新")
            continue
        print(f"同步 {ev}: {datetime.fromtimestamp(lo/1000, tz=timezone.utc)} → {datetime.fromtimestamp(hi_ms/1000, tz=timezone.utc)}")
        sync_event(conn, ev, lo, hi_ms)

    n = conn.execute("SELECT COUNT(*) FROM freeze_events").fetchone()[0]
    n_add = conn.execute("SELECT COUNT(*) FROM freeze_events WHERE event_name='AddedBlackList'").fetchone()[0]
    n_rem = conn.execute("SELECT COUNT(*) FROM freeze_events WHERE event_name='RemovedBlackList'").fetchone()[0]
    print(f"完成: 总 {n} 条 (AddedBlackList {n_add} / RemovedBlackList {n_rem})")
    conn.close()


if __name__ == "__main__":
    main()
