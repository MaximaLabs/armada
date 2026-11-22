# Superplan: Armada Agen & Daemon `wr-node`

> Proyek lab **MaximaLabs** — https://maximalabs.tech

> Status: **rancangan — menunggu pengesahan owner** (22 Nov 2026)
> Penulis: Devin, berdasarkan diskusi owner + audit lapangan
> Dokumen ini adalah *plan-of-record* untuk visi "semua agen menjangkau semua
> server, dari jaringan mana pun, dan bisa hidup di host mana pun".

---

## 1. Visi

Empat properti yang ingin dicapai (dari owner):

1. **Semua agen menjangkau semua server** — Devin (laptop), Hermes, agy CLI,
   DeepSeek harness, dan bot memoh nantinya bisa melihat kesehatan server dan
   mengeksekusi tugas terkontrol di tiap host.
2. **Tembus blokir jaringan** — tetap bekerja dari wifi kantor yang memblokir
   port SSH, server di balik CGNAT/NAT tanpa port-forward, firewall inbound
   penuh. Semua lewat koneksi keluar :443.
3. **Agen tidak terikat host** — server A mati → agen hidup di server B atau
   laptop. Job yang sedang dipegang agen mati kembali ke antrian.
4. **Beban ringan** — daemon setipis mungkin; yang berat (memoh) ditaruh di
   host terpisah, bukan server produksi.

## 2. Fondasi yang SUDAH ada (bukan proposal)

Komponen berikut sudah berjalan di produksi — superplan ini membangun **di
atasnya**, bukan mengganti:

| Komponen | Lokasi | Peran dalam visi |
|---|---|---|
| `warroom-bus` (`/home/admin/bus/server.py`, :8810 lokal, HTTPS via nginx) | webdock | **Mailbox**: SQLite append-only, topik + cursor per-agen, token per-agen, tanpa delete via API. Docstring sendiri: *"agent di mesin berbeda (Webdock, cyber1, instabox, laptop) perlu saling meninggalkan catatan tanpa SSH fan-in"* |
| `wstunnel` SSH :443 | webdock | Akses manusia lewat port web — tembus blokir :22 |
| `tailscaled` | webdock | Mesh VPN, NAT traversal + DERP relay |
| `ttyd`, `novnc` | webdock | Terminal & desktop MT5 lewat browser :443 |
| `hermithub` (:8787) | laptop | Dashboard agen di laptop |
| Backup postgres+bus harian | webdock → `~/backups/` | Restore control plane |

**Armada yang diakui hari ini**: `polywarroom` (webdock), `cyber1`, laptop
owner, instabox (`box-2aacb3`). VM2 Azure (`mt5-trader-vm2`) **BUKAN** anggota
— host live terproteksi, tidak pernah menerima job.

## 3. Arsitektur target

```
┌─────────────── Agen (lokasi bebas) ───────────────┐
│  Devin@laptop   Hermes   agy CLI   DeepSeek       │
│  bot memoh (nanti, workspace container)           │
└────────┬──────────────────────────────────────────┘
         │ HTTPS :443 — POST job + baca hasil
         ▼
   warroom-bus (mailbox; direplikasi; satu-satunya
                 permukaan publik baru = endpoint /bus/job/*)
         ▲                ▲                ▲
   wr-node@polywr   wr-node@cyber1   wr-node@instabox
   poll job outbound :443 → eksekusi allowlist → POST result
   + heartbeat & health snapshot ke topik health/<host>
```

Prinsip kunci: **server tidak pernah mendengarkan port baru**. `wr-node`
hanya membuat koneksi keluar ke bus — host di jaringan apa pun tetap bisa
jadi anggota armada.

### 3.1 Tiga tingkat kapabilitas `wr-node`

| Tier | Isi | Status rollout |
|---|---|---|
| **T1 — health** | heartbeat + snapshot berkala: unit gagal, disk, load, mem, paket upgradable, uptime; diposting ke `health/<host>` | P1 |
| **T2 — exec allowlist** | job = `{program, argv[]}` tanpa shell; hanya perintah di policy (`systemctl status`, `journalctl -u`, `df`, `git -C status`, `psql` read) | P2 |
| **T3 — worker** | job panjang: backup-test, ingest run, sinkronisasi; stream log ke bus; grant per jenis job | P4 |

### 3.2 Semantik job di bus

Tabel baru `job` (aditif, tabel `msg`/`cursor` tidak disentuh):

```
job(
  id TEXT PK,            -- uuid dari pembuat job
  host TEXT NOT NULL,    -- sasaran; '*' = siapa pun boleh klaim
  agent TEXT NOT NULL,   -- peminta (dari token)
  kind TEXT NOT NULL,    -- 'exec' | 'worker' | 'query'
  argv TEXT NOT NULL,    -- JSON array, tanpa shell
  state TEXT NOT NULL,   -- queued|claimed|done|failed|expired
  lease_until REAL,      -- failover: lewat batas → balik 'queued'
  claim_agent TEXT, claim_host TEXT,
  exit_code INTEGER, stdout TEXT, stderr TEXT,   -- dipotong 64KB
  ts_post REAL, ts_claim REAL, ts_done REAL
)
```

Endpoint baru:
- `POST /bus/job/post` — enqueue (auth agen)
- `GET  /bus/job/claim?host=<h>&agent=<a>` — atomik: ambil job queued
  milik host ini, set `claimed` + `lease_until` (mis. +300 dtk)
- `POST /bus/job/result` — daemon laporkan `exit_code/stdout/stderr`;
  sekalian menulis pesan `kind='result'` ke topik `job/<id>` → audit
  otomatis mengikuti pola diskusi yang sudah ada
- `GET  /bus/job/list?state=...` — pantau antrian
- Reaper internal di server.py: tiap menit, `claimed` dengan
  `lease_until < now` → `queued` (failover tanpa komponen baru)

### 3.3 `wr-node` (daemon per host, ~150 baris, Python stdlib saja)

Mengikuti gaya `server.py`: satu file, nol dependensi, systemd unit
hardened (`NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`).

```
loop:
    heartbeat → POST /bus/post topic=health/<host> (tiap 90±15 dtk)
    claim     → GET /bus/job/claim?host=<ini>
    jika ada  → verifikasi argv ∈ policy.allow[host]
              → subprocess.run(argv, timeout, capture, cwd=allowdir)
              → POST /bus/job/result
    sleep 5–10 dtk (backoff bila bus tak terjangkau; agen standby, bukan mati)
```

Batas beban kerja (bagian yang benar-benar bisa memberatkan host):
`max 1 job bersamaan`, `timeout` per jenis job, output dipotong 64KB,
`deny` pola berat/merusak di policy (`rm`, `dd`, `find /`, `docker`,
`systemctl restart|stop` kecuali unit allowlist, akses path terlarang).

### 3.4 Policy armada — `fleet-policy.json`

Satu file (awalnya di samping `agents.json`, lalu dipindah ke repo agar
perubahan lewat PR):

```json
{
  "agents": {
    "devin":    {"hosts": {"polywarroom": ["health","exec"], "cyber1": ["health"]}},
    "hermes":   {"hosts": {"polywarroom": ["health","exec"], "instabox": ["health","exec"]}},
    "memoh-*":  {"hosts": {"polywarroom": ["health"]}}
  },
  "exec_allow": {
    "polywarroom": ["systemctl status *", "journalctl -u * -n 200", "df -h",
                    "free -m", "git -C /home/admin/warroom *", "uptime"],
    "cyber1":      []
  },
  "deny_always": ["sudo", "rm ", "dd ", "mkfs", "reboot", "shutdown",
                  "mt5-trader-vm2", "36525553", "/opt/polymarket",
                  "/etc/poly-pilot", "tencent"]
}
```

`deny_always` menang di tingkat policy — bukan di argv — sehingga domain
terlarang tidak bisa disentuh dari jalur mana pun.

### 3.5 Kenapa bukan Rust / bukan memoh / bukan SSH

- **Bukan Rust**: bus + wr-node I/O-bound; biaya riil ada pada perintah
  yang dieksekusi, bukan pada daemon. Stdlib Python sudah terpasang di
  semua host → nol toolchain, ~15–20MB RSS, CPU nol saat idle.
  (`fast-anything` disimpan untuk kasus CPU-bound: hot path backtest di
  `packages/live-trading`, bukan untuk daemon.)
- **Bukan memoh sebagai daemon**: memoh adalah *rumah agen* (postgres +
  pgvector + containerd + desktop per bot) — berat dan menjawab masalah
  berbeda. Tempatkan di host khusus/cloud; bot-nya tetap menjangkau
  server produksi lewat bus+wr-node yang terbatas. "Computer" memoh
  (desktop penuh) hanya untuk dev box, **tidak** untuk server produksi.
- **Bukan SSH fan-in**: itulah masalah yang sudah diselesaikan bus —
  dan SSH justru diblokir di banyak jaringan sasaran.

## 4. Failover & ketahanan

| Skenario | Perilaku |
|---|---|
| Agen mati saat pegang job | `lease_until` lewat → job balik `queued`, agen/host lain mengklaim |
| Server sasaran mati | heartbeat `health/<host>` berhenti → terlihat di papan; job menumpuk `queued` sampai host hidup |
| Bus (webdock) mati | semua agen standby + backoff; bus direstore dari backup `~/backups/` di host lain dalam hitungan menit; endpoint stabil via nginx/tunnel sehingga alamat tidak berubah |
| Semua server mati | agen tetap hidup di laptop; menyalakan kembali armada saat host pulih |

Tambahan kecil untuk retensi: janitor memangkas topik `health/*` (simpan
snapshot terakhir per host + buang >7 hari) agar `bus.db` tidak
membengkak — append-only diskusi tetap utuh, hanya deret health yang
diringkas.

## 5. Model ancaman

- **Endpoint /bus/job/\* = RCE-by-design** → wajib: token per-agen, TLS
  via nginx, policy allow/deny di server, audit append-only.
- **Token bocor** → blast radius dibatasi policy per-agen; rotasi = edit
  `agents.json` (dibaca ulang tiap request, tanpa restart — sudah ada).
- **Host palsu mengklaim job host lain** → claim diverifikasi: token
  agen daemon berbeda dari token agen pekerja; `claim_agent` dicatat.
- **Replay** → `job.id` unik + `nonce`; hasil kedua ditolak bila state
  bukan `claimed` oleh penyerang.
- **Agen jahat/buggy flood** → rate limit per token + `max_jobs` host.
- **Kill switch owner** → `/etc/warroom/fleet-deny` (pola poly-pilot):
  daemon & endpoint job berhenti total selama file ada. Hanya owner.

## 6. Tahapan rollout

| Fase | Isi | Bukti |
|---|---|---|
| **P0** | Dokumen ini disahkan; `bus/` diangkat ke repo (`services/bus/` atau `ops/bus/`) apa adanya agar ter-version | PR docs + PR impor kode |
| **P1** | `wr-node` T1 di polywarroom: heartbeat + snapshot ke `health/polywarroom`; halaman/papan menampilkan status armada | unit aktif + pesan health di bus |
| **P2** | Job semantics di server.py + policy + T2 exec allowlist di polywarroom | job nyata (`df -h`) lewat bus end-to-end |
| **P3** | `wr-node` di host kedua (cyber1 atau instabox) → multi-host terbukti | 2 host heartbeat + job silang |
| **P4** | T3 worker (backup-test, ingest) + memoh deploy di host khusus + bot pertama ikut armada | job panjang + audit lengkap |

## 7. Keputusan terbuka (owner)

1. **Lokasi kode bus di repo** — `services/bus/` (sejajar service lain)
   atau `ops/bus/` (tool infra)? Usul: `services/bus/`.
2. **Host kedua pertama** — cyber1 atau instabox?
3. **Memoh**: waitlist = cloud atau self-host? Kalau self-host: host mana
   (usul: bukan polywarroom — stack berat di samping MT5/Wine + postgres).
4. **Laptop** masuk armada sebagai `wr-node` juga? (berguna: agen di
   server bisa meminta laptop menjalankan sesuatu saat online)

## 8. Non-goal (dikesampingkan)

- Desktop penuh ("Computer" ala memoh) di server produksi — terlalu luas.
- Rust/binary untuk bus atau wr-node — tidak menyelesaikan beban riil.
- Mengubah `msg`/`cursor` yang sudah produksi — semua aditif.
- VM2, `/opt/polymarket`, Tencent, gate poly-pilot sebagai anggota/job —
  tetap terlarang.
