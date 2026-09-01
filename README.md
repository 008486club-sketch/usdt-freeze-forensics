# 🔍 USDT Freeze Forensics · 链上取证工作流

> **TRON/USDT 地址被 Tether 冻结？帮你查清楚：冻了多少钱、什么时候冻的、哪笔交易触发的、怎么申诉。**

TRON-chain USDT freeze investigation & appeal workflow — determine freeze time, trace tainted funds, identify trigger transactions, and prepare Tether appeals.

Quy trình điều tra đóng băng USDT trên TRON — xác định thời điểm đóng băng, truy nguồn dòng tiền, xác định giao dịch kích hoạt và chuẩn bị kháng nghị Tether.

---

## ✨ 为什么做这个项目

2026 年 8 月，一位越南华商的 USDT 钱包被 Tether 冻结了 **48.4 万 U**。我们花了三天完成全链路取证，并沉淀出这套可复用的工作流。**Tether 每月都在批量冻结地址**，而绝大多数受害者不知道——**每个痛点，我们都有对应的解法**：

| 痛点 | 解决方案（本工作流） |
| :--- | :--- |
| **① 冻结时间怎么看？** 受害者常以为钱包"突然就废了"，不知道具体哪天、哪一秒被冻 | **BL 封条定位法**：每个地址自己的 BanList 标记转入时间 = 该地址被冻结的**精确时间**（精确到秒）。真实案例中我们据此定位主账户冻结于 **2026-08-08 21:20:36 UTC**，并发现关联账户其实更早 38 天被冻——**改写整个案件的因果判断** |
| **② 是哪笔交易触发的？** 冻结前流水几十笔，不知道哪笔是"雷" | **毒源定位三步**：① 冻结前 72h 全量逐笔列出 → ② 锁定一次性马甲地址（此前零交互、冻结后消失）→ ③ 同批冻结地址交集分析。案例中最可疑触发交易 = 冻结前 38 小时入账的一笔大额 USDT（来自一次性地址） |
| **③ 为什么被冻？** OTC 中转商 / 过桥 / 关联标记分不清 | **画像建模**：全量统计 + 双向对手方排名（转入/转出 TOP15）+ 占比法验证因果。可识别职业 OTC 枢纽、秒进秒出过桥、能量委托批量操作等特征；**用数据说话，不冤枉任何一方** |
| **④ 怎么申诉？** 材料不会列、话术不会写、被拒了不知道怎么办 | **申诉材料包**：交易凭证 / KYC / 资金来源说明清单 + **稳妥化申诉话术模板**（避免绝对化措辞）+ 有利/不利证据预判（冻结金额与涉案规模比例、冻结后是否停手） |
| **⑤ 怎么识别二次诈骗？** 冻结后收到"UNFREEZE/解冻"代币，差点又被骗 | **假代币识别铁律**：先看合约地址再看 symbol——`U ≠ USDT`；UNFREEZE / UNLOCK / UNBANNED 全是骗子代币；**Tether 官方不会通过 TG 或链上备注联系你**。真实案例中识别出 5 种假解冻代币，阻止二次受骗 |

这套工作流已固化为**标准流程**：线上免费查询（官方合约级冻结检测）+ CSV 全量深度分析 + 诊断报告模板 + 申诉文书模板，**任何取证任务都可以直接套用**。

---

## 🚀 快速开始

```bash
# 方式一：在线检测（推荐客户使用）
# 启动完整产品（前端+API 一体）
cd api && python3 -m uvicorn api_server:app --host 0.0.0.0 --port 8902
# 打开 http://localhost:8902 输入地址即可诊断

# 方式二：CSV 深度分析（推荐取证使用）
# 1. 从 TronScan 导出地址的交易记录
#    https://tronscan.org/address/<地址>/transfers → Export CSV
# 2. 全量统计
python3 scripts/csv_analyzer.py TRON-tokenTransfer-<地址>--<时间戳>.csv
# 3. 生成诊断报告
python3 scripts/report_generator.py TRON-tokenTransfer-<地址>--<时间戳>.csv --address <地址> -o report.md
```

完整方法论见 `docs/WORKFLOW.md`。

---

## 📁 项目结构

```
usdt-freeze-forensics/
├── api/
│   └── api_server.py            # FastAPI 后端（TronGrid封装+风险评分+静态页）
├── web/
│   ├── index.html               # 首页（输入地址诊断）
│   ├── report.html              # 报告页（评分/时间线/资金流）
│   └── i18n.js                  # 三语字典（中/越/英）
├── docs/
│   ├── WORKFLOW.md              # 完整取证工作流（口径铁律）
│   └── CASE-STUDY-202608.md     # 实战案例复盘（脱敏）
├── scripts/
│   ├── csv_analyzer.py          # CSV 全量统计
│   ├── tron_api.py              # TronGrid API 封装
│   └── report_generator.py      # 报告生成
├── templates/
│   └── appeal-letter.md         # Tether 申诉信模板
└── PRODUCT_TASKS.md             # 产品任务卡（三兄弟分工）
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

## 📊 使用模式

- 线上查询 **完全免费**：`https://yuezhitong.com/usdt-check/`（TronGrid 最近100笔抽样，非全量）
- 全量深度分析：按本工作流自行导出 CSV 取证，或联系越智通科技商业合作
- 若服务帮到你，欢迎打赏支持（自愿，不构成服务合约）

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
