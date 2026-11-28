# bus — mailbox asinkron + job queue lintas agen & host

`server.py` — satu file HTTP stdlib, bind `127.0.0.1:8810`, SQLite WAL
append-only di `BUS_DB` (default `/var/lib/warroom-bus/bus.db`).

## Endpoint

| Metode | Path | Auth | Kerja |
|---|---|---|---|
| GET | `/bus/health` | — | liveness `{ok, ts}` |
| GET | `/bus/ui` | — | papan status HTML (heartbeat + 25 job) — **baca SECURITY.md sebelum mengekspos** |
| GET | `/bus/messages?topic&since&limit&agent` | ✓ | baca pesan; `agent` memajukan cursor |
| GET | `/bus/unread?agent` | ✓ | hitung belum-dibaca per topik |
| GET | `/bus/topics` | ✓ | topik + jumlah + ts terakhir |
| GET | `/bus/agents` | ✓ | agen aktif per host |
| GET | `/bus/job/claim?host` | ✓ | klaim job `queued` tertua (priority asc); atomic, lease 5 mnt |
| GET | `/bus/job/status?id` | ✓ | `{state, cancel_req, exit_code}` — dipoll daemon saat eksekusi |
| GET | `/bus/job/list?state` | ✓ | 100 job terakhir |
| POST | `/bus/post` | ✓ | `{topic, agent, host, kind, text, refs}` — identitas agent harus cocok token |
| POST | `/bus/job/post` | ✓ | `{host, mode, argv[], dedupe, after_id, ttl_sec, timeout_sec, env_profile, priority}` |
| POST | `/bus/job/result` | ✓ | hanya agen pengklaim (409 selainnya); menulis audit `job/<id>` |
| POST | `/bus/job/cancel` | ✓ | `queued`→`cancelled`; `claimed`→`cancel_req` (daemon kill) |
| POST | `/bus/enroll` | master | `{host, agent?}` → mint `{agent, token}` di registry; token tampil sekali. `400` nama tak sah · `403` non-master · `409` duplikat · `500` registry rusak — file tak pernah ditimpa diam-diam. Menulis audit `audit` |

Reaper internal tiap 60 dtk: lease basi → `queued` ulang; `queued` lewat
`ttl_sec` → `expired`; anak `after_id` dari induk gagal → `cancelled`;
`schedule.next_due` lewat → materialisasi job `kind=sched`.

## Auth

`X-Bus-Token`: token master dari env `BUS_TOKEN`, atau token per-agen di
`BUS_TOKENS_FILE` (default `/home/admin/bus/agents.json`, format
`{"tokens": {"<agent>": "<token>"}}` — dibaca ulang tiap request → rotasi
tanpa restart). Token per-agen hanya boleh bertindak sebagai identitasnya;
token master (`*`) boleh atas nama siapa pun — dan **hanya master** yang boleh
`POST /bus/enroll` (registry = root of trust). Lihat `agents.example.json`.

## Isi direktori

| File | Peran |
|---|---|
| `server.py` | server + schema + reaper + UI |
| `talk` | CLI bash untuk post/read/watch |
| `backup_bus_db.py` | backup `.backup` sqlite harian (cron) |
| `agents.example.json` | contoh format token — file asli tidak pernah masuk repo |

## Deploy

`ops/warroom-bus.service` (systemd, `ProtectSystem=strict` + `ReadWritePaths`
ke direktori DB). Env: `BUS_PORT`, `BUS_DB`, `BUS_TOKEN`, `BUS_TOKENS_FILE` —
**wajib menunjuk path yang bisa ditulis service** (mis. `/var/lib/warroom-bus/agents.json`),
bukan path read-only di `~/bus/` — `/bus/enroll` menulis registry ini.
Ekspos publik lewat nginx `https://<host>/bus/*` → `127.0.0.1:8810` —
klien jarak jauh cukup HTTPS :443.
