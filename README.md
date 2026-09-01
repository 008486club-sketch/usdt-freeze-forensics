# 🔍 USDT Freeze Forensics · 链上取证工作流

> **TRON/USDT 地址被 Tether 冻结？帮你查清楚：冻了多少钱、什么时候冻的、哪笔交易触发的、怎么申诉。**

TRON-chain USDT freeze investigation & appeal workflow — determine freeze time, trace tainted funds, identify trigger transactions, and prepare Tether appeals.

Quy trình điều tra đóng băng USDT trên TRON — xác định thời điểm đóng băng, truy nguồn dòng tiền, xác định giao dịch kích hoạt và chuẩn bị kháng nghị Tether.

---

## ✨ 为什么做这个项目

2026 年 8 月，一位越南华商的 USDT 钱包被 Tether 冻结了 48.4 万 U。我们花了三天完成全链路取证，并沉淀出这套可复用的工作流。**Tether 每月都在批量冻结地址**，而绝大多数受害者不知道：

- 冻结时间怎么看（BL 封条）
- 是哪笔交易触发的（毒源定位）
- 为什么被冻（OTC 枢纽 / 过桥 / 关联标记）
- 怎么申诉（材料 + 话术）
- 怎么识别二次诈骗（UNFREEZE 假代币）

这套工作流把这些全部固化成标准流程，**任何取证任务都可以直接套用**。

---

## 🚀 快速开始

```bash
# 1. 从 TronScan 导出地址的交易记录
#    https://tronscan.org/address/<地址>/transfers → Export CSV

# 2. 用 csv_analyzer.py 做全量统计（待阿兴交付）
python scripts/csv_analyzer.py TRON-tokenTransfer-<地址>--<时间戳>.csv

# 3. 按 SKILL 工作流解读，生成报告
```

完整方法论见 `docs/WORKFLOW.md`。

---

## 📁 项目结构

```
usdt-freeze-forensics/
├── docs/
│   ├── WORKFLOW.md              # 完整取证工作流（口径铁律）
│   └── CASE-STUDY-202608.md     # 实战案例复盘（脱敏）
├── scripts/
│   ├── csv_analyzer.py          # CSV 全量统计（开发中）
│   └── report_generator.py      # 报告生成（开发中）
├── templates/
│   └── appeal-letter.md         # Tether 申诉信模板
└── data/
    ├── high-risk-tokens.md      # 高风险代币库
    └── blacklist-db.csv         # 地址结论沉淀
```

---

## 📖 核心方法论（口径铁律）

1. **CSV 为准**：TronScan 导出的全量 CSV 是唯一可信底座，API 只补元信息
2. **BL 封条 = 冻结时间**：每个地址自己的 BanList 标记时间 = 冻结时间
3. **U ≠ USDT**：收到带 "unfrozen" 备注的代币先查合约地址，假币是二次诈骗
4. **事实 vs 推断**：所有结论必须标注证据来源，禁止臆断
5. **占比法验证因果**：金额占比决定是"供血方"还是"主犯"

---

## 🔒 合规声明

- 本项目仅提供**链上数据分析方法论**，不构成法律意见
- 不承诺任何解冻结果
- 打赏是自愿支持，不构成服务合约
- 商业合作请联系越智通科技

---

## ☕ 支持我们

如果这套工作流帮到了你，可以请我们喝杯咖啡：

**USDT (TRC-20)**: `TTYu42MKHtNJXAbuDpeFdoaiwaeZNFdrVT`（主力通道，零费率，无国界）

**其他方式**: 聚合打赏页 `donatr.ee/...`（BTC/ETH/SOL/信用卡，待开放）· GitHub Sponsors（国际开发者）

> ⚠️ 警告：任何声称"付费解冻"的个人/TG 群都是诈骗。Tether 官方不会通过 Telegram 联系你。本仓库作者也不会主动私聊你要求付费。
>
> 打赏是自愿支持，不构成服务合约；商业合作请联系官网。

---

## 📬 联系

**越智通科技服务有限公司**（VietTriTong Technology Services Co., Ltd.）
- 官网：https://yuezhitong.com
- 业务范围：越南市场数字化服务 / 跨境电商 / AI 解决方案

---

*越智通AI决策助手 · 阿智 · 2026-08-31*
