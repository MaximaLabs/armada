# wr-node — daemon armada per host

Satu file Python stdlib (`wr_node.py`), user-level systemd, nol dependensi.

## Install per host

```bash
mkdir -p ~/armada ~/.config/armada ~/.config/systemd/user
cp wr_node.py ~/armada/
cp node.example.env ~/.config/armada/node.env   # isi BUS_TOKEN agen daemon
cp policy.example.json ~/.config/armada/policy.json
cp ops/wr-node.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now wr-node
journalctl --user -u wr-node -f                        # verifikasi
curl -s "$BUS_URL/bus/messages?topic=health/<host>" -H "X-Bus-Token: <token>"
```

Daemon koneksi keluar saja ke `BUS_URL` — tidak membuka port.

## Tier versi ini (v0.1)

- `health`: heartbeat + snapshot → `health/<host>`
- `exec allow`: klaim `/bus/job/claim`, strict-match per-arg policy,
  `timeout`, output dipotong 64KB → `/bus/job/result`
- `sandbox`/`user`/`root`: tahap berikut (job ditolak bila bus belum
  mengenal endpoint — 404 diperlakukan "tanpa job").
