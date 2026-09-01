# 🎯 阿兴任务卡：csv_analyzer.py 自动化分析脚本

**来自：** 阿智（越智通AI决策助手）
**日期：** 2026-08-31
**优先级：** 高（流水线自动化关键路径）

---

## 任务目标

写一个 Python 脚本 `csv_analyzer.py`，输入 TronScan 导出的 CSV，输出标准化的全量统计结果，供取证分析直接使用。

## 输入（两份真实样例，必须跑通）

1. **老板 tokenTransfer CSV（资金流）**：
   `/home/admin/.hermes-web-ui/upload/default/f922112bd60cdd4c.csv`（522 行）
   - 表头：`Tx Hash,blockHeight,blockTime(UTC+8),blockTime(UTC),from,to,value,symbol,tokenAddress,isConfirm`

2. **朋友 transaction CSV（冻结时间/能量信号）**：
   `/home/admin/.hermes-web-ui/upload/default/d4a97a9bf0644cb5.csv`（2544 行）
   - 表头：`Tx Hash,blockHeight,blockTime(UTC+8),blockTime(UTC),from,to,value,symbol,contractType,status`

## 脚本要求

### 用法
```bash
python3 csv_analyzer.py <csv路径> [--address 目标地址] [--type token|transaction]
```

- 自动识别类型（看表头有无 contractType），也可手动指定
- `--address` 指定分析的目标地址（默认取 CSV 中出现最多的地址）

### 输出（stdout，格式固定，阿智验收用）

```
=== 基础统计 ===
总交易数: N | 时间范围: START ~ END | 代币分布: {symbol: 笔数}

=== USDT 进出（仅 token 类型） ===
转入总额: X | 转出总额: Y | 净额: Z
按天流量 TOP10（日期, 转入, 转出）

=== 对手方 TOP15（双向，仅 token 类型） ===
[转入 TOP15] 地址: 笔数, 金额
[转出 TOP15] 地址: 笔数, 金额

=== 冻结标记（transaction 类型重点） ===
BL 封条: 时间(UTC), 金额, 来源地址, TxHash
解冻诈骗代币(UNFREEZE/UNLOCK/UNBANNED/解封): 列出
其他非标准代币: 列出

=== 关联地址 ===
指定关联地址的交易（时间, 方向, 金额, 对手方, TxHash）
```

### 关键规则（必须遵守）
1. **Tx Hash 显示格式**：前 12 位 + `...` + 后 8 位（如 `5427a910...ea653ad8`）
2. **时间统一用 UTC**（CSV 里 `blockTime(UTC)` 列），不要用 UTC+8
3. **USDT 判定**：`symbol == 'USDT'` 且 `tokenAddress == 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'`（token 类型）
4. **金额单位**：CSV value 已经是 USDT 数值（如 270000），直接 float，保留 2 位小数
5. **transaction 类型**：
   - `TriggerSmartContract` 行 = USDT 转账信号（金额显示 0，不统计进 USDT 进出）
   - `TransferAssetContract` 行 = TRC-10（BL 封条、诈骗币、垃圾币都在这里，必须列出）
   - `DelegateResourceContract` / `UnDelegateResourceContract` 行 = 能量委托（统计次数和总 TRX）
6. **编码**：UTF-8，输出中文，兼容 Windows 终端（避免 emoji，用纯文本 `===`/`---`）

### 验收标准（阿智跑完会核对）
- [ ] 两份样例 CSV 都能跑通，无报错
- [ ] 老板 CSV：USDT 总流水 ≈ 48,097,316.99；转入 ≈ 24,290,864.49；转出 ≈ 23,806,452.50
- [ ] 老板 CSV：TFDM... 是最大转入方（78笔 956万）——能对上
- [ ] 朋友 CSV：能找到 BL 61.781241 @ 2026-07-01 18:04:03 UTC
- [ ] 朋友 CSV：能量委托次数 ≈ 878
- [ ] 输出格式与上面模板一致

## 交付物

- `csv_analyzer.py`（单文件，无第三方依赖，只用 csv/datetime/collections）
- 放到：`/home/admin/yuezhi_tong/usdt-freeze-forensics/scripts/csv_analyzer.py`

## 注意事项

- 不要改动两份样例 CSV（只读）
- 脚本要健壮：空行、缺列、非数字 value 都能处理
- 完成后自己跑一遍，把 stdout 结果贴回来，阿智验收

---

**阿智验收铁律：** 任何数字必须能指到 CSV 具体行/哈希；格式与模板不一致直接打回。
