#!/bin/bash
# conf-access — 内网站点 hosts 一键钉(install / uninstall / status)
# 域名与 IP 不硬编码,来源优先级:命令行 --domain/--ip > 环境变量 CONF_DOMAIN/CONF_IP
# > ~/.config/conf-access/config;均未配置时 install 交互式询问。
# 任一来源首次生效都会保存到本地 config(600 权限,只存你自己机器),下次免配。
# 只动 hosts 文件的一个标记块;先备份、幂等、可一键还原。写 /etc/hosts 需 sudo。
set -euo pipefail

HOSTS="${CONF_HOSTS_FILE:-/etc/hosts}"   # 测试/沙箱可用 CONF_HOSTS_FILE 指向普通文件
MARK_BEGIN="# conf-access begin"
MARK_END="# conf-access end"

# 配置文件归属真实用户(兼容 sudo 执行)
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")
CONF_DIR="${CONF_CONFIG_DIR:-$REAL_HOME/.config/conf-access}"
CONF_FILE="$CONF_DIR/config"

need_root(){
  [ "$HOSTS" != "/etc/hosts" ] && return 0
  [ "$(id -u)" = "0" ] || { echo "请用 sudo 执行:sudo bash $0 $1"; exit 1; }
}

load_config(){
  if { [ -z "${CONF_DOMAIN:-}" ] || [ -z "${CONF_IP:-}" ]; } && [ -f "$CONF_FILE" ]; then
    # shellcheck disable=SC1090
    . "$CONF_FILE"
  fi
}

ask_config(){
  echo "首次使用:域名与 IP 请向你的网络管理员/团队群获取。"
  read -r -p "内网站点域名(如 wiki.example.internal):" CONF_DOMAIN
  read -r -p "网关/服务器 IP(如 203.0.113.10):" CONF_IP
  [ -n "${CONF_DOMAIN:-}" ] && [ -n "${CONF_IP:-}" ] || { echo "✗ 域名/IP 不能为空"; exit 1; }
}

save_config(){
  mkdir -p "$CONF_DIR"
  printf 'CONF_DOMAIN=%s\nCONF_IP=%s\n' "$CONF_DOMAIN" "$CONF_IP" > "$CONF_FILE"
  chmod 600 "$CONF_FILE"
  [ -n "${SUDO_USER:-}" ] && chown -R "$SUDO_USER" "$CONF_DIR" 2>/dev/null || true
  echo "✔ 配置已保存:$CONF_FILE(更换站点直接编辑该文件或重跑 install)"
}

validate(){
  echo "$CONF_IP" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' || { echo "✗ IP 格式不合法:$CONF_IP"; exit 1; }
  echo "$CONF_DOMAIN" | grep -Eq '^[A-Za-z0-9.-]+$' || { echo "✗ 域名格式不合法:$CONF_DOMAIN"; exit 1; }
}

flush_dns(){
  dscacheutil -flushcache 2>/dev/null || true
  killall -HUP mDNSResponder 2>/dev/null || true
}

strip_block(){  # 从 stdin 滤掉标记块
  awk -v b="$MARK_BEGIN" -v e="$MARK_END" '$0==b{skip=1;next} $0==e{skip=0;next} !skip'
}

CMD="${1:-}"; [ $# -gt 0 ] && shift

# install 可带参:--domain <域名> --ip <IP>(一条命令完成配置+写入+验证)
CLI_SET=0
while [ $# -gt 0 ]; do
  case "$1" in
    --domain) CONF_DOMAIN="${2:-}"; CLI_SET=1; shift 2;;
    --ip)     CONF_IP="${2:-}";     CLI_SET=1; shift 2;;
    *) echo "✗ 未知参数:$1(install 只认 --domain / --ip)"; exit 1;;
  esac
done

case "$CMD" in
  install)
    need_root install
    load_config
    ASKED=0
    if [ -z "${CONF_DOMAIN:-}" ] || [ -z "${CONF_IP:-}" ]; then
      ask_config; ASKED=1
    fi
    validate   # 先校验,后落盘
    if [ "$CLI_SET" = "1" ] || [ "$ASKED" = "1" ] || [ ! -f "$CONF_FILE" ]; then
      save_config   # 带参/交互/环境变量首跑都落一份本地 config,下次免配
    fi
    ts=$(date +%Y%m%d-%H%M%S)
    cp "$HOSTS" "$HOSTS.bak-conf-access-$ts"
    tmp=$(mktemp)
    strip_block < "$HOSTS" > "$tmp"
    { cat "$tmp"; echo "$MARK_BEGIN"; echo "$CONF_IP $CONF_DOMAIN"; echo "$MARK_END"; } > "$HOSTS"
    rm -f "$tmp"
    flush_dns
    echo "✔ 已写入:$CONF_IP $CONF_DOMAIN(备份:$HOSTS.bak-conf-access-$ts)"
    code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "https://$CONF_DOMAIN/" || true)
    case "$code" in
      2??|3??) echo "✔ 验证通过(HTTP $code)——浏览器打开 https://$CONF_DOMAIN 即可";;
      *) echo "⚠ 验证返回 HTTP ${code:-000}:请确认当前在目标内网;若持续失败可执行卸载:"
         echo "  sudo bash $0 uninstall";;
    esac
    ;;
  uninstall)
    need_root uninstall
    tmp=$(mktemp)
    strip_block < "$HOSTS" > "$tmp"
    cat "$tmp" > "$HOSTS"
    rm -f "$tmp"
    flush_dns
    echo "✔ 标记块已移除,hosts 其余内容未动"
    ;;
  status)
    if grep -q "^$MARK_BEGIN$" "$HOSTS" 2>/dev/null; then
      echo "已安装:"; sed -n "/^$MARK_BEGIN$/,/^$MARK_END$/p" "$HOSTS"
    else
      echo "未安装"
    fi
    [ -f "$CONF_FILE" ] && { echo "本地配置($CONF_FILE):"; cat "$CONF_FILE"; } || echo "本地配置:无"
    ;;
  *)
    echo "用法:sudo bash $0 install [--domain <域名> --ip <IP>] | uninstall | status"; exit 1;;
esac
