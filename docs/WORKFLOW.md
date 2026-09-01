# 📖 USDT 冻结取证工作流（完整版）

> 基于 2026-08 实战案例沉淀，供内部取证与外部参考。

---

## Step 0: 获取全量数据（先做这个！）

**为什么必须用 CSV：**
- TronGrid `transactions/trc20` API 只返回最近 N 笔（抽样），**不能**据此判断地址活跃度
- TronScan 网页动态加载，直接抓取只能拿到空表格
- **CSV 是官方导出的全量记录，每行可复核，是唯一可信底座**

**操作：**
1. 打开 `https://tronscan.org/address/<地址>/transfers`
2. 点 Export 下载 token transfer CSV（文件名 `TRON-tokenTransfer-<地址>--<时间戳>.csv`）
3. 如需查冻结时间/能量信号，再导出 transaction CSV（`TRON-transaction-<地址>--<时间戳>.csv`）

**两类 CSV 的区别：**

| 文件 | 表头 | 用途 |
| :--- | :--- | :--- |
| tokenTransfer | Tx Hash,blockHeight,blockTime(UTC+8),blockTime(UTC),from,to,value,symbol,tokenAddress,isConfirm | 资金流分析（有 USDT 金额） |
| transaction | Tx Hash,blockHeight,blockTime(UTC+8),blockTime(UTC),from,to,value,symbol,contractType,status | 冻结时间(BL) / 能量信号 / TRC-10 |

---

## Step 1: 验证冻结事实

用 web_search 查：
- `"<地址>" blacklist frozen site:trustsniffer.com OR site:blocklist.fyi`
- 工具：TrustSniffer / BlockchainAnalysis.io / blocklist.fyi

确认：是否在黑名单、官方冻结时间、金额。

---

## Step 2: 用 BL 封条定位冻结时间（铁律）

在 **transaction CSV** 里搜 `TransferAssetContract` 行中 `symbol=BL`（BanList）的记录：

- **该记录的时间 = 该地址被 Tether 冻结的时间**（UTC）
- **该记录的金额 ≈ 被冻结的 USDT 余额**（可能有 ±30U 精度差）

⚠️ **禁止假设"同秒冻结 = 同批/同案"**。每个地址要查自己的 BL 封条。
实战案例：关联方 A（朋友）BL 在 2026-07-01，主账户 B（老板）BL 在 2026-08-08——**差 38 天**，因果方向完全相反。（注：案例完整复盘见 `docs/CASE-STUDY-202608.md`，公开版已脱敏，真实地址用 关联方A/主账户B 代称）

---

## Step 3: TRC-10 "泥巴效应"

- TRC-10 代币可**被动入账**（无需接收方签名）
- 即使当事人声称"没收过"，链上存在即构成"环境指纹"
- 博彩/灰产代币（见 `data/high-risk-tokens.md`）：DuGame、Gas35、U125com、SUNGAME 等
- 给"满身泥巴"的地址转大钱 = 被判定为高风险关联方

---

## Step 4: 资金流画像

用 `csv_analyzer.py` 对 tokenTransfer CSV 做全量统计：
- USDT 进出总额
- 按天流量（识别 OTC 枢纽：单日 200 万+）
- 对手方双向 TOP15（**必须双向都算**）
- 关联地址交易

**关键解读：**
- 总流水 vs 冻结额：冻结额只是"冻结瞬间账上存量"，不是全部身家
- 双向交易对手 vs 单向主要资金对手方：某地址既转入又大量转出 = 双向对手方（"供血方"含因果判断，禁用）
- OTC 枢纽画像：日均 50 万+、30+ 对手方、大量 1.01/1.49901 零头测试转账

---

## Step 5: 冻结关联分析（非因果判断，铁律 #8）

- 冻结前 72 小时交易逐笔列出（**只陈述链上事实**，禁止对"最后一笔大额入账"做因果断言）
- 时间邻近 ≠ 因果：大额入账 ≠ 冻结原因；来源未被官方冻结 ≠ 可认定风险源
- 同批冻结地址间查直接交集（有交集 = 可证资金关系；无交集 = 仅推断同案）
- 标准结论：**目前只能证明资金关系，不能证明冻结因果**

---

## Step 6: 识别二次诈骗（必须警告用户）

冻结后地址收到以下代币 = **骗子**：
- `UNFREEZE` / `UNLOCK` / `UNBANNED` / `解封UNFREEZE`（常带 TG 号）
- `unfrozen U <代号>` 备注的假币（symbol 是 U 不是 USDT）

**铁律：Tether 官方不会用链上备注或 TG 联系用户。任何"付费解冻"都是诈骗。**

---

## Step 7: 构建申诉

见 `templates/appeal-letter.md`（稳妥化措辞 v2.1）。

**有利证据：**
- 冻结金额与涉案规模不成比例（身份标记非资金扣押）
- 冻结后立即停止操作
- 真实贸易合同/发票

**不利证据（需准备解释）：**
- OTC 高频操作（能量租赁 878 次等）
- 秒进秒出过桥
- 高危对手方交互

---

## ✅ 交付标准

- 报告顶部：数据源(CSV+条数)、时间范围、统计方法(全量非抽样)
- 关键数字标注「可复核」+ 交易哈希定位
- 结论分「链上事实」与「推断/建议」两栏
- 报告署名：越智通AI决策助手 · 阿智

---

*越智通AI决策助手 · 阿智 · 2026-08-31*
