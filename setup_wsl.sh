#!/usr/bin/env bash
# CEG5101 — WSL2 (Ubuntu 20.04) 实验环境一键脚本
#   Mininet 2.3.1b4 + Open vSwitch + Ryu (Python 3.8) + hping3 / iperf / matplotlib
#
# 用法（用普通用户运行，不要加 sudo）：
#   bash setup_wsl.sh          安装全部并自检
#   bash setup_wsl.sh test     只跑自检
# 可以重复运行，已装好的部分会跳过。不会改动 SSH 和 Tailscale 的配置。

set -euo pipefail

MININET_TAG="2.3.1b4"            # Lab 1 文档用的版本
RYU_VENV="$HOME/ryu-venv"
MODE="${1:-all}"
# 自检日志不能放 /tmp：mn -c 清理时会删掉 /tmp/*.log
LOG_DIR="$HOME/.cache/ceg5101-selftest"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m  ✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ---------- 0. 前置检查 ----------
step "前置检查"
[ "$(id -u)" -ne 0 ] || die "请用普通用户运行（脚本内部会自己调用 sudo）"

# shellcheck disable=SC1091
. /etc/os-release
echo "  系统: $PRETTY_NAME    内核: $(uname -r)    Python: $(python3 --version 2>&1)"
case "$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')" in
    3.8|3.9) ;;
    *) warn "Ryu 需要 Python 3.8/3.9，当前版本可能装不上（Ubuntu 20.04 自带 3.8）" ;;
esac

# WSL 5.15 内核没有 openvswitch / netem / htb，Mininet 的 TCLink（带宽、时延）跑不了。
kver="$(uname -r)"; kmajor="${kver%%.*}"; krest="${kver#*.}"; kminor="${krest%%.*}"
if [ "$kmajor" -lt 6 ] || { [ "$kmajor" -eq 6 ] && [ "$kminor" -lt 6 ]; }; then
    die "WSL 内核 $kver 太旧，需要 6.6 以上。在 Windows PowerShell 里执行 wsl --update 和 wsl --shutdown 后重试。"
fi
[ "$(ps -p 1 -o comm=)" = "systemd" ] || die "systemd 没有运行。在 /etc/wsl.conf 的 [boot] 下加 systemd=true，然后 wsl --shutdown 重启。"
ok "内核和 systemd 满足要求"

sudo -v
# 安装时间较长，保持 sudo 不过期
( while true; do sudo -n true; sleep 50; kill -0 "$$" 2>/dev/null || exit; done ) 2>/dev/null &

if [ "$MODE" != "test" ]; then   # ===== 安装部分开始（test 模式跳过）=====

# ---------- 1. apt 软件源 ----------
# archive.ubuntu.com / security.ubuntu.com 有时能连上但不回数据，apt 会一直卡住。
# 连不通时自动换成能用的镜像（原文件备份为 sources.list.bak-ceg5101）。
step "检查 apt 软件源"
apt_ok() {
    curl -4 -fsS -o /dev/null --connect-timeout 5 --max-time 10 \
        "http://$1/ubuntu/dists/$VERSION_CODENAME/InRelease"
}
if grep -Eq '//(archive|security)\.ubuntu\.com' /etc/apt/sources.list && ! apt_ok archive.ubuntu.com; then
    MIRROR=""
    for m in sg.archive.ubuntu.com mirrors.aliyun.com mirrors.tuna.tsinghua.edu.cn; do
        if apt_ok "$m"; then MIRROR="$m"; break; fi
    done
    [ -n "$MIRROR" ] || die "官方源和备选镜像都连不上，请先检查这台机器的网络。"
    [ -e /etc/apt/sources.list.bak-ceg5101 ] || sudo cp /etc/apt/sources.list /etc/apt/sources.list.bak-ceg5101
    sudo sed -i -E "s#https?://(archive|security)\.ubuntu\.com/ubuntu#http://$MIRROR/ubuntu#g" /etc/apt/sources.list
    warn "官方源不通，已切换到镜像 $MIRROR"
else
    ok "apt 软件源可用"
fi

# ---------- 2. 基础软件包 ----------
step "安装基础软件包"
export DEBIAN_FRONTEND=noninteractive
APT_OPTS=(-o Acquire::Retries=3 -o Acquire::http::Timeout=20 -o Acquire::ForceIPv4=true)
sudo apt-get "${APT_OPTS[@]}" update
sudo -E apt-get "${APT_OPTS[@]}" install -y \
    git curl wget ca-certificates build-essential \
    python3-pip python3-venv python3-dev python3-tk python3-matplotlib \
    kmod iproute2 iputils-ping net-tools \
    hping3 iperf iperf3 tcpdump xterm
ok "基础软件包安装完成"

# ---------- 3. 内核模块 ----------
step "加载内核模块 (openvswitch / netem / htb)"
for m in openvswitch sch_netem sch_htb; do
    sudo modprobe "$m" || die "模块 $m 加载失败。请在 PowerShell 里 wsl --update 后重试。"
done
printf 'openvswitch\nsch_netem\nsch_htb\n' | sudo tee /etc/modules-load.d/mininet.conf >/dev/null
ok "内核模块已加载，并设为开机自动加载"

# ---------- 4. Mininet + Open vSwitch ----------
step "安装 Mininet $MININET_TAG 和 Open vSwitch"
if command -v mn >/dev/null 2>&1; then
    ok "Mininet 已安装，跳过"
else
    if [ ! -d "$HOME/mininet/.git" ]; then
        git clone https://github.com/mininet/mininet "$HOME/mininet"
    fi
    git -C "$HOME/mininet" checkout -q "$MININET_TAG"
    # 只装 Mininet 本体(-n) 和 Open vSwitch(-v)。
    # 文档里不带参数的 install.sh 会尝试装 linux-image 内核包，在 WSL 上会失败。
    PYTHON=python3 "$HOME/mininet/util/install.sh" -nv
fi
sudo systemctl enable --now openvswitch-switch >/dev/null 2>&1
# 测试控制器会占用 6653 端口，和 Ryu 冲突
sudo systemctl disable --now openvswitch-testcontroller >/dev/null 2>&1 || true
ok "Mininet / OVS 就绪"

# ---------- 5. Ryu ----------
step "安装 Ryu（虚拟环境 $RYU_VENV）"
if [ -x "$RYU_VENV/bin/ryu-manager" ]; then
    ok "Ryu 已安装，跳过"
else
    python3 -m venv "$RYU_VENV"
    # 版本固定来自 Lab 3 文档：新版 setuptools / eventlet 与 Ryu 不兼容
    "$RYU_VENV/bin/pip" install wheel 'setuptools==57.5.0' pbr
    "$RYU_VENV/bin/pip" install 'eventlet==0.30.2'
    "$RYU_VENV/bin/pip" install ryu
fi
sudo ln -sf "$RYU_VENV/bin/ryu-manager" /usr/local/bin/ryu-manager
ok "ryu-manager 已链接到 /usr/local/bin，任何目录下可直接运行"

fi   # ===== 安装部分结束 =====

# ---------- 6. 自检 ----------
step "自检（约 1 分钟）"
RESULTS=(); FAILED=0
check() {
    local name="$1"; shift
    if "$@" >/dev/null 2>&1; then RESULTS+=("PASS  $name"); else RESULTS+=("FAIL  $name"); FAILED=1; fi
}
netem_test() {
    sudo tc qdisc add dev lo root netem delay 1ms && sudo tc qdisc del dev lo root
}
# 先把 mn 的输出完整存到文件再判断。直接接 "| grep -q" 的话，grep 匹配后提前退出，
# mn 会因为管道被关而返回非 0，在 pipefail 下即使 ping 全通也会被判成失败。
mn_test() {
    sudo mn -c >/dev/null 2>&1 || true
    sudo mn --switch ovsk --link tc,bw=10,delay=5ms --test pingall >"$LOG_DIR/mn-tclink.log" 2>&1 || true
    grep -q ' 0% dropped' "$LOG_DIR/mn-tclink.log"
}
# 和 Lab 3 一样的跑法：Ryu 做远程控制器，Mininet 连上去 pingall
ryu_e2e_test() {
    local pid
    sudo mn -c >/dev/null 2>&1 || true
    ryu-manager ryu.app.simple_switch_13 >"$LOG_DIR/ryu.log" 2>&1 &
    pid=$!
    sleep 5
    sudo mn --switch ovsk --controller remote --wait --test pingall >"$LOG_DIR/mn-ryu.log" 2>&1 || true
    kill "$pid" 2>/dev/null || true
    grep -q ' 0% dropped' "$LOG_DIR/mn-ryu.log"
}
mkdir -p "$LOG_DIR"
check "ovs-vsctl 可用"                         sudo ovs-vsctl show
check "ryu-manager 可用"                       ryu-manager --version
check "hping3 已安装"                          command -v hping3
check "iperf 已安装"                           command -v iperf
check "matplotlib 可导入"                      python3 -c 'import matplotlib'
check "tc netem（链路时延）"                   netem_test
check "Mininet + OVS + TCLink pingall"         mn_test
check "Ryu 控制器 + Mininet 端到端 pingall"    ryu_e2e_test
sudo mn -c >/dev/null 2>&1 || true
printf '  %s\n' "${RESULTS[@]}"
grep -h 'Results:' "$LOG_DIR"/mn-*.log 2>/dev/null | sed 's/^/    /' || true

# ---------- 7. 汇总 ----------
step "完成"
cat <<EOF
  常用命令：
      ryu-manager --observe-links <controller>.py
      sudo mn --switch ovsk --controller remote --custom <topo>.py --topo <name>
      sudo -E python3 ~/mininet/examples/miniedit.py      # 图形界面，SSH 里先 export DISPLAY=:0
      $RYU_VENV/bin/pip install <包名>                     # 给控制器加 Python 依赖
EOF

if [ "$FAILED" -ne 0 ]; then
    die "有自检项失败（见上面的 FAIL）。完整输出在 $LOG_DIR/ 下。"
fi
ok "所有自检通过"
