#!/usr/bin/env python3
# TronGrid API wrapper with retry logic
# Usage: python3 tron_api.py <address> [--api-key KEY]

import requests
import time
import json
import sys
import os
from typing import Optional, Dict, Any, List

TRONGRID_BASE = 'https://api.trongrid.io'
USDT_CONTRACT = 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'  # 真实 USDT 合约（已修正）


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

    def _get(self, endpoint, params=None):
        url = f'{self.base_url}{endpoint}'
        def do_request():
            resp = self.session.get(url, params=params or {})
            resp.raise_for_status()
            return resp.json()
        return retry_with_backoff(do_request)

    def get_account(self, address):
        """Get account info (create time, balance, permissions)"""
        data = self._get(f'/v1/accounts/{address}')
        if not data.get('data'):
            return {'error': 'Account not found', 'address': address}
        return data['data'][0]

    def get_trc20(self, address, contract=USDT_CONTRACT, limit=100, order_by='block_timestamp,desc'):
        """Get TRC-20 (USDT) transfer records"""
        params = {'contract_address': contract, 'limit': limit, 'order_by': order_by}
        data = self._get(f'/v1/accounts/{address}/transactions/trc20', params)
        return data.get('data', [])

    def get_trc10(self, address, limit=100):
        """Get TRC-10 token records (scam/spam tokens)"""
        params = {'limit': limit}
        data = self._get(f'/v1/accounts/{address}/transactions/trc10', params)
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
