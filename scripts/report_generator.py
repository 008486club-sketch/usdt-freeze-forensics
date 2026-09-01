#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report_generator.py - USDT Freeze Forensics Report Generator
Generates Markdown report from CSV analysis + API data

Usage: python3 report_generator.py <csv_path> [--api-key KEY] [--output report.md]
"""

import sys
import os
import json
import argparse
from datetime import datetime
from collections import defaultdict

# Import csv_analyzer (same directory)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from csv_analyzer import CsvAnalyzer

# Import tron_api (same directory)
try:
    from tron_api import TronAPI
    HAS_API = True
except ImportError:
    HAS_API = False


def fmt_hash(h):
    if not h or len(h) < 20:
        return h or '-'
    return h[:12] + '...' + h[-8:]


def fmt_amt(v, d=2):
    if abs(v) >= 1:
        return '{:,.{p}f}'.format(v, p=d)
    return '{:.6f}'.format(v)


def fmt_addr(a):
    if not a:
        return '-'
    return a[:6] + '...' + a[-4:]


def ts_to_str(ts_ms):
    if not ts_ms:
        return 'N/A'
    try:
        dt = datetime.utcfromtimestamp(ts_ms / 1000)
        return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    except Exception:
        return str(ts_ms)


class ReportGenerator:
    def __init__(self, csv_path, api_key=None, target_addr=None):
        self.csv_path = csv_path
        self.api_key = api_key
        self.target_addr = target_addr
        self.analyzer = None
        self.api_data = {}

    def analyze_csv(self):
        """Run CSV analysis"""
        self.analyzer = CsvAnalyzer(self.csv_path, target_address=self.target_addr)
        self.analyzer.read()
        self.analyzer.process()

    def fetch_api_data(self, address):
        """Fetch on-chain data via TronGrid API"""
        if not HAS_API:
            print('[WARN] tron_api.py not available, skipping API fetch')
            return

        api = TronAPI(api_key=self.api_key)
        print(f'Fetching API data for {address}...')

        try:
            self.api_data['account'] = api.get_account(address)
            self.api_data['trc20'] = api.get_trc20(address, limit=50)
            self.api_data['trc10'] = api.get_trc10(address, limit=50)
            self.api_data['balance'] = api.get_balance(address)
        except Exception as e:
            print(f'[WARN] API fetch failed: {e}')

    def generate_report(self, output_path=None):
        """Generate Markdown report"""
        if not self.analyzer:
            self.analyze_csv()

        lines = []
        a = lines.append

        # Header
        a('# 冻结诊断报告')
        a("")
        a(f'**生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        a(f'**数据来源**: {os.path.basename(self.csv_path)}')
        a(f'**数据格式**: {self.analyzer.fmt}')
        a("")

        # Section 1: Freeze Status
        a('## 1. 冻结状态（BL封条）')
        a("")
        marked = {addr: d for addr, d in self.analyzer.addr_tags.items()
                  if d['freeze_n'] > 0 or d['tags']}
        if marked:
            a(f'发现 **{len(marked)}** 个地址有冻结/BL标记：')
            a("")
            ranked = sorted(marked.items(), key=lambda x: x[1]['freeze_n'], reverse=True)[:10]
            for addr, d in ranked:
                tags = ', '.join(sorted(d['tags']))
                a(f'- **{fmt_addr(addr)}** — BL {d["freeze_n"]}次  [{tags}]')
            if len(marked) > 10:
                a(f'- ... 共 {len(marked)} 个标记地址')
        else:
            a('未发现冻结/BL标记。')
        a("")

        # Section 2: Account Profile
        a('## 2. 账户画像')
        a("")
        if self.api_data.get('account') and 'error' not in self.api_data['account']:
            acc = self.api_data['account']
            a('**链上事实**：')
            a("")
            a(f'- **创建时间**: {ts_to_str(acc.get("create_time"))}')
            bal = self.api_data.get('balance', {})
            a(f'- **TRX余额**: {bal.get("trx", 0):.6f} TRX')
            a(f'- **USDT余额**: {bal.get("usdt", 0):.2f} USDT')
            a(f'- **涉及地址数**: {len(self.analyzer.all_addrs)}')
            if self.analyzer.timestamps:
                mn, mx = min(self.analyzer.timestamps), max(self.analyzer.timestamps)
                a(f'- **活跃时间**: {mn} ~ {mx} UTC')
                a(f'- **跨度**: {(mx - mn).days} 天')
        else:
            a('**CSV统计**：')
            a("")
            a(f'- **涉及地址数**: {len(self.analyzer.all_addrs)}')
            if self.analyzer.timestamps:
                mn, mx = min(self.analyzer.timestamps), max(self.analyzer.timestamps)
                a(f'- **活跃时间**: {mn} ~ {mx} UTC')
                a(f'- **跨度**: {(mx - mn).days} 天')
        a("")

        # Section 3: Fund Flow
        a('## 3. 资金流')
        a("")
        if self.analyzer.fmt == 'token_transfer':
            ti = sum(v['in'] for v in self.analyzer.cp.values())
            to2 = sum(v['out'] for v in self.analyzer.cp.values())
            ni = sum(1 for v in self.analyzer.cp.values() if v['in'] > 0)
            no = sum(1 for v in self.analyzer.cp.values() if v['out'] > 0)

            a('**链上事实**：')
            a("")
            a(f'- **USDT总转入**: {fmt_amt(ti)} USDT ({ni} 个地址)')
            a(f'- **USDT总转出**: {fmt_amt(to2)} USDT ({no} 个地址)')
            a(f'- **总流水**: {fmt_amt(ti + to2)} USDT')
            net = ti - to2
            sign = '+' if net >= 0 else ''
            a(f'- **净差额**: {sign}{fmt_amt(net)} USDT')
            a("")

            # TOP counterparties
            a('**TOP对手方**（按USDT总量）：')
            a("")
            ranked = sorted(self.analyzer.cp.items(),
                            key=lambda x: x[1]['in'] + x[1]['out'],
                            reverse=True)[:10]
            for i, (addr, d) in enumerate(ranked, 1):
                net = d['in'] - d['out']
                ns = f'+{fmt_amt(net)}' if net >= 0 else f'-{fmt_amt(abs(net))}'
                a(f'{i}. **{fmt_addr(addr)}** — {d["cnt"]}笔  转入 {fmt_amt(d["in"])}  转出 {fmt_amt(d["out"])}  净 {ns}')
        else:
            a('**链上事实**：')
            a("")
            a(f'- **收入笔数**: {self.analyzer.usdt_in_n}')
            a(f'- **支出笔数**: {self.analyzer.usdt_out_n}')
        a("")

        # Section 4: High-risk Signals
        a('## 4. 高风险信号')
        a("")

        # Scam tokens
        if self.analyzer.scam:
            a('**诈骗代币**：')
            a("")
            ranked_s = sorted(self.analyzer.scam.items(),
                              key=lambda x: x[1]['cnt'],
                              reverse=True)[:10]
            for name, d in ranked_s:
                a(f'- **{name[:40]}** — {d["cnt"]}笔  总量 {fmt_amt(d["amt"])}')
            a("")

        # TRC-10 (potential spam)
        if self.analyzer.trc10:
            a('**TRC-10代币**（可能为垃圾币）：')
            a("")
            ranked_t = sorted(self.analyzer.trc10.items(),
                              key=lambda x: x[1]['cnt'],
                              reverse=True)[:10]
            for name, d in ranked_t:
                a(f'- **{name[:40]}** — {d["cnt"]}笔  总量 {fmt_amt(d["amt"])}')
            if len(self.analyzer.trc10) > 10:
                a(f'- ... 共 {len(self.analyzer.trc10)} 种代币')
            a("")

        if not self.analyzer.scam and not self.analyzer.trc10:
            a('未发现高风险信号。')
            a("")

        # Section 5: Suspicious Transactions
        a('## 5. 最可疑触发交易')
        a("")
        a('**推断**：')
        a("")
        if self.analyzer.fmt == 'token_transfer' and self.analyzer.cp:
            # Find largest single transfer
            max_in_addr = max(self.analyzer.cp.items(),
                              key=lambda x: x[1]['in'])
            max_out_addr = max(self.analyzer.cp.items(),
                               key=lambda x: x[1]['out'])
            a(f'- **最大转入方**: {fmt_addr(max_in_addr[0])} — {fmt_amt(max_in_addr[1]["in"])} USDT ({max_in_addr[1]["cnt"]}笔)')
            a(f'- **最大转出方**: {fmt_addr(max_out_addr[0])} — {fmt_amt(max_out_addr[1]["out"])} USDT ({max_out_addr[1]["cnt"]}笔)')
        elif self.analyzer.fmt == 'transaction':
            a(f'- **收入笔数**: {self.analyzer.usdt_in_n}')
            a(f'- **支出笔数**: {self.analyzer.usdt_out_n}')

        # Delegation stats
        if self.analyzer.dlg['total_n'] > 0:
            a(f'- **能量/带宽委托**: {self.analyzer.dlg["total_n"]}次')
            a(f'  - Freeze: {self.analyzer.dlg["freeze_n"]}')
            a(f'  - Unfreeze: {self.analyzer.dlg["unfreeze_n"]}')
        a("")

        # Section 6: Appeal Suggestions
        a('## 6. 申诉建议')
        a("")
        a('**有利证据**：')
        a("")
        if self.analyzer.fmt == 'token_transfer':
            ti = sum(v['in'] for v in self.analyzer.cp.values())
            a(f'- 总流水 {fmt_amt(ti)} USDT，交易活跃')
        if self.analyzer.timestamps:
            mn, mx = min(self.analyzer.timestamps), max(self.analyzer.timestamps)
            a(f'- 活跃时间跨度 {(mx - mn).days} 天，非短期异常')
        if not self.analyzer.scam:
            a('- 未接收诈骗代币')
        a("")

        a('**不利证据**：')
        a("")
        if marked:
            a(f'- {len(marked)} 个地址有冻结/BL标记')
        if self.analyzer.scam:
            a(f'- 接收 {len(self.analyzer.scam)} 种诈骗代币')
        if self.analyzer.trc10:
            a(f'- 接收 {len(self.analyzer.trc10)} 种 TRC-10 代币（可能为垃圾币）')
        a("")

        a('**建议**：')
        a("")
        a('1. 整理所有正常业务交易的 TxHash 作为证据')
        a('2. 如有被标记地址，说明交易背景（如 OTC、交易所提现）')
        a('3. 准备账户创建时间、历史活跃度证明')
        a('4. 联系 TronLink 或交易所客服提交申诉')
        a("")

        # Footer
        a('---')
        a("")
        a(f'*报告由 csv_analyzer.py + report_generator.py 自动生成*')
        a(f'*生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*')

        report = '\n'.join(lines)

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f'[OK] Report saved to {output_path}')
        else:
            print(report)

        return report


def main():
    parser = argparse.ArgumentParser(description='USDT Freeze Forensics Report Generator')
    parser.add_argument('csv_path', help='Path to TronScan CSV file')
    parser.add_argument('--api-key', help='TronGrid API key (optional)')
    parser.add_argument('--address', help='Tron address for API fetch (optional)')
    parser.add_argument('--output', '-o', help='Output Markdown file path')
    args = parser.parse_args()

    if not os.path.isfile(args.csv_path):
        print(f'Error: CSV file not found: {args.csv_path}')
        sys.exit(1)

    gen = ReportGenerator(args.csv_path, api_key=args.api_key, target_addr=args.address)

    print(f'Analyzing {args.csv_path}...')
    gen.analyze_csv()
    print(f'[OK] CSV analyzed: {len(gen.analyzer.rows)} rows, format: {gen.analyzer.fmt}')

    if args.address and HAS_API:
        gen.fetch_api_data(args.address)

    print()
    gen.generate_report(output_path=args.output)


if __name__ == '__main__':
    main()
