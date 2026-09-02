#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify.py — 埋点数据隐私断言（查线上 JSONL events-*.jsonl）。

断言:
  1. 事件文件无 Tron 地址明文（无 T 开头 34 字符 base58 串）
  2. 无 from_address/to_address/address 等明文地址字段
  3. addr_fp 恒为 8 位 hex（sha256 前8）；uv 恒为 10 位 hex（HMAC 日桶）
  4. ev 在白名单内；score 在 [0,100]
用法: python3 verify.py [data_dir]   (默认 /var/lib/usdt-forensics/analytics)
"""
import os
import re
import sys

ADDR_RE = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")
EVENTS = {"page_view", "page_leave", "query_start", "query_done", "query_error",
          "tip_copy", "share_click", "lang_switch", "report_expand"}
HEX8 = re.compile(r"^[0-9a-f]{8}$")
HEX10 = re.compile(r"^[0-9a-f]{10}$")

DATA_DIR = sys.argv[1] if len(sys.argv) > 1 else "/var/lib/usdt-forensics/analytics"


def check():
    errors = []
    checked = 0
    if not os.path.isdir(DATA_DIR):
        return True, ["目录不存在（首次运行 OK）：" + DATA_DIR], 0
    for fn in sorted(os.listdir(DATA_DIR)):
        if not fn.startswith("events-") or not fn.endswith(".jsonl"):
            continue
        p = os.path.join(DATA_DIR, fn)
        with open(p, encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                checked += 1
                try:
                    import json
                    e = json.loads(line)
                except ValueError:
                    errors.append(f"{fn}:{ln} 非 JSON")
                    continue
                if not isinstance(e, dict):
                    errors.append(f"{fn}:{ln} 非对象")
                    continue
                # 1) 任何值不得是 Tron 地址明文
                for k, v in e.items():
                    if isinstance(v, str) and ADDR_RE.match(v):
                        errors.append(f"{fn}:{ln} 地址明文 {k}")
                # 2) 不得有明文地址字段名
                for bad in ("from_address", "to_address", "address"):
                    if bad in e:
                        errors.append(f"{fn}:{ln} 明文地址字段 {bad}")
                # 3) 指纹格式
                if "addr_fp" in e and not HEX8.match(str(e["addr_fp"])):
                    errors.append(f"{fn}:{ln} addr_fp 非8hex")
                if "uv" in e and not HEX10.match(str(e["uv"])):
                    errors.append(f"{fn}:{ln} uv 非10hex")
                # 4) ev 白名单 / score 范围
                if e.get("ev") not in EVENTS:
                    errors.append(f"{fn}:{ln} 未知 ev={e.get('ev')}")
                s = e.get("score")
                if s is not None and not (0 <= float(s) <= 100):
                    errors.append(f"{fn}:{ln} score 越界 {s}")
    return (len(errors) == 0, errors, checked)


def main():
    passed, errors, checked = check()
    print("=== 埋点隐私断言 verify.py ===")
    print(f"检查事件行: {checked}")
    if passed:
        print("✓ PASS: 无地址明文 / 指纹格式正确 / ev 白名单 / score 合规")
        return 0
    print(f"✗ FAIL: {len(errors)} 处问题")
    for e in errors[:20]:
        print("  -", e)
    return 1


if __name__ == "__main__":
    sys.exit(main())
