/* USDT Freeze Forensics - App Logic */
let currentLang = 'zh';

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
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

function copyA() {
  const addr = 'TTYu42MKHtNJXAbuDpeFdoaiwaeZNFdrVT';
  navigator.clipboard.writeText(addr).then(() => {
    showToast(I18N[currentLang].toastCopy || 'Copied!');
  }).catch(() => {
    /* fallback */
    const ta = document.createElement('textarea');
    ta.value = addr;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast(I18N[currentLang].toastCopy || 'Copied!');
  });
}

function startDiag() {
  const addr = document.getElementById('addrIn').value.trim();
  if (!addr || addr.length < 10) {
    document.getElementById('addrIn').focus();
    document.getElementById('addrIn').style.borderColor = '#dc2626';
    setTimeout(() => document.getElementById('addrIn').style.borderColor = '', 1500);
    return;
  }
  showToast(I18N[currentLang].toastDiag || 'Analyzing...');
  /* TODO: integrate with backend API */
  /* fetch('/api/report?address=' + encodeURIComponent(addr))
       .then(r => r.json())
       .then(data => window.location.href = 'report.html?address=' + addr)
       .catch(err => console.error(err)); */
  
  /* Demo: redirect to report with mock data after delay */
  setTimeout(() => {
    window.location.href = 'report.html?address=' + encodeURIComponent(addr);
  }, 1500);
}

/* Enter key triggers diagnosis */
document.getElementById('addrIn').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') startDiag();
});

/* Auto-detect language from browser */
(function() {
  const nav = navigator.language || navigator.userLanguage || 'zh';
  if (nav.startsWith('vi')) setLang('vi');
  else if (nav.startsWith('en') || nav.startsWith('zh')) setLang(nav.startsWith('zh') ? 'zh' : 'en');
  else setLang('zh');
})();