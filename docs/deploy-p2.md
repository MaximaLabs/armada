# Status deploy bus — 22 Nov 2026 (P4 selesai)

**Bus v2 = produksi.** `warroom-bus.service` (:8810) menjalankan kode penuh:
job queue, capability ladder, env_profile, streaming, cancel, kill switch,
per-agent tokens. Instance interim `warroom-bus-v2` (:8811) sudah stop+disable.
Rollback: `sudo cp /home/admin/bus/server.py.bak.20261122 server.py` + restart.

## Eksposur publik

`https://polywarroom.vps.webdock.cloud/bus/` → `127.0.0.1:8810` (nginx `webdock`).

| Endpoint publik | Status |
|---|---|
| `GET /bus/health` | 200 — sengaja publik |
| `GET /bus/ui` | **403** — unauthenticated + menampilkan hostname/status; tetap bisa dibuka lokal `curl 127.0.0.1:8810/bus/ui` |
| sisanya | token `X-Bus-Token` wajib (per-agent dari `agents.json` / master `BUS_TOKEN`) |

## Fleet status

- `polywarroom` — wr-node → `http://127.0.0.1:8810`, heartbeat+job ✅
- `laptop` — wr-node → URL publik, heartbeat+job ✅ (terverifikasi `user` mode exit 0 lewat domain)
- `cyber1` — wr-node → URL publik, heartbeat ✅

## Terverifikasi lewat URL publik

`job_post` user+allow mode → claim laptop → done. `allow` exit 126 untuk
argv non-allowlist = policy bekerja.
