#!/usr/bin/env bash
# ============================================================
# 三医改革热点观察 — 腾讯云服务器一键部署脚本
# 适用：Ubuntu / Debian / CentOS / RHEL / TencentOS
# 用法：sudo bash install.sh [端口]     # 端口默认 80
# ============================================================
set -e

PORT="${1:-80}"
SITE_DIR="/var/www/sanyi-hot"
APP_DIR="/opt/sanyi-hot"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> [1/7] 安装 Nginx / Python3 / Cron ..."
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y -qq
  apt-get install -y -qq nginx python3 cron
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y -q nginx python3 cronie
elif command -v yum >/dev/null 2>&1; then
  yum install -y -q nginx python3 cronie
else
  echo "未识别的包管理器，请手动安装 nginx、python3、cron 后重试。" >&2
  exit 1
fi

echo "==> [2/7] 部署网站文件到 ${SITE_DIR} ..."
mkdir -p "${SITE_DIR}" "${APP_DIR}"
cp "${SCRIPT_DIR}/index.html" "${SITE_DIR}/index.html"
cp "${SCRIPT_DIR}/update-news.py" "${APP_DIR}/update-news.py"
chmod +x "${APP_DIR}/update-news.py"

echo "==> [3/7] 首次生成数据文件 data.json ..."
SANYI_SITE_DIR="${SITE_DIR}" python3 "${APP_DIR}/update-news.py" || true

echo "==> [4/7] 写入 Nginx 配置（监听端口 ${PORT}）..."
cat > /etc/nginx/conf.d/sanyi-hot.conf <<EOF
server {
    listen ${PORT} default_server;
    listen [::]:${PORT} default_server;
    server_name _;
    root ${SITE_DIR};
    index index.html;
    charset utf-8;

    gzip on;
    gzip_types text/css application/javascript application/json;

    location = /data.json {
        add_header Cache-Control "no-cache, no-store, must-revalidate";
    }
    location / {
        try_files \$uri \$uri/ =404;
    }
}
EOF
# 移除 Debian/Ubuntu 默认站点，避免 default_server 冲突
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

echo "==> [5/7] 配置定时任务：每 15 分钟自动抓取最新新闻 ..."
CRON_FILE="/etc/cron.d/sanyi-hot"
cat > "${CRON_FILE}" <<EOF
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
*/15 * * * * root SANYI_SITE_DIR=${SITE_DIR} /usr/bin/python3 ${APP_DIR}/update-news.py >> /var/log/sanyi-hot-update.log 2>&1
EOF
chmod 644 "${CRON_FILE}"
# 确保 cron 服务在运行
systemctl enable cron  >/dev/null 2>&1 || systemctl enable crond >/dev/null 2>&1 || true
systemctl restart cron >/dev/null 2>&1 || systemctl restart crond >/dev/null 2>&1 || true

echo "==> [6/7] 启动 Nginx ..."
nginx -t
systemctl enable nginx >/dev/null 2>&1 || true
systemctl restart nginx

echo "==> [7/7] 放行防火墙端口 ${PORT} ..."
if command -v ufw >/dev/null 2>&1; then
  ufw allow "${PORT}/tcp" >/dev/null 2>&1 || true
fi
if command -v firewall-cmd >/dev/null 2>&1; then
  firewall-cmd --permanent --add-port="${PORT}/tcp" >/dev/null 2>&1 && firewall-cmd --reload >/dev/null 2>&1 || true
fi

PUBLIC_IP="$(curl -s --max-time 5 ifconfig.me || echo '<你的公网IP>')"
echo ""
echo "============================================================"
echo " 部署完成！"
echo " 网站目录   : ${SITE_DIR}"
echo " 抓取脚本   : ${APP_DIR}/update-news.py（每 15 分钟自动运行）"
echo " 更新日志   : /var/log/sanyi-hot-update.log"
echo ""
echo " 请访问     : http://${PUBLIC_IP}:${PORT}/"
echo " （若端口为 80 可省略 :${PORT}）"
echo ""
echo " 重要：如果无法访问，请到腾讯云控制台【安全组/防火墙】"
echo "       放行 TCP ${PORT} 端口（这一步脚本无法代劳）。"
echo "============================================================"
