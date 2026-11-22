#!/usr/bin/env bash
# install.sh — pasang wr-node di host ini (user-level systemd, nol root).
#
# Pemakaian:
#   curl -fsSL <repo>/ops/install.sh | bash -s -- \
#       --bus https://bus.example.com --token <token> --host <nama-host>
#
#   # atau dari checkout lokal:
#   bash ops/install.sh --bus http://127.0.0.1:8810 --token t --host devbox
#
# Yang dilakukan: salin wr_node.py ke ~/armada, tulis env+policy contoh ke
# ~/.config/armada (tidak menimpa), pasang unit user, start, verifikasi health.
set -euo pipefail

BUS_URL="" ; TOKEN="" ; HOST_NAME="$(hostname -s 2>/dev/null || hostname)"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd -P 2>/dev/null || echo)"

while [ $# -gt 0 ]; do
    case "$1" in
        --bus)   BUS_URL="$2"; shift 2;;
        --token) TOKEN="$2"; shift 2;;
        --host)  HOST_NAME="$2"; shift 2;;
        *) echo "arg tak dikenal: $1" >&2; exit 2;;
    esac
done
[ -n "$BUS_URL" ] && [ -n "$TOKEN" ] || {
    echo "wajib: --bus <url> --token <token> [--host <nama>]" >&2; exit 2; }
BUS_URL="${BUS_URL%/}"   # TANPA suffix /bus — daemon menambahkannya sendiri

mkdir -p "$HOME/armada" "$HOME/.config/armada" "$HOME/.config/systemd/user"

# sumber file: checkout lokal, atau unduh dari repo
if [ -f "$SRC_DIR/node/wr_node.py" ]; then
    cp "$SRC_DIR/node/wr_node.py" "$HOME/armada/"
    cp "$SRC_DIR/node/policy.example.json" "$HOME/.config/armada/policy.json.example"
    cp "$SRC_DIR/ops/wr-node.service" "$HOME/.config/systemd/user/wr-node.service"
else
    BASE="https://raw.githubusercontent.com/MaximaLabs/armada/main"
    curl -fsSL "$BASE/node/wr_node.py" -o "$HOME/armada/wr_node.py"
    curl -fsSL "$BASE/node/policy.example.json" -o "$HOME/.config/armada/policy.json.example"
    curl -fsSL "$BASE/ops/wr-node.service" -o "$HOME/.config/systemd/user/wr-node.service"
fi

# env & policy: tulis hanya bila belum ada (jangan timpa konfigurasi jalan)
if [ ! -f "$HOME/.config/armada/node.env" ]; then
    cat > "$HOME/.config/armada/node.env" <<EOF
BUS_URL=$BUS_URL
BUS_TOKEN=$TOKEN
WR_HOST=$HOST_NAME
HEALTH_SEC=90
JOB_SEC=7
EOF
    chmod 600 "$HOME/.config/armada/node.env"
else
    echo "~/.config/armada/node.env sudah ada — tidak ditimpa"
fi
[ -f "$HOME/.config/armada/policy.json" ] || \
    cp "$HOME/.config/armada/policy.json.example" "$HOME/.config/armada/policy.json"

systemctl --user daemon-reload
systemctl --user enable --now wr-node
sleep 2
systemctl --user --no-pager status wr-node | head -8
echo
echo "wr-node terpasang untuk host '$HOST_NAME' → $BUS_URL"
echo "Verifikasi heartbeat: curl -s '$BUS_URL/bus/messages?topic=health/$HOST_NAME' \\"
echo "    -H 'X-Bus-Token: <token-agen-anda>'"
