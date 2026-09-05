#!/usr/bin/env bash
# usdt-check 一键部署脚本（2026-09-05 加：替代手动逐文件上传）
# 用法: ./deploy_usdt.sh [--backend-only|--frontend-only]
# 默认: 后端(api_server/tron_api) + 前端(web/ 下当前引用文件) → 广州 + 雅加达 + 重启 + 健康检查
set -e
cd "$(dirname "$0")/.."   # 到 usdt-freeze-forensics/

LOCAL_REPO="/home/admin/yuezhi_tong/usdt-freeze-forensics"
PSSH="/home/admin/yuezhi_tong/pssh.py"
JAKARTA_HOST="8.215.90.78"
JAKARTA_KEY="/home/admin/yuezhi_tong/官网/new0630.pem"

MODE="${1:-all}"
echo "=== usdt-check 部署 [$MODE] ==="

deploy_backend() {
  echo "--- 后端 → 广州 ---"
  python3 "$PSSH" -f "$LOCAL_REPO/api/api_server.py" /opt/usdt-forensics/api_server.py
  python3 "$PSSH" -f "$LOCAL_REPO/scripts/tron_api.py" /opt/usdt-forensics/tron_api.py
  python3 "$PSSH" "systemctl restart usdt-forensics && sleep 2 && systemctl is-active usdt-forensics"
  echo "--- 后端 → 雅加达 ---"
  python3 "$PSSH" -h "$JAKARTA_HOST" -f "$LOCAL_REPO/api/api_server.py" /opt/usdt-forensics/api_server.py
  python3 "$PSSH" -h "$JAKARTA_HOST" -f "$LOCAL_REPO/scripts/tron_api.py" /opt/usdt-forensics/tron_api.py
  python3 "$PSSH" -h "$JAKARTA_HOST" "systemctl restart usdt-forensics && sleep 2 && systemctl is-active usdt-forensics"
}

deploy_frontend() {
  # 从 report.html 提取当前引用的 JS 版本（保证只传线上引用文件）
  JS_VER=$(grep -o 'report-app\.[0-9]*[a-z]\.js' "$LOCAL_REPO/web/report.html" | head -1)
  FILES=("report.html" "index.html" "deep.html" "i18n.js" "collect.js" "$JS_VER" "og-cover.png" "tip-qr.png" "faq.html")
  echo "--- 前端(${JS_VER}) → 广州 ---"
  for f in "${FILES[@]}"; do
    [ -f "$LOCAL_REPO/web/$f" ] && python3 "$PSSH" -f "$LOCAL_REPO/web/$f" "/home/admin/yuezhi_tong/usdt-check/$f"
  done
  echo "--- 前端(${JS_VER}) → 雅加达 ---"
  for f in "${FILES[@]}"; do
    [ -f "$LOCAL_REPO/web/$f" ] && python3 "$PSSH" -h "$JAKARTA_HOST" -f "$LOCAL_REPO/web/$f" "/home/admin/yuezhi_tong/usdt-check/$f"
  done
}

health() {
  echo "--- 健康检查 ---"
  python3 "$PSSH" "curl -s -o /dev/null -w '广州health=%{http_code}\\n' http://127.0.0.1:8902/api/health"
  python3 "$PSSH" -h "$JAKARTA_HOST" "curl -s -o /dev/null -w '雅加达health=%{http_code}\\n' http://127.0.0.1:8902/api/health"
}

case "$MODE" in
  backend) deploy_backend ;;
  frontend) deploy_frontend ;;
  all) deploy_backend; deploy_frontend ;;
esac
health
echo "=== 部署完成 ==="
