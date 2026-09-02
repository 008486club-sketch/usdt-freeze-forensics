/*! collect.js - USDT 冻结检测埋点采集（同源 /api/collect，无依赖，约 2KB gzip 前）。
 *  自动埋点：page_view / query_start / query_done(score,frozen,dur) / query_error
 *  点击埋点：data-ua="tip_copy|share_click|report_expand|lang_switch:xx" 或 文案启发式匹配
 *  隐私：不发送 IP/UA（服务端自己取）；地址只在 query_done 带一次，服务端只存 8 位指纹。
 *  关闭地址上报：在引入前设置 window.UA_NO_ADDR = true
 */
(function () {
  "use strict";
  var ENDPOINT = (window.UA_ENDPOINT || "/api/collect");
  var REPORT_HINT = window.UA_REPORT_PATH || "/api/report";
  var doc = document, win = window;
  function lang() {
    var l = (win.I18N && (win.I18N.locale || win.I18N.lang)) || doc.documentElement.getAttribute("lang") || (doc.body && doc.body.getAttribute("data-lang")) || "";
    l = String(l).slice(0, 2).toLowerCase();
    return l === "vi" || l === "en" ? l : "zh";
  }
  function send(ev, props) {
    var body = { ev: ev, path: String(location.pathname).slice(0, 80), lang: lang() };
    if (props) for (var k in props) if (props.hasOwnProperty(k)) body[k] = props[k];
    var s; try { s = JSON.stringify(body); } catch (e) { return; }
    try {
      if (nav.sendBeacon) {
        if (nav.sendBeacon.call(nav, ENDPOINT, new Blob([s], { type: "text/plain" }))) return;
      }
    } catch (e) { /* fall through */ }
    try {
      fetch(ENDPOINT, { method: "POST", body: s, type: "cors", keepalive: true, cache: "no-store",
        headers: { "Content-Type": "text/plain" } }).catch(function () {});
    } catch (e) { /* 最坏情况：静默失败，绝不影响页面功能 */ }
  }
  var nav = navigator;
  var pending = null;

  // ---- 自动捕获对 /api/report 的请求：不用改 report-app.js 就能拿到评分分布 ----
  if (win.fetch && !win.__UA_FETCH_WRAPPED) {
    var origFetch = win.fetch;
    win.fetch = function (input, init) {
      var url = typeof input === "string" ? input : (input && input.url) || "";
      var isReport = url.indexOf(REPORT_HINT) >= 0;
      if (isReport) {
        var m = url.match(/[?&]address=([^&#]+)/i);
        pending = { t0: Date.now(), addr: m ? decodeURIComponent(m[1]).slice(0, 64) : "" };
        send("query_start");
      }
      var p = origFetch.apply(this, arguments);
      if (!isReport) return p;
      return p.then(function (res) {
        var mine = pending || { t0: Date.now(), addr: "" };
        pending = null;
        var dur = Date.now() - (mine.t0 || Date.now());
        var cloned = null;
        try { cloned = res.clone ? res.clone() : null; } catch (e) { cloned = null; }
        if (!cloned) { send(res.ok ? "query_done" : "query_error", { status: res.status, dur_ms: dur }); return res; }
        return cloned.json().then(function (data) {
          var d = data || {};
          var score = d.score != null ? d.score : (d.risk && (d.risk.score != null ? d.risk.score : d.risk.total));
          var frozen = d.frozen != null ? !!d.frozen : !!(d.isBlackListed || d.blacklisted || (d.risk && d.risk.frozen));
          var props = { dur_ms: dur, status: res.status };
          if (score != null && !isNaN(+score)) props.score = Math.max(0, Math.min(100, +score));
          props.frozen = frozen;
          if (!win.UA_NO_ADDR && mine.addr) props.addr = mine.addr;
          send(res.ok ? "query_done" : "query_error", props);
          return res;
        }, function () { send("query_error", { status: res.status, dur_ms: dur }); return res; });
      }, function (err) {
        pending = null;
        send("query_error", { status: 0, dur_ms: Date.now() - Date.now() });
        throw err;
      });
    };
    win.__UA_FETCH_WRAPPED = 1;
  }

  // ---- 点击委托：优先 data-ua，其次文案/类名启发式 ----
  var TIP_RE = /打赏|复制.*地址|trc-?20|tip|donat/i;
  var SHARE_RE = /分享|share|朋友圈|telegram|twitter/i;
  var MORE_RE = /展开|查看更多|详情|expand|more/i;
  function hookOf(el) {
    var h = el.getAttribute && el.getAttribute("data-ua");
    if (h) return h;
    var t = (el.textContent || "").trim().slice(0, 40);
    var cn = (el.className && String(el.className)) || "";
    if (TIP_RE.test(t) || TIP_RE.test(cn)) return "tip_copy";
    if (SHARE_RE.test(t) || SHARE_RE.test(cn)) return "share_click";
    if (MORE_RE.test(t) || MORE_RE.test(cn)) return "report_expand";
    return null;
  }
  doc.addEventListener("click", function (e) {
    var el = e.target;
    for (var i = 0; el && i < 6; i++) {
      if (el.getAttribute) {
        var h = hookOf(el);
        if (h) {
          if (h.indexOf("lang_switch") === 0) {
            var nl = (el.getAttribute("data-lang") || el.getAttribute("href") || "").match(/lang=(vi|en|zh)/i);
            send("lang_switch", { to: nl ? nl[1].toLowerCase() : "zh" });
          } else send(h);
          return;
        }
        var href = el.getAttribute("href") || "";
        var lm = href.match(/[?&]lang=(vi|en|zh)/i);
        if (lm) { send("lang_switch", { to: lm[1].toLowerCase() }); return; }
      }
      el = el.parentNode;
    }
  }, true);

  // ---- 页面访问 + 停留时长 ----
  var t0 = Date.now(), sentLeave = false;
  function leave() {
    if (sentLeave) return; sentLeave = true;
    // 用独立事件名，别把 page_view 漏斗分母翻倍
    send("page_leave", { dwell_ms: Date.now() - t0 });
  }
  doc.addEventListener("visibilitychange", function () { if (doc.hidden) leave(); });
  win.addEventListener("pagehide", leave);
  var first = function () { send("page_view", { first: 1 }); };
  if (doc.readyState === "interactive" || doc.readyState === "complete") first();
  else doc.addEventListener("DOMContentLoaded", first);
  win.UA = { track: send, lang: lang, version: "1.0.0" };
})();
