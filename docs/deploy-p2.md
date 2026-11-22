# Status deploy bus v2 — 22 Nov 2026

**Job queue SUDAH LIVE** lewat instance kedua `warroom-bus-v2.service`
(systemd --user admin, :8811) yang berbagi `bus.db` yang sama dengan
produksi :8810. Produksi tidak disentuh — pendekatan interim tanpa sudo.

- `bus.db` milik `admin` + WAL → dua instance aman; claim job atomik.
- wr-node polywarroom mengarah ke :8811 → heartbeat + eksekusi job jalan.
- wr-node laptop mengarah ke URL publik (→ :8810) → heartbeat saja untuk
  sementara (job endpoint belum terekspos nginx).
- `/bus/ui` hidup di :8811 lokal (belum lewat nginx).

## Yang terverifikasi live di produksi (DB nyata)

`df -h` allow ✅ · `user` mode (argv bebas sbg admin) ✅ · `sandbox`
(alpine container, `--network none --read-only`) ✅ · `root` ditolak policy
sesuai grants ✅ · dedupe/cancel/lease/wrong-agent-409 ✅ (uji lokal)

## Path final (bila owner siap, ~2 menit)

```bash
sudo cp /home/admin/bus/server.py /home/admin/bus/server.py.bak.$(date +%Y%m%d)
sudo cp /home/admin/bus/server-v2.py /home/admin/bus/server.py
sudo systemctl restart warroom-bus
systemctl --user stop --now warroom-bus-v2  # sebagai admin
```

Lalu kembalikan `BUS_URL` wr-node polywarroom ke `http://127.0.0.1:8810`.
Rollback: restore .bak + restart.
