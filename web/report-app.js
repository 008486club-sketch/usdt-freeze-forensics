/* Report page logic + mock data */
let currentLang = 'zh';

/* ===== Mock Data ===== */
const MOCK = {
  address: 'TYDzsYUEpGYyKbNYR5kFmKjXoEfCw66moo',
  score: 72,
  risk: 'high',
  created: '2024-03-15',
  txCount: 847,
  counterparties: [
    { addr: 'Binance Hot...', inAmt: 125000, outAmt: 98000 },
    { addr: 'TKnK...x9Qm', inAmt: 15000, outAmt: 0 },
    { addr: 'Shopee Pay...', inAmt: 67000, outAmt: 45000 },
    { addr: 'OTC Desk A...', inAmt: 32000, outAmt: 28000 },
    { addr: 'DeFi Pool...', inAmt: 8000, outAmt: 12000 },
    { addr: 'Personal B...', inAmt: 5500, outAmt: 3200 }
  ],
  transactions: [
    { time: '2026-01-18 14:05', dir: 'in', amt: 15000, cp: 'TKnK...x9Qm', hash: 'a1b2c3...f47e', flag: true },
    { time: '2026-01-15 09:30', dir: 'out', amt: 8500, cp: 'Binance Hot...', hash: 'd5e6f7...a82b', flag: false },
    { time: '2026-01-10 16:22', dir: 'in', amt: 3200, cp: 'Shopee Pay...', hash: 'c9d0e1...b34c', flag: false },
    { time: '2025-12-28 11:45', dir: 'out', amt: 12000, cp: 'OTC Desk A...', hash: 'f2g3h4...c56d', flag: false },
    { time: '2025-12-15 08:00', dir: 'in', amt: 6700, cp: 'Shopee Pay...', hash: 'i7j8k9...d78e', flag: false },
    { time: '2025-11-20 19:33', dir: 'in', amt: 45000, cp: 'Binance Hot...', hash: 'l0m1n2...e90f', flag: false },
    { time: '2025-10-05 14:18', dir: 'out', amt: 5000, cp: 'DeFi Pool...', hash: 'o3p4q5...f12g', flag: false },
    { time: '2025-08-12 10:00', dir: 'in', amt: 25000, cp: 'Binance Hot...', hash: 'r6s7t8...g34h', flag: false }
  ]
};

/* ===== i18n additions for report ===== */
const REPORT_I18N = {
zh: {
  brand:"USDT 冻结取证",addrLabel:"诊断地址",
  metaCreated:"创建时间：2024-03-15",metaTx:"交易总数：847",metaFirst:"首笔：2024-03-15",metaLast:"末笔：2026-07-22",
  riskLabel:"风险评分",verdictHigh:"⚠️ 高风险 — 建议深度分析",verdictMid:"⚡ 中风险 — 建议关注",verdictLow:"✅ 低风险",
  tlTitle:"冻结时间线",
  tl1t:"地址创建",tl1d:"首次收到 500 USDT 转入，来源为 Binance 热钱包",
  tl2t:"正常交易期",tl2d:"累计 623 笔交易，主要为电商收款和 OTC 兑换，对手方分散",
  tl3t:"高风险转入",tl3d:"收到来自 TKnK...x9Qm 的 15,000 USDT，该地址已被标记为涉案地址",
  tl4t:"地址被标记冻结",tl4d:"交易所收到链上风控警报，限制该地址提币和交易",
  tl5t:"冻结后",tl5d:"地址状态为只读，无法转出资产。共 224 笔后续交易尝试均被拒绝",
  flowTitle:"资金流向（TOP 对手方）",legIn:"转入",legOut:"转出",
  txTitle:"关键交易记录",txTime:"时间",txDir:"方向",txAmt:"金额 (USDT)",txCp:"对手方",txHash:"TxHash",
  dirIn:"转入",dirOut:"转出",flagWarn:"⚠ 涉案",
  appealT:"申诉建议",
  a1t:"收集交易凭证",a1d:"整理与 TKnK...x9Qm 交易的完整记录：聊天记录、合同、发票、物流单据，证明交易背景真实合法。",
  a2t:"准备 KYC 材料",a2d:"更新交易所 KYC 信息，提供身份证明、地址证明、资金来源说明。确保与链上行为一致。",
  a3t:"提交申诉工单",a3d:"通过交易所官方渠道提交申诉，附上本报告和所有支持材料。保持耐心，跟进处理进度。",
  a4t:"寻求法律支持",a4d:"如申诉被拒，考虑委托专业律师发函或向监管机构投诉。保留所有沟通记录作为证据。",
  ctaT:"需要专业申诉协助？",ctaS:"我们的团队可以帮您准备材料、撰写文书、全程跟进",ctaBtn:"联系申诉顾问",
  tipL:"USDT-TRC20 打赏地址",tipC:"点击复制",
  footN:"本服务基于区块链公开数据，不提供法律建议。",
  toastCopy:"地址已复制到剪贴板"
},
vi: {
  brand:"Điều tra USDT đóng băng",addrLabel:"Địa chỉ chẩn đoán",
  metaCreated:"Tạo: 2024-03-15",metaTx:"Tổng GD: 847",metaFirst:"Đầu: 2024-03-15",metaLast:"Cuối: 2026-07-22",
  riskLabel:"Điểm rủi ro",verdictHigh:"⚠️ Rủi ro cao — Nên phân tích sâu",verdictMid:"⚡ Rủi ro trung bình",verdictLow:"✅ Rủi ro thấp",
  tlTitle:"Dòng thời gian đóng băng",
  tl1t:"Tạo địa chỉ",tl1d:"Nhận 500 USDT đầu tiên từ ví nóng Binance",
  tl2t:"Giao dịch bình thường",tl2d:"623 giao dịch, chủ yếu thương mại điện tử và OTC",
  tl3t:"Chuyển tiền rủi ro cao",tl3d:"Nhận 15.000 USDT từ TKnK...x9Qm, địa chỉ bị đánh dấu liên quan vụ án",
  tl4t:"Địa chỉ bị đóng băng",tl4d:"Sàn nhận cảnh báo rủi ro, hạn chế rút và giao dịch",
  tl5t:"Sau đóng băng",tl5d:"Chỉ đọc, không thể chuyển. 224 lần thử bị từ chối",
  flowTitle:"Dòng tiền (TOP đối tác)",legIn:"Chuyển vào",legOut:"Chuyển ra",
  txTitle:"Giao dịch quan trọng",txTime:"Thời gian",txDir:"Hướng",txAmt:"Số tiền (USDT)",txCp:"Đối tác",txHash:"TxHash",
  dirIn:"Vào",dirOut:"Ra",flagWarn:"⚠ Liên quan",
  appealT:"Gợi ý khiếu nại",
  a1t:"Thu thập chứng từ",a1d:"Tổng hợp đầy đủ giao dịch với TKnK...x9Qm: chat, hợp đồng, hóa đơn, vận đơn.",
  a2t:"Chuẩn bị KYC",a2d:"Cập nhật KYC sàn, cung cấp CMND, bằng địa chỉ, giải trình nguồn tiền.",
  a3t:"Gửi khiếu nại",a3d:"Gửi qua kênh chính thức của sàn, kèm báo cáo và tài liệu.",
  a4t:"Hỗ trợ pháp lý",a4d:"Nếu bị từ chối, xem xét thuê luật sư hoặc khiếu nại cơ quan quản lý.",
  ctaT:"Cần hỗ trợ khiếu nại?",ctaS:"Đội ngũ chúng tôi sẵn sàng giúp đỡ",ctaBtn:"Liên hệ tư vấn",
  tipL:"Địa chỉ USDT-TRC20",tipC:"Nhấn sao chép",
  footN:"Dịch vụ dựa trên dữ liệu blockchain công khai, không phải tư vấn pháp lý.",
  toastCopy:"Đã sao chép địa chỉ"
},
en: {
  brand:"USDT Freeze Forensics",addrLabel:"Diagnosed Address",
  metaCreated:"Created: 2024-03-15",metaTx:"Total TXs: 847",metaFirst:"First: 2024-03-15",metaLast:"Last: 2026-07-22",
  riskLabel:"Risk Score",verdictHigh:"⚠️ High Risk — Deep analysis recommended",verdictMid:"⚡ Medium Risk — Monitor",verdictLow:"✅ Low Risk",
  tlTitle:"Freeze Timeline",
  tl1t:"Address Created",tl1d:"First received 500 USDT from Binance hot wallet",
  tl2t:"Normal Trading Period",tl2d:"623 transactions, mainly e-commerce and OTC, diverse counterparties",
  tl3t:"High-risk Inflow",tl3d:"Received 15,000 USDT from TKnK...x9Qm, flagged as involved address",
  tl4t:"Address Flagged & Frozen",tl4d:"Exchange received on-chain risk alert, restricted withdrawals and trading",
  tl5t:"Post-freeze",tl5d:"Address is read-only, cannot transfer. 224 subsequent attempts rejected",
  flowTitle:"Fund Flow (TOP Counterparties)",legIn:"Inflow",legOut:"Outflow",
  txTitle:"Key Transactions",txTime:"Time",txDir:"Direction",txAmt:"Amount (USDT)",txCp:"Counterparty",txHash:"TxHash",
  dirIn:"IN",dirOut:"OUT",flagWarn:"⚠ Flagged",
  appealT:"Appeal Recommendations",
  a1t:"Collect Transaction Records",a1d:"Gather complete records with TKnK...x9Qm: chats, contracts, invoices, shipping docs to prove legitimacy.",
  a2t:"Prepare KYC Materials",a2d:"Update exchange KYC, provide ID, address proof, source of funds explanation.",
  a3t:"Submit Appeal Ticket",a3d:"File appeal through official exchange channel with this report and all supporting materials.",
  a4t:"Seek Legal Support",a4d:"If appeal is rejected, consider hiring a lawyer or filing with regulators. Keep all records.",
  ctaT:"Need Professional Appeal Help?",ctaS:"Our team can prepare documents and follow up for you",ctaBtn:"Contact Appeal Advisor",
  tipL:"USDT-TRC20 Tip Address",tipC:"Click to copy",
  footN:"This service is based on public blockchain data and does not constitute legal advice.",
  toastCopy:"Address copied to clipboard"
}
};

/* Merge report i18n into main */
Object.keys(REPORT_I18N).forEach(lang => {
  if (I18N[lang]) Object.assign(I18N[lang], REPORT_I18N[lang]);
});

/* ===== Functions ===== */
function setLang(lang) {
  currentLang = lang;
  document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`.lang-btn[onclick="setLang('${lang}')"]`).classList.add('active');
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const val = I18N[lang] && I18N[lang][key];
    if (val) el.innerHTML = val;
  });
  document.documentElement.lang = lang === 'zh' ? 'zh' : lang === 'vi' ? 'vi' : 'en';
  renderFlow();
  renderTx();
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

function copyA() {
  navigator.clipboard.writeText('TTYu42MKHtNJXAbuDpeFdoaiwaeZNFdrVT').then(() => {
    showToast(I18N[currentLang].toastCopy || 'Copied!');
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = 'TTYu42MKHtNJXAbuDpeFdoaiwaeZNFdrVT';
    document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
    showToast(I18N[currentLang].toastCopy || 'Copied!');
  });
}

function renderFlow() {
  const chart = document.getElementById('flowChart');
  const maxAmt = Math.max(...MOCK.counterparties.map(c => Math.max(c.inAmt, c.outAmt)));
  const t = I18N[currentLang];
  chart.innerHTML = MOCK.counterparties.map(c => {
    const inW = Math.max((c.inAmt / maxAmt) * 100, c.inAmt > 0 ? 3 : 0);
    const outW = Math.max((c.outAmt / maxAmt) * 100, c.outAmt > 0 ? 3 : 0);
    return `<div class="flow-row">
      <div class="flow-label" title="${c.addr}">${c.addr}</div>
      <div class="flow-bars">
        <div class="flow-bar in" style="width:${inW}%"><div class="flow-tip">${t.dirIn || 'IN'} ${c.inAmt.toLocaleString()} USDT</div></div>
        <div class="flow-bar out" style="width:${outW}%"><div class="flow-tip">${t.dirOut || 'OUT'} ${c.outAmt.toLocaleString()} USDT</div></div>
      </div>
    </div>`;
  }).join('');
}

function renderTx() {
  const body = document.getElementById('txBody');
  const t = I18N[currentLang];
  body.innerHTML = MOCK.transactions.map(tx => {
    const dirClass = tx.dir === 'in' ? 'in' : 'out';
    const dirText = tx.dir === 'in' ? (t.dirIn || 'IN') : (t.dirOut || 'OUT');
    const flag = tx.flag ? ` <span style="color:var(--red);font-size:12px">${t.flagWarn || '⚠ Flagged'}</span>` : '';
    return `<tr>
      <td>${tx.time}</td>
      <td><span class="tx-dir ${dirClass}">${dirText}</span>${flag}</td>
      <td style="font-weight:600">${tx.amt.toLocaleString()}</td>
      <td class="tx-addr">${tx.cp}</td>
      <td class="tx-hash hide-mobile">${tx.hash}</td>
    </tr>`;
  }).join('');
}

function updateScore(score) {
  const circumference = 2 * Math.PI * 68; /* ~427 */
  const offset = circumference - (score / 100) * circumference;
  const fg = document.getElementById('scoreFg');
  const big = document.getElementById('scoreBig');
  fg.style.strokeDashoffset = offset;

  let color, verdictKey;
  if (score >= 70) { color = 'var(--red)'; verdictKey = 'verdictHigh'; }
  else if (score >= 40) { color = 'var(--ylw)'; verdictKey = 'verdictMid'; }
  else { color = 'var(--grn)'; verdictKey = 'verdictLow'; }

  fg.setAttribute('stroke', color);
  big.style.color = color;
  big.textContent = score;

  const t = I18N[currentLang];
  const verdictEl = document.querySelector('.score-verdict span');
  if (verdictEl && t[verdictKey]) {
    const bgMap = { verdictHigh: '#fee2e2', verdictMid: '#fef9c3', verdictLow: '#dcfce7' };
    const colorMap = { verdictHigh: '#991b1b', verdictMid: '#854d0e', verdictLow: '#166534' };
    verdictEl.style.background = bgMap[verdictKey];
    verdictEl.style.color = colorMap[verdictKey];
    verdictEl.textContent = t[verdictKey];
  }
}

/* ===== Init ===== */
(function init() {
  /* Get address from URL */
  const params = new URLSearchParams(window.location.search);
  const addr = params.get('address');
  if (addr) {
    document.getElementById('reportAddr').textContent = addr;
    MOCK.address = addr;
  }

  /* Detect language */
  const nav = navigator.language || 'zh';
  const lang = nav.startsWith('vi') ? 'vi' : (nav.startsWith('en') && !nav.startsWith('zh')) ? 'en' : 'zh';

  /* Render with mock first (so page never blank) */
  setLang(lang);
  updateScore(MOCK.score);
  renderFlow();
  renderTx();

  /* ===== API Integration (real data) ===== */
  if (addr) {
    const apiBase = window.API_BASE || '';
    fetch(apiBase + '/api/report?address=' + encodeURIComponent(addr))
      .then(r => r.json())
      .then(data => {
        if (data && data.score !== undefined) {
          updateScore(data.score);
          if (data.created) {
            document.getElementById('reportAddr').textContent = addr;
            const meta = document.querySelectorAll('.meta-item span');
            if (meta.length > 1) meta[1].textContent = data.created;
          }
          MOCK.counterparties = data.counterparties || [];
          MOCK.transactions = data.transactions || [];
          MOCK.score = data.score;
          MOCK.risk = data.risk;
          renderFlow();
          renderTx();
          if (data.freezeStatus && data.freezeStatus.flags && data.freezeStatus.flags.length) {
            console.log('Freeze flags:', data.freezeStatus.flags);
          }
        }
      })
      .catch(err => {
        console.error('API error (falling back to mock):', err);
        /* keep mock display */
      });
  }
})();