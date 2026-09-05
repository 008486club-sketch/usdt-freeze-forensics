#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
csv_analyzer.py — TRON USDT 冻结取证 CSV 全量分析脚本
用法:
    python3 csv_analyzer.py <csv路径> [--address 目标地址] [--type token|transaction]

支持两种 TronScan 导出 CSV:
  - TRON-tokenTransfer-*.csv   (含 USDT 金额, 表头有 tokenAddress/isConfirm)
  - TRON-transaction-*.csv     (冻结时间/能量信号, 表头有 contractType/status)
"""
import csv
import sys
import argparse
from collections import defaultdict

USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
FREEZE_KW = ["UNFREEZE", "UNLOCK", "UNBANNED", "解封", "unfrozen"]  # 2026-09-06: 移除 "BL"——symbol=BL 是 TRC-10 垃圾币名非冻结标记（SKILL v2.4 铁律 #2）


def short_hash(tx):
    """TxHash 前12+后8"""
    tx = (tx or "").strip()
    if len(tx) <= 20:
        return tx
    return tx[:12] + "..." + tx[-8:]


def detect_type(rows):
    """自动识别 CSV 类型: token / transaction"""
    if rows and "contractType" in rows[0]:
        return "transaction"
    return "token"


def load_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            for k in r:
                if r[k] is None:
                    r[k] = ""
            try:
                r["_value"] = float(r.get("value", 0) or 0)
            except (ValueError, TypeError):
                r["_value"] = 0.0
            rows.append(r)
    return rows


def fmt(v):
    return f"{v:,.2f}"


class CsvAnalyzer:
    """兼容层：把 csv_analyzer 的命令行分析封装成类，供 report_generator 调用。

    属性：
      rows: 原始行列表
      fmt: 'token_transfer' 或 'transaction'
      all_addrs: 涉及的所有地址集合
      timestamps: 时间戳列表（datetime）
      cp: 对手方统计 {addr: {'in': 转入额, 'out': 转出额, 'cnt': 笔数}}
      usdt_in / usdt_out / usdt_in_n / usdt_out_n: USDT 进出汇总
      scam: 诈骗代币 {name: {'cnt': 笔数, 'amt': 金额}}
      trc10: TRC-10 代币 {name: {'cnt': 笔数, 'amt': 金额}}
      dlg: 能量委托 {'freeze_n': 委托次数, 'unfreeze_n': 解除次数, 'total_n': 合计}
      addr_tags: 冻结标记地址 {addr: {'freeze_n': 次数, 'tags': [标签]}}
    """

    def __init__(self, csv_path, target_address=None):
        self.csv_path = csv_path
        self.target = (target_address or "").lower()
        self.rows = []
        self.fmt = "token_transfer"
        self.all_addrs = set()
        self.timestamps = []
        self.cp = defaultdict(lambda: {'in': 0.0, 'out': 0.0, 'cnt': 0})
        self.usdt_in = 0.0
        self.usdt_out = 0.0
        self.usdt_in_n = 0
        self.usdt_out_n = 0
        self.scam = defaultdict(lambda: {'cnt': 0, 'amt': 0.0})
        self.trc10 = defaultdict(lambda: {'cnt': 0, 'amt': 0.0})
        self.dlg = {'freeze_n': 0, 'unfreeze_n': 0, 'total_n': 0}
        self.addr_tags = defaultdict(lambda: {'freeze_n': 0, 'tags': set()})

    def read(self):
        """读取 CSV 文件"""
        self.rows = load_csv(self.csv_path)
        if not self.rows:
            raise ValueError("CSV 为空")
        # 识别类型
        if "contractType" in self.rows[0]:
            self.fmt = "transaction"
        # 时间戳与地址
        from datetime import datetime
        for r in self.rows:
            ts = r.get("blockTime(UTC)", "")
            if ts:
                try:
                    self.timestamps.append(datetime.strptime(ts, "%Y/%m/%d %H:%M:%S"))
                except ValueError:
                    pass
            for k in ("from", "to"):
                a = r.get(k, "")
                if a and a != USDT_CONTRACT:
                    self.all_addrs.add(a)

    def process(self):
        """核心统计"""
        for r in self.rows:
            frm = r.get("from", "")
            to = r.get("to", "")
            sym = r.get("symbol", "")
            val = r.get("_value", 0.0)
            ct = r.get("contractType", "")

            # 记录所有地址
            if frm:
                self.all_addrs.add(frm)
            if to:
                self.all_addrs.add(to)

            if self.fmt == "token_transfer":
                if sym == "USDT" and r.get("tokenAddress", "").strip() == USDT_CONTRACT:
                    frm_l = (frm or "").lower()
                    to_l = (to or "").lower()
                    if self.target:
                        # 目标地址视角：转入目标 = in，目标转出 = out
                        if to_l == self.target and frm_l != self.target:
                            self.usdt_in += val
                            self.usdt_in_n += 1
                            self.cp[frm_l]['in'] += val
                            self.cp[frm_l]['cnt'] += 1
                        elif frm_l == self.target and to_l != self.target:
                            self.usdt_out += val
                            self.usdt_out_n += 1
                            self.cp[to_l]['out'] += val
                            self.cp[to_l]['cnt'] += 1
                    else:
                        # 无目标地址：记录所有对手方（from 视角）
                        if frm and to and to_l != USDT_CONTRACT.lower():
                            self.cp[frm_l]['out'] += val
                            self.cp[frm_l]['cnt'] += 1
                            self.usdt_out += val
                            self.usdt_out_n += 1
                        if to and frm and frm_l != USDT_CONTRACT.lower():
                            self.cp[to_l]['in'] += val
                            self.cp[to_l]['cnt'] += 1
                            self.usdt_in += val
                            self.usdt_in_n += 1
                elif sym and sym != "USDT":
                    self.scam[sym]['cnt'] += 1
                    self.scam[sym]['amt'] += val
            else:  # transaction
                if ct == "TransferAssetContract":
                    # 2026-09-06 修正（SKILL v2.4 铁律 #2）：symbol=BL 是 TRC-10 垃圾币名，不是 Tether 冻结标记——
                    # 归入 trc10 垃圾币统计，绝不 ++freeze_n（曾致朋友案误判"BL 封条=冻结时间"）
                    if sym:
                        self.trc10[sym]['cnt'] += 1
                        self.trc10[sym]['amt'] += val
                    if sym == "BL":
                        self.addr_tags[to]['tags'].add("垃圾币BL")  # 仅标记非冻结；freeze_n 不增加
                elif ct == "DelegateResourceContract":
                    self.dlg['freeze_n'] += 1
                elif ct == "UnDelegateResourceContract":
                    self.dlg['unfreeze_n'] += 1
                self.dlg['total_n'] = self.dlg['freeze_n'] + self.dlg['unfreeze_n']

                # 诈骗代币检测
                up = sym.upper()
                if any(kw in up for kw in ["UNFREEZE", "UNLOCK", "UNBANNED"]) or "解封" in sym:
                    self.scam[sym]['cnt'] += 1
                    self.scam[sym]['amt'] += val

    def run(self):
        """便捷方法：read + process"""
        self.read()
        self.process()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--address", default=None, help="目标地址（默认取出现最多地址）")
    ap.add_argument("--type", choices=["token", "transaction"], default=None)
    args = ap.parse_args()

    rows = load_csv(args.csv_path)
    if not rows:
        print("错误: CSV 为空")
        sys.exit(1)

    ctype = args.type or detect_type(rows)
    # 目标地址: 优先 --address，否则统计出现最多的地址
    if args.address:
        target = args.address
    else:
        cnt = defaultdict(int)
        for r in rows:
            cnt[r.get("from", "")] += 1
            cnt[r.get("to", "")] += 1
        # 取出现次数最多的地址（按计数）
        target = ""
        best = -1
        for a, c in cnt.items():
            if c > best:
                best = c
                target = a
        if not target:
            target = rows[0].get("from", "")
    target_l = target.lower()

    times = [r.get("blockTime(UTC)", "") for r in rows if r.get("blockTime(UTC)")]
    times.sort()
    start = times[0] if times else "?"
    end = times[-1] if times else "?"

    print("=== 基础统计 ===")
    print(f"总交易数: {len(rows)} | 时间范围: {start} ~ {end} | 类型: {ctype}")
    print(f"目标地址: {target}")

    # 代币分布
    tokens = defaultdict(int)
    for r in rows:
        tokens[r.get("symbol", "(空)")] += 1
    dist = ", ".join(f"{k}:{v}" for k, v in sorted(tokens.items(), key=lambda x: -x[1])[:10])
    print(f"代币分布: {dist}")

    if ctype == "token":
        usdt = [r for r in rows if r.get("symbol") == "USDT"
                and r.get("tokenAddress", "").strip() == USDT_CONTRACT]
        inflow = sum(r["_value"] for r in usdt if r.get("to", "").lower() == target_l)
        outflow = sum(r["_value"] for r in usdt if r.get("from", "").lower() == target_l)
        print("")
        print("=== USDT 进出 ===")
        print(f"转入总额: {fmt(inflow)} | 转出总额: {fmt(outflow)} | 净额: {fmt(inflow - outflow)}")
        print(f"USDT 交易笔数: {len(usdt)}")

        # 按天流量 TOP10
        daily_in, daily_out = defaultdict(float), defaultdict(float)
        for r in usdt:
            day = r.get("blockTime(UTC)", "")[:10]
            if r.get("to", "").lower() == target_l:
                daily_in[day] += r["_value"]
            if r.get("from", "").lower() == target_l:
                daily_out[day] += r["_value"]
        days = sorted(set(list(daily_in.keys()) + list(daily_out.keys())),
                      key=lambda d: -(daily_in.get(d, 0) + daily_out.get(d, 0)))[:10]
        print("按天流量 TOP10 (日期, 转入, 转出):")
        for d in days:
            print(f"  {d}  入 {fmt(daily_in.get(d, 0))}  出 {fmt(daily_out.get(d, 0))}")

        # 对手方双向 TOP15
        in_c, out_c = defaultdict(float), defaultdict(float)
        in_n, out_n = defaultdict(int), defaultdict(int)
        for r in usdt:
            if r.get("to", "").lower() == target_l:
                f = r.get("from", "")
                in_c[f] += r["_value"]; in_n[f] += 1
            if r.get("from", "").lower() == target_l:
                t = r.get("to", "")
                out_c[t] += r["_value"]; out_n[t] += 1
        print("")
        print("=== 对手方 TOP15 (转入) ===")
        for a, v in sorted(in_c.items(), key=lambda x: -x[1])[:15]:
            print(f"  {a}: {in_n[a]}笔 {fmt(v)} U")
        print("=== 对手方 TOP15 (转出) ===")
        for a, v in sorted(out_c.items(), key=lambda x: -x[1])[:15]:
            print(f"  {a}: {out_n[a]}笔 {fmt(v)} U")

    # 冻结/诈骗标记扫描（全列）
    print("")
    print("=== 冻结/诈骗标记 ===")
    found = 0
    for r in rows:
        sym = r.get("symbol", "")
        if any(kw in sym.upper() for kw in ["UNFREEZE", "UNLOCK", "UNBANNED", "BL"]) \
           or any(kw in sym for kw in ["解封", "unfrozen"]):
            found += 1
            print(f"  {r.get('blockTime(UTC)', '?')}  {sym}  {r.get('value', '')}  "
                  f"from:{r.get('from', '')[:12]}  Tx:{short_hash(r.get('Tx Hash', ''))}")
    if not found:
        print("  （未发现冻结/诈骗标记代币）")

    if ctype == "transaction":
        # BL 封条（TransferAssetContract 中的 BL）
        print("")
        print("=== BL 封条记录 ===")
        bl = [r for r in rows if r.get("symbol") == "BL"]
        if bl:
            for r in bl:
                print(f"  {r.get('blockTime(UTC)', '?')}  BL {r.get('value', '')}  "
                      f"来源:{r.get('from', '')}  Tx:{short_hash(r.get('Tx Hash', ''))}")
        else:
            print("  （本 CSV 未发现 BL 标记）")

        # 非 USDT/TRX 代币（TRC-10）
        print("")
        print("=== 其他非标准代币 ===")
        others = [(r.get('blockTime(UTC)', '?'), r.get('symbol', ''), r.get('value', ''),
                   r.get('from', '')[:12]) for r in rows
                  if r.get("contractType") == "TransferAssetContract" and r.get("symbol") != "BL"]
        if others:
            for t, s, v, f in others:
                print(f"  {t}  {s}  {v}  from:{f}")
        else:
            print("  （无）")

        # 能量/带宽委托
        d_cnt = sum(1 for r in rows if r.get("contractType") == "DelegateResourceContract")
        u_cnt = sum(1 for r in rows if r.get("contractType") == "UnDelegateResourceContract")
        d_trx = sum(r["_value"] for r in rows if r.get("contractType") == "DelegateResourceContract")
        u_trx = sum(r["_value"] for r in rows if r.get("contractType") == "UnDelegateResourceContract")
        print("")
        print("=== 能量/带宽委托 ===")
        print(f"委托: {d_cnt}次 {fmt(d_trx)} TRX | 解除: {u_cnt}次 {fmt(u_trx)} TRX | 合计: {d_cnt + u_cnt}次")

        # 关联地址（可选 --address 指定后）
        if args.address:
            print("")
            print("=== 关联地址交易 ===")
            rel = [r for r in rows if target_l in (r.get("from", "").lower(), r.get("to", "").lower())]
            for r in sorted(rel, key=lambda x: x.get("blockTime(UTC)", ""))[-30:]:
                d = "→" if r.get("from", "").lower() == target_l else "←"
                print(f"  {r.get('blockTime(UTC)', '?')} {d} {r.get('value', '')} "
                      f"{r.get('symbol', '')} {r.get('contractType', '')} Tx:{short_hash(r.get('Tx Hash', ''))}")

    print("")
    print("=== 统计完成 ===")


if __name__ == "__main__":
    main()
