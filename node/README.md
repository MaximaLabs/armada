# wr-node — daemon armada per host

Satu file Python stdlib (`wr_node.py`), user-level systemd, nol dependensi.
Keluar-only ke `BUS_URL` — host tidak pernah membuka port.

## Install per host

```bash
bash ops/install.sh --bus https://bus.example.com --token <token> --host <nama>
```

…atau manual:

```bash
mkdir -p ~/armada ~/.config/armada ~/.config/systemd/user
cp wr_node.py ~/armada/
cp node.example.env ~/.config/armada/node.env   # isi BUS_TOKEN agen daemon
cp policy.example.json ~/.config/armada/policy.json
cp ../ops/wr-node.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now wr-node
journalctl --user -u wr-node -f                        # verifikasi
curl -s "$BUS_URL/bus/messages?topic=health/<host>" -H "X-Bus-Token: <token>"
```

## Kerja

- **Heartbeat** tiap `HEALTH_SEC` (±jitter) → topik `health/<host>`:
  uptime, load, mem, `df /`, unit gagal, versi daemon.
- **Job loop** tiap `JOB_SEC` → `GET /bus/job/claim?host=<host>`:
  eksekusi sesuai `mode` (lihat ladder di README utama), streaming potongan
  stdout ke `job/<id>` tiap ~5 dtk, hasil akhir ke `/bus/job/result`.
  Bus lama tanpa endpoint job (404) = "tanpa job" — daemon tetap hidup.

## Capability ladder (semua mode terimplementasi)

| `mode` | Jalur eksekusi | Sumber grant |
|---|---|---|
| `allow` | `argv` strict-match per-token lawan `exec_allow.<host>` | `agents.<agent>.<host>` ⊇ `allow`, atau policy lama tanpa `agents` |
| `user` | `argv` langsung sebagai user daemon | grant `user` |
| `root` | `sudo -n <argv>` — butuh sudoers daemon sendiri | grant `root` |
| `sandbox` | `docker run --rm --network <p> --read-only --memory … <image> <argv>` | grant `sandbox` + `sandbox_profiles.<nama>` |

`deny_always` dievaluasi **sebelum** grant apa pun di semua mode.
Kill switch: `/etc/warroom/fleet-deny` atau `/etc/armada/deny` ada → semua
exec ditolak. Job boleh membawa `env_profile` — daemon menyuntik env dari
`~/.config/armada/env/<nama>.env` (mode 600) atau `/etc/armada/env/`;
rahasia tidak pernah lewat bus.

## Konfigurasi (`node.env`)

`BUS_URL` (tanpa suffix `/bus` — daemon menambahkannya), `BUS_TOKEN`,
`WR_HOST`, `HEALTH_SEC`, `JOB_SEC`, `JOB_TIMEOUT_SEC`, `WR_POLICY`.
