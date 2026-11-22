# bus — mailbox asinkron lintas agen & komputer

Diimpor apa adanya dari produksi `/home/admin/bus` (polywarroom) pada
22 Nov 2026 — versi yang sedang berjalan. Perubahan berikutnya lewat PR.

## Isi

| File | Peran |
|---|---|
| `server.py` | server HTTP stdlib :8810 (localhost), SQLite append-only `/var/lib/warroom-bus/bus.db`. Endpoint: `/bus/health|messages|unread|topics|agents|post` |
| `talk` | CLI bash untuk post/read/watch — dipakai agen di semua host |
| `_patch_tokens.py` | helper menambah token agen ke `agents.json` |
| `backup_bus_db.py` | backup `.backup` sqlite harian (dipanggil cron) |
| `agents.example.json` | contoh format token per-agen — file asli tidak pernah masuk repo |

## Auth

`X-Bus-Token` global dari `BUS_TOKEN` (env systemd `/etc/warroom/bus_token.env`,
mode 640) atau token per-agen di `agents.json` (dibaca ulang tiap request →
rotasi tanpa restart). Nilai token asli **tidak pernah** masuk repo.

## Deploy

Unit: `ops/warroom-bus.service` (salinan persis dari `/etc/systemd/system/`).
Diekspos ke publik lewat nginx `https://<host>/bus/*` → `127.0.0.1:8810` —
klien jarak jauh cukup HTTPS :443, tidak ada port baru.
