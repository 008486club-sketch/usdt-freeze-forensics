#!/usr/bin/env node
/**
 * verify_collect.js — 埋点数据隐私断言（Node 版，查线上 JSONL events-*.jsonl）
 * 与 scripts/verify.py 同逻辑：无地址明文 / 指纹格式 / ev 白名单 / score 范围
 * 用法: node verify_collect.js [data_dir]  (默认 /var/lib/usdt-forensics/analytics)
 */
"use strict";
const fs = require("fs");
const path = require("path");

const DATA_DIR = process.argv[2] || "/var/lib/usdt-forensics/analytics";
const ADDR_RE = /^T[1-9A-HJ-NP-Za-km-z]{33}$/;
const EVENTS = new Set(["page_view", "page_leave", "query_start", "query_done", "query_error",
  "tip_copy", "share_click", "lang_switch", "report_expand"]);
const HEX8 = /^[0-9a-f]{8}$/;
const HEX10 = /^[0-9a-f]{10}$/;

function check() {
  const errors = [];
  let checked = 0;
  if (!fs.existsSync(DATA_DIR) || !fs.statSync(DATA_DIR).isDirectory()) {
    return { passed: true, errors: ["目录不存在（首次运行 OK）：" + DATA_DIR], checked: 0 };
  }
  const files = fs.readdirSync(DATA_DIR).filter(f => f.startsWith("events-") && f.endsWith(".jsonl"));
  for (const fn of files) {
    const lines = fs.readFileSync(path.join(DATA_DIR, fn), "utf-8").split("\n");
    lines.forEach((line, i) => {
      line = line.trim();
      if (!line) return;
      checked++;
      let e;
      try { e = JSON.parse(line); } catch (err) { errors.push(`${fn}:${i + 1} 非JSON`); return; }
      if (!e || typeof e !== "object") { errors.push(`${fn}:${i + 1} 非对象`); return; }
      for (const [k, v] of Object.entries(e)) {
        if (typeof v === "string" && ADDR_RE.test(v)) errors.push(`${fn}:${i + 1} 地址明文 ${k}`);
      }
      for (const bad of ["from_address", "to_address", "address"]) {
        if (bad in e) errors.push(`${fn}:${i + 1} 明文地址字段 ${bad}`);
      }
      if ("addr_fp" in e && !HEX8.test(String(e.addr_fp))) errors.push(`${fn}:${i + 1} addr_fp非8hex`);
      if ("uv" in e && !HEX10.test(String(e.uv))) errors.push(`${fn}:${i + 1} uv非10hex`);
      if (!EVENTS.has(e.ev)) errors.push(`${fn}:${i + 1} 未知ev=${e.ev}`);
      if (e.score != null && !(Number(e.score) >= 0 && Number(e.score) <= 100)) errors.push(`${fn}:${i + 1} score越界`);
    });
  }
  return { passed: errors.length === 0, errors, checked };
}

const r = check();
console.log("=== 埋点隐私断言 verify_collect.js ===");
console.log("检查事件行:", r.checked);
if (r.passed) {
  console.log("✓ PASS: 无地址明文 / 指纹格式正确 / ev 白名单 / score 合规");
  process.exit(0);
}
console.log(`✗ FAIL: ${r.errors.length} 处问题`);
r.errors.slice(0, 20).forEach(e => console.log("  -", e));
process.exit(1);
