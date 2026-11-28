# Design — `armada enroll`: enrollment node tanpa jumphost

Tanggal: 2026-11-23 · Status: disetujui (owner: "gas B")

## Maksud

Menambah host ke armada hari ini butuh dua SSH: edit `agents.json` di host bus,
dan jalanin `install.sh` di node. Dari jaringan yang memblokir port 22
(WiFi kantor IOHGuest) itu memaksa jumphost. Padahal desain Armada sudah
outbound-only — enrollment adalah satu-satunya titik yang masih menuntut SSH.

Sasaran: **enrollment 100% lewat bus `:443`** — laptop hanya bicara ke bus,
mendapat satu baris bootstrap yang bisa ditempel ke channel apa pun yang sudah
ada ke host (Tencent TAT console, web shell provider, atau SSH bila jaringan
mengizinkan). Setelah itu node poll keluar; tak ada inbound selamanya.

## Goals / non-goals / anti-goals

- Goal: `armada enroll --host <nama>` mencetak baris bootstrap siap tempel.
- Goal: token per-agen dibuat server-side; tidak perlu edit `agents.json` manual.
- Non-goal: mengubah policy engine, capability ladder, atau deny-first.
- Non-goal: self-register dengan kode sekali-pakai (opsi C — mungkin tahap 2).
- Anti-goal: token agen lain boleh memint token baru (eskalasi hak) — endpoint
  wajib menolak semua identitas selain master.

## Pendekatan yang ditimbang

- **A. Docs saja** — enroll manual via `ssh -J` + dokumentasi. Nol kode,
  tapi enrollment tetap manual selamanya. Ditolak.
- **B. `POST /bus/enroll` + `armada enroll` (dipilih)** — satu endpoint
  registry di bus + satu subperintah CLI. Sesuai filosofi single-file stdlib.
- **C. Self-register dengan enrollment code** — token tak transit clipboard;
  menambah state machine di bus. Ditunda.

## Desain

### `POST /bus/enroll` (bus/server.py)

- Whitelist path baru di `do_POST`; setelah `_auth()` wajib `identity == "*"`
  (master env `BUS_TOKEN`), selain itu → 403.
- Body: `{"host": "<h>", "agent": "<nama?>"}`. Nama default `wr-node-<host>`;
  validasi `[A-Za-z0-9._-]{1,64}` → 400 bila tak sah, 409 bila sudah ada.
- Token: `"bus-" + secrets.token_hex(32)` (stdlib `secrets`).
- Registry: file `BUS_TOKENS_FILE` (tetap `{"tokens": {nama: token}}`) —
  read-modify-write di bawah `threading.Lock` (ThreadingHTTPServer), ditulis
  atomik via `<path>.tmp` + `os.replace`, mode 600 bila file baru.
  `agent_tokens()` sudah baca ulang tiap request → token langsung aktif.
- Respons `{"ok": true, "agent", "token", "host"}` — token tampil sekali di
  respons ini; tidak ada endpoint baca-token.

### `armada enroll` (cli/armada.py)

`armada enroll --host <nama> [--agent <nama>] [--wait <dtk>]`:

1. `POST /bus/enroll` → cetak agen + baris bootstrap:
   `curl -fsSL https://raw.githubusercontent.com/MaximaLabs/armada/main/ops/install.sh | bash -s -- --bus <BUS_URL-tanpa-/bus> --token <tok> --host <nama>`
   (`BUS_URL` di agent.env membawa suffix `/bus`; node.env tidak — strip).
2. `--wait N` (default 0): poll `health/<host>` tiap 5 dtk sampai heartbeat
   pertama atau timeout → konfirmasi node hidup tanpa SSH.

### Constraint produksi (penting)

`warroom-bus.service` berjalan dengan `ProtectSystem=strict` +
`ReadWritePaths=/var/lib/warroom-bus` → service **tidak bisa menulis** ke
`/home/admin/bus/agents.json`. Maka registry dipindah ke state dir:

- `agents.json` → `/var/lib/warroom-bus/agents.json` (mode 640 root:admin —
  service jalan sebagai `admin`, cukup baca+tulis).
- `BUS_TOKENS_FILE=/var/lib/warroom-bus/agents.json` ditambah ke
  `/etc/warroom/bus_token.env` (EnvironmentFile yang sudah ada → cukup
  restart, tanpa edit unit).
- File lama di `~/bus/agents.json` dikosongkan/dibuang setelah migrasi terbukti
  (jangan biarkan salinan token kedaluwarsa bertebaran).
- Deploy: `scp server.py` via `ssh warroom` (wstunnel :443 — jalan dari kantor),
  `sudo -n systemctl restart warroom-bus` (NOPASSWD sesuai catatan).

### Tes (tests/test_bus_api.py)

Kontrak baru: enroll tanpa token → 401; token agen (bukan master) → 403;
master → 200 + token `bus-<64hex>`; nama duplikat → 409; nama aneh → 400;
token baru langsung sah dipakai `POST /bus/post` sebagai agen baru;
file registry tertulis ke `BUS_TOKENS_FILE` temporer.

## Yang tersisa untuk builder

- Pesan CLI bahasa Indonesia, gaya mengikuti subperintah lain.
- README quickstart + node/README disegarkan ke alur enroll.
- Pendaftaran `vps-dash` produksi menyusul setelah merge (langkah operasional,
  bukan bagian patch ini).
