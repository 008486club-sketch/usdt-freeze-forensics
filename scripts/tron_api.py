#!/usr/bin/env python3
# TronGrid API wrapper with retry logic
# Usage: python3 tron_api.py <address> [--api-key KEY]

import requests
import time
import json
import sys
import os
import sqlite3
from typing import Optional, Dict, Any, List

TRONGRID_BASE = 'https://api.trongrid.io'
USDT_CONTRACT = 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'  # 真实 USDT 合约（已修正）

# ===== 轻量 SQLite 查询缓存（2026-09-05 加：同地址重复查秒出，省 TronGrid 配额）=====
# 策略：account/trc10 历史稳定 TTL 24h；trc20 抽样 6h；isBlackListed 当前状态【不缓存】
CACHE_DB = os.environ.get("API_CACHE_DB", "/opt/usdt-forensics/api_cache.db")
CACHE_TTL_ACCOUNT = 86400    # 24h：账户创建时间/地址元信息稳定
CACHE_TTL_TRC20 = 21600      # 6h：抽样窗口随新交易变化，容忍半日延迟
CACHE_TTL_TRC10 = 86400      # 24h：垃圾币持仓低频变化

def _cache_get(key):
    try:
        c = sqlite3.connect(CACHE_DB, timeout=3)
        row = c.execute("SELECT value FROM api_cache WHERE key=? AND expires_at>?", (key, int(time.time()))).fetchone()
        c.close()
        return row[0] if row else None
    except Exception:
        return None

def _cache_set(key, value, ttl):
    try:
        c = sqlite3.connect(CACHE_DB, timeout=3)
        c.execute("CREATE TABLE IF NOT EXISTS api_cache(key TEXT PRIMARY KEY, value TEXT, expires_at INTEGER)")
        c.execute("INSERT OR REPLACE INTO api_cache VALUES(?,?,?)", (key, value, int(time.time()) + ttl))
        # 顺带清理过期行（低频小表，防长期膨胀；2026-09-05 审查）
        try:
            c.execute("DELETE FROM api_cache WHERE expires_at < ?", (int(time.time()),))
        except Exception:
            pass
        c.commit()
        c.close()
    except Exception:
        pass


class TronAPIError(Exception):
    pass


def retry_with_backoff(func, max_retries=3, base_delay=2):
    """Exponential backoff: 2s, 4s, 8s for 429/401/5xx"""
    for attempt in range(max_retries):
        try:
            return func()
        except (requests.exceptions.HTTPError, requests.exceptions.RequestException) as e:
            if attempt == max_retries - 1:
                raise
            status = getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
            if status in (429, 401, 500, 502, 503, 504):
                delay = base_delay * (2 ** attempt)
                print(f'[RETRY] {status} error, waiting {delay}s... (attempt {attempt+1}/{max_retries})')
                time.sleep(delay)
            else:
                raise


class TronAPI:
    def __init__(self, api_key=None, base_url=TRONGRID_BASE):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        if api_key:
            self.session.headers['TRON-PRO-API-KEY'] = api_key
        self.session.headers['Accept'] = 'application/json'
        self.session.timeout = 30

    def _get(self, endpoint, params=None, allow_400=False, cache_key=None, cache_ttl=0):
        """GET 封装。allow_400=True 时 400（地址无效/链上不存在）返回 {} 而非抛异常，
        由调用方转为友好错误（get_account → {'error': ...} → HTTP 404）。
        cache_key/cache_ttl 给定后：先查 SQLite 缓存，命中直接返回；未命中请求成功(200)后回写。"""
        if cache_key and cache_ttl:
            hit = _cache_get(cache_key)
            if hit is not None:
                try:
                    return json.loads(hit)
                except Exception:
                    pass  # 缓存损坏则重新请求
        url = f'{self.base_url}{endpoint}'
        def do_request():
            resp = self.session.get(url, params=params or {})
            if allow_400 and resp.status_code == 400:
                return None  # None = 不缓存（地址无效不该长期缓存）
            resp.raise_for_status()
            return resp.json()
        data = retry_with_backoff(do_request)
        if cache_key and cache_ttl and data is not None:
            try:
                _cache_set(cache_key, json.dumps(data), cache_ttl)
            except Exception:
                pass
        if data is None:
            return {}
        return data

    def get_account(self, address):
        """Get account info (create time, balance, permissions)"""
        data = self._get(f'/v1/accounts/{address}', allow_400=True,
                         cache_key=f'acct:{address}', cache_ttl=CACHE_TTL_ACCOUNT)
        if not data or not data.get('data'):
            return {'error': 'Account not found', 'address': address}
        return data['data'][0]

    def get_trc20(self, address, contract=USDT_CONTRACT, limit=100, order_by='block_timestamp,desc'):
        """Get TRC-20 (USDT) transfer records"""
        params = {'contract_address': contract, 'limit': limit, 'order_by': order_by}
        data = self._get(f'/v1/accounts/{address}/transactions/trc20', params,
                         cache_key=f'trc20:{address}:{contract}:{limit}:{order_by}', cache_ttl=CACHE_TTL_TRC20)
        return data.get('data', [])

    def get_trc10(self, address, limit=100):
        """Get TRC-10 token records (scam/spam tokens)"""
        params = {'limit': limit}
        data = self._get(f'/v1/accounts/{address}/transactions/trc10', params,
                         cache_key=f'trc10:{address}:{limit}', cache_ttl=CACHE_TTL_TRC10)
        return data.get('data', [])

    def get_transactions(self, address, limit=100):
        """Get all transactions for address"""
        params = {'limit': limit, 'order_by': 'block_timestamp,desc'}
        data = self._get(f'/v1/accounts/{address}/transactions', params)
        return data.get('data', [])

    def get_balance(self, address):
        """Get TRX and USDT balances"""
        acc = self.get_account(address)
        if 'error' in acc:
            return {'trx': 0.0, 'usdt': 0.0}
        trx_sun = acc.get('balance', 0)
        trx = trx_sun / 1_000_000
        trc20 = acc.get('trc20', [])
        usdt = 0.0
        for t in trc20:
            if USDT_CONTRACT in t:
                usdt = float(t[USDT_CONTRACT]) / 1_000_000
                break
        return {'trx': trx, 'usdt': usdt}


def main():
    import argparse
    parser = argparse.ArgumentParser(description='TronGrid API client')
    parser.add_argument('address', help='Tron address')
    parser.add_argument('--api-key', help='TronGrid API key (optional)')
    parser.add_argument('--output', choices=['json', 'summary'], default='summary')
    args = parser.parse_args()

    api = TronAPI(api_key=args.api_key)
    print(f'Querying {args.address}...')
    print()

    print('=== Account Info ===')
    acc = api.get_account(args.address)
    if 'error' in acc:
        print(f'Error: {acc["error"]}')
        return

    print(f'Address: {acc.get("address", args.address)}')
    print(f'Create Time: {acc.get("create_time", "N/A")}')
    bal = api.get_balance(args.address)
    print(f'TRX Balance: {bal["trx"]:.6f}')
    print(f'USDT Balance: {bal["usdt"]:.2f}')

    if args.output == 'json':
        print()
        print('=== Full JSON ===')
        print(json.dumps(acc, indent=2, ensure_ascii=False))
        return

    print()
    print('=== Recent USDT Transfers (TRC-20) ===')
    trc20 = api.get_trc20(args.address, limit=10)
    if not trc20:
        print('(none)')
    else:
        for i, tx in enumerate(trc20[:5], 1):
            from_addr = tx.get('from', '?')
            to_addr = tx.get('to', '?')
            value = float(tx.get('value', 0)) / 1_000_000
            tx_hash = tx.get('transaction_id', '?')[:20] + '...'
            print(f'{i}. {value:.2f} USDT  {from_addr[:8]}... -> {to_addr[:8]}...  tx:{tx_hash}')

    print()
    print('=== TRC-10 Tokens ===')
    trc10 = api.get_trc10(args.address, limit=10)
    if not trc10:
        print('(none)')
    else:
        for i, tx in enumerate(trc10[:5], 1):
            name = tx.get('token_name', tx.get('token_id', '?'))
            value = tx.get('value', 0)
            print(f'{i}. {name}: {value}')

    print()
    print('=== Done ===')


if __name__ == '__main__':
    main()
