/* Report page logic + mock data */
let currentLang = 'zh';
let currentFrozen = null; /* 时间线标题状态：fetch 完成后 true/false；未加载 null → 显示"地址活动时间线" */
let currentAddr = ''; /* 当前诊断地址：setLang 切换语言时重新请求后端（动态文案按语言返回） */

/* 空壳占位：禁止放入任何假数据（曾有 mock 导致用户看到别家地址信息，被麦总当场抓包） */
const MOCK = { score: null, risk: 'low', counterparties: [], transactions: [] };

/* ===== i18n additions for report ===== */
const REPORT_I18N = {
zh: {
  brand:"USDT 冻结检测",addrLabel:"诊断地址",
  metaCreated:"创建时间",metaTx:"抽样记录",metaFirst:"抽样首笔",metaLast:"抽样末笔",metaTxSuffix:"笔（TronGrid 最近100笔）",noteSample:"数据来自 TronGrid 最近100笔抽样（非全量）；交易总数/首笔/末笔均为抽样窗口数据；如需全量分析请使用深度报告",loading:"数据加载中…",emptyFlow:"暂无对手方数据",emptyTx:"暂无交易记录",
  riskLabel:"风险评分",verdictHigh:"⚠️ 高风险 — 建议深度分析",verdictMid:"⚡ 中风险 — 建议关注",verdictLow:"✅ 低风险",
  riskBannerFrozen:"🔒 该地址已被 Tether 冻结（高风险）",riskBannerHigh:"⚠️ 高风险地址 — 建议深度排查",riskBannerMid:"⚡ 中风险地址 — 建议关注",riskBannerLow:"✅ 低风险地址",bldzen:"第三方复核:",
  tlTitle:"冻结时间线",tlTitleFree:"地址活动时间线",planTitle:"行动方案",bdTitle:"评分依据",
  tl1t:"地址创建",tl1d:"地址创建后开始产生链上交易",
  tl2t:"正常交易期",tl2d:"交易活跃期由 API 实时生成",
  tl3t:"高风险转入",tl3d:"高风险/大额交易由 API 实时生成",
  tl4t:"地址被标记冻结",tl4d:"交易所收到链上风控警报，限制该地址提币和交易",
  tl5t:"冻结后",tl5d:"地址被冻结后的状态与后续交易由 API 实时生成",
  flowTitle:"资金流向（TOP 对手方）",legIn:"转入",legOut:"转出",
  txTitle:"关键交易记录",txTime:"时间",txDir:"方向",txAmt:"金额 (USDT)",txCp:"对手方",txHash:"TxHash",
  dirIn:"转入",dirOut:"转出",flagWarn:"⚠ 异常",
  appealT:"申诉建议",
  a1t:"收集交易凭证",a1d:"整理与该地址关联交易的完整记录：聊天记录、合同、发票、物流单据，证明交易背景真实合法。",
  a2t:"准备 KYC 材料",a2d:"更新交易所 KYC 信息，提供身份证明、地址证明、资金来源说明。确保与链上行为一致。",
  a3t:"提交申诉工单",a3d:"通过交易所官方渠道提交申诉，附上本报告和所有支持材料。保持耐心，跟进处理进度。",
  a4t:"寻求法律支持",a4d:"如申诉被拒，考虑委托专业律师发函或向监管机构投诉。保留所有沟通记录作为证据。",
  tipL:"USDT-TRC20 打赏地址",tipC:"点击复制",
  footN:"本服务基于区块链公开数据，不提供法律建议。",
  toastCopy:"地址已复制到剪贴板"
},
vi: {
  brand:"Kiểm tra đóng băng USDT",addrLabel:"Địa chỉ chẩn đoán",
  metaCreated:"Tạo",metaTx:"GD mẫu",metaFirst:"Đầu (mẫu)",metaLast:"Cuối (mẫu)",metaTxSuffix:" GD (TronGrid 100 GD gần nhất)",noteSample:"Dữ liệu từ TronGrid lấy mẫu 100 GD gần nhất (không đầy đủ); tổng/đầu/cuối chỉ là cửa sổ mẫu; cần phân tích đầy đủ vui lòng dùng báo cáo chuyên sâu",loading:"Đang tải…",emptyFlow:"Chưa có dữ liệu đối tác",emptyTx:"Chưa có giao dịch",
  riskLabel:"Điểm rủi ro",verdictHigh:"⚠️ Rủi ro cao — Nên phân tích sâu",verdictMid:"⚡ Rủi ro trung bình",verdictLow:"✅ Rủi ro thấp",
  riskBannerFrozen:"🔒 Địa chỉ đã bị Tether đóng băng (rủi ro cao)",riskBannerHigh:"⚠️ Địa chỉ rủi ro cao — nên kiểm tra sâu",riskBannerMid:"⚡ Rủi ro trung bình — nên theo dõi",riskBannerLow:"✅ Rủi ro thấp",bldzen:"Kiểm tra chéo bên thứ ba:",
  tlTitle:"Dòng thời gian đóng băng",tlTitleFree:"Dòng thời gian địa chỉ",planTitle:"Kế hoạch hành động",bdTitle:"Cơ sở chấm điểm",
  tl1t:"Tạo địa chỉ",tl1d:"Tạo địa chỉ, bắt đầu giao dịch trên chuỗi",
  tl2t:"Giao dịch bình thường",tl2d:"Giai đoạn giao dịch được tạo tự động từ API",
  tl3t:"Chuyển tiền rủi ro cao",tl3d:"Giao dịch rủi ro được tạo tự động từ API",
  tl4t:"Địa chỉ bị đóng băng",tl4d:"Sàn nhận cảnh báo rủi ro, hạn chế rút và giao dịch",
  tl5t:"Sau đóng băng",tl5d:"Trạng thái sau đóng băng được tạo tự động từ API",
  flowTitle:"Dòng tiền (TOP đối tác)",legIn:"Chuyển vào",legOut:"Chuyển ra",
  txTitle:"Giao dịch quan trọng",txTime:"Thời gian",txDir:"Hướng",txAmt:"Số tiền (USDT)",txCp:"Đối tác",txHash:"TxHash",
  dirIn:"Vào",dirOut:"Ra",flagWarn:"⚠ Bất thường",
  appealT:"Gợi ý khiếu nại",
  a1t:"Thu thập chứng từ",a1d:"Tổng hợp đầy đủ giao dịch với đối tác liên quan: chat, hợp đồng, hóa đơn, vận đơn.",
  a2t:"Chuẩn bị KYC",a2d:"Cập nhật KYC sàn, cung cấp CMND, bằng địa chỉ, giải trình nguồn tiền.",
  a3t:"Gửi khiếu nại",a3d:"Gửi qua kênh chính thức của sàn, kèm báo cáo và tài liệu.",
  a4t:"Hỗ trợ pháp lý",a4d:"Nếu bị từ chối, xem xét thuê luật sư hoặc khiếu nại cơ quan quản lý.",
  tipL:"Địa chỉ USDT-TRC20",tipC:"Nhấn để sao chép",
  footN:"Dịch vụ dựa trên dữ liệu blockchain công khai, không phải tư vấn pháp lý.",
  toastCopy:"Đã sao chép địa chỉ"
},
en: {
  brand:"USDT Freeze Check",addrLabel:"Diagnosed Address",
  metaCreated:"Created",metaTx:"Sampled TXs",metaFirst:"First (sampled)",metaLast:"Last (sampled)",metaTxSuffix:" (TronGrid recent 100)",noteSample:"Data from TronGrid sampling of last 100 TXs (not complete); totals/first/last are sampled window only; for full analysis use deep report",loading:"Loading…",emptyFlow:"No counterparty data",emptyTx:"No transactions",
  riskLabel:"Risk Score",verdictHigh:"⚠️ High Risk — Deep analysis recommended",verdictMid:"⚡ Medium Risk — Monitor",verdictLow:"✅ Low Risk",
  riskBannerFrozen:"🔒 Address frozen by Tether (high risk)",riskBannerHigh:"⚠️ High-risk address — deep check recommended",riskBannerMid:"⚡ Medium risk — monitor",riskBannerLow:"✅ Low risk",bldzen:"Third-party cross-check:",
  tlTitle:"Freeze Timeline",tlTitleFree:"Address Timeline",planTitle:"Action Plan",bdTitle:"Score Basis",
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
  const langBtn = document.querySelector(`.lang-btn[onclick="setLang('${lang}')"]`);
  if (langBtn) langBtn.classList.add('active');
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const val = I18N[lang] && I18N[lang][key];
    if (val) el.innerHTML = val;
  });
  document.documentElement.lang = lang === 'zh' ? 'zh' : lang === 'vi' ? 'vi' : 'en';
  renderFlow();
  renderTx();
  /* 时间线标题状态同步：不依赖 data-i18n（避免 setLang 用默认值覆盖），由 fetch 数据驱动 */
  const tlTitleEl = document.getElementById('tlTitle');
  if (tlTitleEl) {
    const frozen = currentFrozen === true;
    const t = I18N[currentLang] || {};
    tlTitleEl.textContent = t[frozen ? 'tlTitle' : 'tlTitleFree']
      || (frozen ? '冻结时间线' : '地址活动时间线');
  }
  /* 语言切换后重新请求后端：动态文案（时间线/行动方案/评分依据/note）按语言返回，否则中英混杂 */
  if (currentAddr) {
    loadReport(currentAddr);
  }
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
  const cps = MOCK.counterparties || [];
  if (!cps.length) {
    chart.innerHTML = `<div class="flow-empty">${t.emptyFlow || '暂无对手方数据'}</div>`;
    return;
  }
  /* 对手方标签徽章（已验/特征标签） */
  const tagOf = (c) => {
    if (!c.tag) return '';
    const warn = c.tag.indexOf('疑似') >= 0 || c.tag.indexOf('高危') >= 0 || c.tag.indexOf('冻结') >= 0
      || c.tag.indexOf('马甲') >= 0 || c.tag.indexOf('诈骗') >= 0;
    return `<span class="cp-tag${warn ? ' warn' : ''}">${c.tag}</span>`;
  };
  /* 桑基图：左=转入来源 TOP5 / 中=本地址 / 右=转出去向 TOP5，带宽按金额占比 */
  const ins = cps.filter(c => c.inAmt > 0).sort((a, b) => b.inAmt - a.inAmt).slice(0, 5);
  const outs = cps.filter(c => c.outAmt > 0).sort((a, b) => b.outAmt - a.outAmt).slice(0, 5);
  const maxIn = Math.max(...ins.map(c => c.inAmt), 1);
  const maxOut = Math.max(...outs.map(c => c.outAmt), 1);
  const addrEl = document.getElementById('reportAddr');
  const addrShort = (addrEl && addrEl.textContent || '').slice(0, 12) || '本地址';
  chart.innerHTML = `
  <div class="sankey">
    <div class="sk-col sk-in">
      <div class="sk-head"><span class="sk-arrow">←</span> ${t.legIn || '转入'}</div>
      ${ins.map(c => `<div class="sk-row">
        <div class="sk-label" title="${c.addr}">${c.addr.slice(0, 8)}…${tagOf(c)}</div>
        <div class="sk-track"><div class="sk-bar in" style="width:${(c.inAmt / maxIn * 100).toFixed(1)}%"></div></div>
        <div class="sk-amt">${c.inAmt.toLocaleString()}</div>
      </div>`).join('') || '<div class="sk-empty">—</div>'}
    </div>
    <div class="sk-mid"><div class="sk-addr">${addrShort}</div></div>
    <div class="sk-col sk-out">
      <div class="sk-head">${t.legOut || '转出'} <span class="sk-arrow">→</span></div>
      ${outs.map(c => `<div class="sk-row">
        <div class="sk-amt">${c.outAmt.toLocaleString()}</div>
        <div class="sk-track"><div class="sk-bar out" style="width:${(c.outAmt / maxOut * 100).toFixed(1)}%"></div></div>
        <div class="sk-label" title="${c.addr}">${c.addr.slice(0, 8)}…${tagOf(c)}</div>
      </div>`).join('') || '<div class="sk-empty">—</div>'}
    </div>
  </div>`;
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
    const flag = tx.flag ? ` <span style="color:var(--red);font-size:12px" title="${(tx.flagNote || '').replace(/"/g, '&quot;')}">${t.flagWarn || '⚠ Flagged'}</span>` : '';
    const flagNote = tx.flagNote ? `<div style="color:var(--red);font-size:11px;opacity:.85;margin-top:2px;line-height:1.3">${tx.flagNote}</div>` : '';
    return `<tr>
      <td>${tx.time}</td>
      <td><span class="tx-dir ${dirClass}">${dirText}</span>${flag}${flagNote}</td>
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

/* 评分依据：展示"为什么是这个分数"（基础分 + 每项加分） */
function renderBreakdown(score, items) {
  const card = document.getElementById('breakdownCard');
  const list = document.getElementById('bdList');
  const scoreEl = document.getElementById('bdScore');
  if (!card || !list) return;
  if (score == null || !items || !items.length) {
    card.style.display = 'none';
    return;
  }
  list.innerHTML = items.map((it, i) => {
    const label = it.label || '';
    const pts = it.points;
    const cls = i === 0 ? 'bd-item bd-base' : 'bd-item bd-pos';
    return `<div class="${cls}"><span class="bd-label">${label}</span><span class="bd-pts">${pts >= 0 ? '+' + pts : pts}</span></div>`;
  }).join('');
  if (scoreEl) scoreEl.textContent = score;
  card.style.display = 'block';
}

function updateScore(score) {
  const circumference = 2 * Math.PI * 68; /* ~427 */
  const fg = document.getElementById('scoreFg');
  const big = document.getElementById('scoreBig');
  /* verdict：id 定位优先（不依赖复杂选择器），文案内置兜底（不依赖 i18n 合并成功） */
  const verdictEl = document.getElementById('verdictBox') || document.querySelector('.score-verdict span');
  const t = (I18N && I18N[currentLang]) || {};
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
  if (score >= 60) { color = 'var(--red)'; verdictKey = 'verdictHigh'; }
  else if (score >= 30) { color = 'var(--ylw)'; verdictKey = 'verdictMid'; }
  else { color = 'var(--grn)'; verdictKey = 'verdictLow'; }

  fg.setAttribute('stroke', color);
  big.style.color = color;
  big.textContent = score;

  /* 风险色块（OKLink 借鉴）：score-card 边框随风险等级变色 */
  const card = document.getElementById('scoreCard');
  if (card) {
    card.classList.remove('risk-high', 'risk-mid', 'risk-low');
    card.classList.add(score >= 60 ? 'risk-high' : (score >= 30 ? 'risk-mid' : 'risk-low'));
  }

  /* 兜底文案：即使 i18n 异常也能显示结论，绝不卡在"数据加载中…" */
  const fallback = {
    verdictHigh: '⚠️ 高风险 — 建议深度分析',
    verdictMid: '⚡ 中风险 — 建议关注',
    verdictLow: '✅ 低风险'
  };
  const txt = t[verdictKey] || fallback[verdictKey];
  if (verdictEl && txt) {
    const bgMap = { verdictHigh: '#fee2e2', verdictMid: '#fef9c3', verdictLow: '#dcfce7' };
    const colorMap = { verdictHigh: '#991b1b', verdictMid: '#854d0e', verdictLow: '#166534' };
    verdictEl.style.background = bgMap[verdictKey];
    verdictEl.style.color = colorMap[verdictKey];
    verdictEl.textContent = txt;
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
    currentAddr = addr;
    loadReport(addr);
  }
})();

/* ===== 加载报告（按当前语言请求后端；setLang 切换语言时也会调用） ===== */
function loadReport(addr) {
  const apiBase = window.API_BASE || '';
  fetch(apiBase + '/api/report?address=' + encodeURIComponent(addr) + '&lang=' + currentLang)
    .then(r => r.json())
    .then(data => {
      if (data && data.score !== undefined) {
        updateScore(data.score);
        /* 评分依据（为什么是这个分数） */
        renderBreakdown(data.score, data.scoreBreakdown || []);
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
        /* 动态标题：未冻结地址不显示"冻结时间线"（防误导）；状态驱动 + id 定位（不被 setLang 覆盖） */
        currentFrozen = data.frozen === true
          || (data.score !== undefined && data.score >= 90)
          || !!(data.freezeStatus && data.freezeStatus.flags && data.freezeStatus.flags.length);
        const tlTitleEl = document.getElementById('tlTitle');
        if (tlTitleEl) {
          const t2 = (I18N[currentLang] && I18N[currentLang]) || {};
          const key = currentFrozen ? 'tlTitle' : 'tlTitleFree';
          tlTitleEl.textContent = t2[key] || (currentFrozen ? '冻结时间线' : '地址活动时间线');
        }
        /* 风险横幅（OKLink 借鉴）：冻结/高危/中危/低危分级提示 */
        const rb = document.getElementById('riskBanner');
        if (rb) {
          const t3 = (I18N[currentLang] && I18N[currentLang]) || {};
          const frozen = data.frozen === true
            || (data.score !== undefined && data.score >= 90)
            || !!(data.freezeStatus && data.freezeStatus.flags && data.freezeStatus.flags.length);
          if (frozen) {
            /* 冻结横幅 + 第三方复核链接（bl.dzen.ws，2026-09-05） */
            const addrQ = encodeURIComponent(currentAddr || '');
            const frozenText = t3.riskBannerFrozen || '🔒 该地址已被 Tether 冻结（高风险）';
            rb.innerHTML = frozenText
              + (addrQ ? `<br><a href="https://bl.dzen.ws/address/${addrQ}" target="_blank" rel="noopener" style="color:inherit;font-size:12px;opacity:.9;text-decoration:underline">${t3.bldzen || ''} bl.dzen.ws ⧉</a>` : '');
            rb.className = 'risk-banner show b-high';
          } else if (data.score >= 60 || data.risk === 'high') {
            rb.textContent = t3.riskBannerHigh || '⚠️ 高风险地址 — 建议深度排查';
            rb.className = 'risk-banner show b-high';
          } else if (data.score >= 30 || data.risk === 'mid') {
            rb.textContent = t3.riskBannerMid || '⚡ 中风险地址 — 建议关注';
            rb.className = 'risk-banner show b-mid';
          } else {
            rb.textContent = t3.riskBannerLow || '✅ 低风险地址';
            rb.className = 'risk-banner show b-low';
          }
        }
        /* 行动方案（API 基于真实数据定制） */
        const pb = document.getElementById('planBox');
        if (pb && data.actionPlan && data.actionPlan.length) {
          pb.innerHTML = data.actionPlan.map((p, i) => `
            <div class="plan-item">
              <div class="pn">${i + 1}</div>
              <div><div class="pt">${p.t}</div><div class="pd">${p.d}</div></div>
            </div>`).join('');
        }
        /* 保险：显式设置 verdict（与 riskBanner 同一路径，阈值与 risk 统一 60/30） */
        const vb = document.getElementById('verdictBox');
        if (vb && data.score !== undefined) {
          const s = data.score;
          const key = s >= 60 ? 'verdictHigh' : (s >= 30 ? 'verdictMid' : 'verdictLow');
          const t4 = (I18N[currentLang] && I18N[currentLang]) || {};
          const fb2 = { verdictHigh: '⚠️ 高风险 — 建议深度分析', verdictMid: '⚡ 中风险 — 建议关注', verdictLow: '✅ 低风险' };
          const txt2 = t4[key] || fb2[key];
          if (txt2) vb.textContent = txt2;
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