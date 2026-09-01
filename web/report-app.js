/* Report page logic + mock data */
let currentLang = 'zh';

/* 空壳占位：禁止放入任何假数据（曾有 mock 导致用户看到别家地址信息，被麦总当场抓包） */
const MOCK = { score: null, risk: 'low', counterparties: [], transactions: [] };

/* ===== i18n additions for report ===== */
const REPORT_I18N = {
zh: {
  brand:"USDT 冻结取证",addrLabel:"诊断地址",
  metaCreated:"创建时间",metaTx:"交易总数",metaFirst:"首笔",metaLast:"末笔",loading:"数据加载中…",emptyFlow:"暂无对手方数据",emptyTx:"暂无交易记录",
  riskLabel:"风险评分",verdictHigh:"⚠️ 高风险 — 建议深度分析",verdictMid:"⚡ 中风险 — 建议关注",verdictLow:"✅ 低风险",
  tlTitle:"冻结时间线",
  tl1t:"地址创建",tl1d:"地址创建后开始产生链上交易",
  tl2t:"正常交易期",tl2d:"交易活跃期由 API 实时生成",
  tl3t:"高风险转入",tl3d:"高风险/大额交易由 API 实时生成",
  tl4t:"地址被标记冻结",tl4d:"交易所收到链上风控警报，限制该地址提币和交易",
  tl5t:"冻结后",tl5d:"地址被冻结后的状态与后续交易由 API 实时生成",
  flowTitle:"资金流向（TOP 对手方）",legIn:"转入",legOut:"转出",
  txTitle:"关键交易记录",txTime:"时间",txDir:"方向",txAmt:"金额 (USDT)",txCp:"对手方",txHash:"TxHash",
  dirIn:"转入",dirOut:"转出",flagWarn:"⚠ 涉案",
  appealT:"申诉建议",
  a1t:"收集交易凭证",a1d:"整理与该地址关联交易的完整记录：聊天记录、合同、发票、物流单据，证明交易背景真实合法。",
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
  metaCreated:"Tạo",metaTx:"Tổng GD",metaFirst:"Đầu",metaLast:"Cuối",loading:"Đang tải…",emptyFlow:"Chưa có dữ liệu đối tác",emptyTx:"Chưa có giao dịch",
  riskLabel:"Điểm rủi ro",verdictHigh:"⚠️ Rủi ro cao — Nên phân tích sâu",verdictMid:"⚡ Rủi ro trung bình",verdictLow:"✅ Rủi ro thấp",
  tlTitle:"Dòng thời gian đóng băng",
  tl1t:"Tạo địa chỉ",tl1d:"Tạo địa chỉ, bắt đầu giao dịch trên chuỗi",
  tl2t:"Giao dịch bình thường",tl2d:"Giai đoạn giao dịch được tạo tự động từ API",
  tl3t:"Chuyển tiền rủi ro cao",tl3d:"Giao dịch rủi ro được tạo tự động từ API",
  tl4t:"Địa chỉ bị đóng băng",tl4d:"Sàn nhận cảnh báo rủi ro, hạn chế rút và giao dịch",
  tl5t:"Sau đóng băng",tl5d:"Trạng thái sau đóng băng được tạo tự động từ API",
  flowTitle:"Dòng tiền (TOP đối tác)",legIn:"Chuyển vào",legOut:"Chuyển ra",
  txTitle:"Giao dịch quan trọng",txTime:"Thời gian",txDir:"Hướng",txAmt:"Số tiền (USDT)",txCp:"Đối tác",txHash:"TxHash",
  dirIn:"Vào",dirOut:"Ra",flagWarn:"⚠ Liên quan",
  appealT:"Gợi ý khiếu nại",
  a1t:"Thu thập chứng từ",a1d:"Tổng hợp đầy đủ giao dịch với đối tác liên quan: chat, hợp đồng, hóa đơn, vận đơn.",
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
  metaCreated:"Created",metaTx:"Total TXs",metaFirst:"First",metaLast:"Last",loading:"Loading…",emptyFlow:"No counterparty data",emptyTx:"No transactions",
  riskLabel:"Risk Score",verdictHigh:"⚠️ High Risk — Deep analysis recommended",verdictMid:"⚡ Medium Risk — Monitor",verdictLow:"✅ Low Risk",
  tlTitle:"Freeze Timeline",
  tl1t:"Address Created",tl1d:"Address created, on-chain activity begins",
  tl2t:"Normal Trading Period",tl2d:"Trading period generated live from API",
  tl3t:"High-risk Inflow",tl3d:"Risk transactions generated live from API",
  tl4t:"Address Flagged & Frozen",tl4d:"Exchange received on-chain risk alert, restricted withdrawals and trading",
  tl5t:"Post-freeze",tl5d:"Post-freeze status generated live from API",
  flowTitle:"Fund Flow (TOP Counterparties)",legIn:"Inflow",legOut:"Outflow",
  txTitle:"Key Transactions",txTime:"Time",txDir:"Direction",txAmt:"Amount (USDT)",txCp:"Counterparty",txHash:"TxHash",
  dirIn:"IN",dirOut:"OUT",flagWarn:"⚠ Flagged",
  appealT:"Appeal Recommendations",
  a1t:"Collect Transaction Records",a1d:"Gather complete records with related counterparties: chats, contracts, invoices, shipping docs to prove legitimacy.",
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
  const t = I18N[currentLang];
  if (!MOCK.counterparties || MOCK.counterparties.length === 0) {
    chart.innerHTML = `<div class="flow-empty">${t.emptyFlow || '暂无对手方数据'}</div>`;
    return;
  }
  const maxAmt = Math.max(...MOCK.counterparties.map(c => Math.max(c.inAmt, c.outAmt))) || 1;
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
  if (!MOCK.transactions || MOCK.transactions.length === 0) {
    body.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#9ca3af;padding:16px">${t.emptyTx || '暂无交易记录'}</td></tr>`;
    return;
  }
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

function renderTimeline(items) {
  const box = document.getElementById('timelineBox');
  if (!box) return;
  const dotIcon = { green: '✓', blue: '→', red: '🔒', gray: '…' };
  box.innerHTML = items.map(it => `
    <div class="tl-item"><div class="tl-dot ${it.dot || 'blue'}">${dotIcon[it.dot] || '→'}</div>
      <div class="tl-time">${it.time || ''}</div>
      <div class="tl-title">${it.title || ''}</div>
      <div class="tl-desc">${it.desc || ''}</div>
    </div>`).join('');
}

function updateScore(score) {
  const circumference = 2 * Math.PI * 68; /* ~427 */
  const fg = document.getElementById('scoreFg');
  const big = document.getElementById('scoreBig');
  /* 加载态：无数据时不显示任何分数（禁止 mock 兜底） */
  if (score == null || isNaN(score)) {
    fg.style.strokeDashoffset = circumference;
    fg.setAttribute('stroke', '#9ca3af');
    big.style.color = '#9ca3af';
    big.textContent = '--';
    return;
  }
  const offset = circumference - (score / 100) * circumference;
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
  }

  /* Detect language */
  const nav = navigator.language || 'zh';
  const lang = nav.startsWith('vi') ? 'vi' : (nav.startsWith('en') && !nav.startsWith('zh')) ? 'en' : 'zh';

  /* 首屏只渲染空态占位，真实数据来自 API（禁止 mock 兜底——曾有假数据被麦总当场抓包） */
  setLang(lang);
  updateScore(null);
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
            const mc = document.querySelector('[data-meta-created]');
            if (mc) mc.textContent = data.created;
            const mtx = document.querySelector('[data-meta-tx]');
            if (mtx) mtx.textContent = (data.txCount || 0).toLocaleString();
            if (data.transactions && data.transactions.length) {
              const mf = document.querySelector('[data-meta-first]');
              if (mf) mf.textContent = data.transactions[data.transactions.length - 1].time;
              const ml = document.querySelector('[data-meta-last]');
              if (ml) ml.textContent = data.transactions[0].time;
            }
          }
          MOCK.counterparties = data.counterparties || [];
          MOCK.transactions = data.transactions || [];
          MOCK.score = data.score;
          MOCK.risk = data.risk;
          renderFlow();
          renderTx();
          if (data.timeline && data.timeline.length) {
            renderTimeline(data.timeline);
          }
          if (data.freezeStatus && data.freezeStatus.flags && data.freezeStatus.flags.length) {
            console.log('Freeze flags:', data.freezeStatus.flags);
          }
        }
      })
      .catch(err => {
        console.error('API error:', err);
        /* 保持空态占位（"加载中/暂无数据"），不显示任何假数据 */
      });
  }
})();