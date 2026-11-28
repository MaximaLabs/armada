# Armada Enroll Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /bus/enroll` (master-only) + `armada enroll` sehingga host baru masuk armada tanpa SSH/jumphost dari laptop.

**Architecture:** Bus mendapat satu endpoint registry yang menulis `BUS_TOKENS_FILE` atomik di bawah lock; CLI mendapat subperintah yang mencetak baris bootstrap `install.sh` siap tempel ke channel apa pun (TAT console, web shell, SSH). Node tetap poll-keluar — tak ada komponen baru.

**Tech Stack:** Python 3.10+ stdlib saja (`secrets`, `re`, `threading`, `os`, `json`). Zero runtime deps — batas keras repo.

**Spec:** `docs/superpowers/specs/2026-11-23-enroll-tanpa-jumphost-design.md`

## Global Constraints

- File tunggal + stdlib: jangan pecah `server.py`/`armada.py` jadi paket, jangan impor non-stdlib.
- Policy engine (`allowed()`, `mode_granted()`, `_denied()`, deny-first) **tidak disentuh** — enroll murni registry agen di sisi bus.
- Tidak ada secret di repo: `agents.json`, `*.env`, token tidak pernah di-commit; placeholder `<token-agen>`.
- Komentar/docstring internal Bahasa Indonesia menjawab *kenapa*; commit Conventional Commits BI, tanpa atribusi AI.
- Verifikasi wajib sebelum commit: `make test` (py_compile + test_policy + test_bus_api).
- Endpoint `/bus/enroll` **wajib menolak** semua identitas selain master (`identity == "*"`) — agen tak boleh memint token (eskalasi hak).
- Token agen format `"bus-" + secrets.token_hex(32)`; nama agen validasi `^[A-Za-z0-9._-]{1,64}$`.

## Review Focus

1. `BUS_TOKENS_FILE` belum ada (install fresh) → enroll harus membuat `{"tokens":{…}}`, bukan crash — dipin Task 1 langkah tes.
2. Token agen biasa memanggil `/bus/enroll` → 403, bukan mint token — dipin Task 1.
3. Nama host mengandung karakter aneh (`h; rm -rf`, spasi, unicode) → 400, bukan nama agen tercemar — dipin Task 1.
4. Re-enroll host yang sama → 409, bukan timpa token lama diam-diam — dipin Task 1.
5. `BUS_URL` di `agent.env` membawa suffix `/bus` tapi `node.env` tidak → baris bootstrap yang dicetak CLI harus men-strip suffix itu, kalau tidak node akan memanggil `/bus/bus/…` — dipin Task 2.
6. Dua enroll bersamaan (ThreadingHTTPServer) → read-modify-write di bawah `threading.Lock`; tak dites unit, dicatat di sini.

---

### Task 1: Endpoint `POST /bus/enroll` di bus + tes kontrak

**Files:**
- Modify: `bus/server.py` (impor `secrets`, `re`; lock modul; whitelist path; handler)
- Test: `tests/test_bus_api.py` (tambah blok assert di `main()`, setelah blok job lifecycle, sebelum `print` sukses — baca dulu ekor main untuk lokasi persis)

**Interfaces:**
- Consumes: `token()`, `agent_tokens()`, `_auth()`, `_send()`, `_body()` yang sudah ada di `H`.
- Produces:
  - `POST /bus/enroll` — body `{"host": str, "agent": str?}` → `200 {"ok": true, "agent": str, "token": str, "host": str}`; `400` nama tak sah; `401` tanpa token; `403` non-master; `409` agen sudah ada.
  - `def enroll_agent(host: str, name: str) -> str` — fungsi modul: validasi→generate→tulis atomik; mengembalikan token; melempar `ValueError(msg)` untuk 400/409 (pemanggil memetakan "sudah ada"→409, lainnya→400).

- [ ] **Step 1: Tulis tes gagal**

Di `tests/test_bus_api.py` `main()`, blok baru setelah kontrak job:

```python
# --- enroll: hanya master --------------------------------------------
c, _ = req("POST", bus.port, "/bus/enroll")
assert c == 401, c
c, _ = req("POST", bus.port, "/bus/enroll", token="tok-agent",
           body={"host": "h9"})
assert c == 403, c
c, r = req("POST", bus.port, "/bus/enroll", token="tok-master",
           body={"host": "h9"})
assert c == 200 and r["agent"] == "wr-node-h9" \
    and r["token"].startswith("bus-") and len(r["token"]) == 68, (c, r)
# token baru langsung sah, sebagai identitasnya sendiri
c, r = req("POST", bus.port, "/bus/post", token=r["token"],
           body={"topic": "t1", "agent": "wr-node-h9", "text": "hi"})
assert c == 200, (c, r)
# nama eksplisit + duplikat + nama jelek
c, r = req("POST", bus.port, "/bus/enroll", token="tok-master",
           body={"host": "h10", "agent": "custom-node"})
assert c == 200 and r["agent"] == "custom-node", (c, r)
c, _ = req("POST", bus.port, "/bus/enroll", token="tok-master",
           body={"host": "h9"})
assert c == 409, c
c, _ = req("POST", bus.port, "/bus/enroll", token="tok-master",
           body={"host": "h; rm -rf"})
assert c == 400, c
# registry tertulis ke BUS_TOKENS_FILE
data = json.load(open(bus.agents))
assert data["tokens"].get("wr-node-h9", "").startswith("bus-"), data
# file registry belum ada → dibuat (fresh install)
os.remove(bus.agents)
c, r = req("POST", bus.port, "/bus/enroll", token="tok-master",
           body={"host": "h11"})
assert c == 200, (c, r)
assert os.path.exists(bus.agents)
```

- [ ] **Step 2: Jalankan tes — pastikan gagal**

Run: `python3 tests/test_bus_api.py`
Expected: FAIL — `assert c == 404` (path tak dikenal) pada baris enroll pertama.

- [ ] **Step 3: Implementasi di `bus/server.py`**

- Impor: tambah `import re`, `import secrets` di blok impor atas.
- Modul: `_AGENTS_LOCK = threading.Lock()`; `AGENTS_PATH = os.environ.get("BUS_TOKENS_FILE", "/home/admin/bus/agents.json")` — **baca env ini sekali di modul** lalu pakai di `agent_tokens()` dan `enroll_agent()` (hapus pembacaan env inline di `agent_tokens()` agar satu sumber).
- `def enroll_agent(host, name)`: validasi `name` terhadap `^[A-Za-z0-9._-]{1,64}$` (juga `host`); di bawah `_AGENTS_LOCK`: baca file (tak ada → `{"tokens": {}}`), `ValueError("sudah ada")` bila `name in data["tokens"]`, generate `"bus-"+secrets.token_hex(32)`, tulis ke `path+".tmp"` lalu `os.replace`, `os.chmod(path, 0o600)`; return token. `os.makedirs(os.path.dirname(path), exist_ok=True)` sebelum tulis.
- `do_POST`: tambah `"/bus/enroll"` ke tuple whitelist. Handler sebelum cabang `/bus/post`: `if self.identity != "*": return self._send(403, …)`; `agent = b.get("agent") or f"wr-node-{b.get('host') or ''}"`; panggil `enroll_agent(host, agent)` dalam try — `ValueError` berisi "sudah ada" → 409, lainnya → 400; sukses → `200 {"ok": True, "agent", "token", "host"}`.

- [ ] **Step 4: Jalankan tes — pastikan hijau**

Run: `make test`
Expected: `test_bus_api.py` lolos semua (blok enroll ikut hijau); `test_policy.py` tetap hijau (tak disentuh).

- [ ] **Step 5: Commit**

```bash
git add bus/server.py tests/test_bus_api.py
git commit -m "feat(bus): endpoint /bus/enroll — registry agen via API, master-only"
```

---

### Task 2: Subperintah `armada enroll` di CLI

**Files:**
- Modify: `cli/armada.py` (docstring daftar perintah, `cmd_enroll`, dispatch `main()`)

**Interfaces:**
- Consumes: `POST /bus/enroll` (Task 1); `http()`, `die()`, `BUS_URL`, `TOKEN` yang ada.
- Produces: `armada enroll --host <h> [--agent <nama>] [--wait <dtk>]` — mencetak agen+token+baris bootstrap; `--wait` poll `GET /bus/messages?topic=health/<h>&limit=1` tiap 5 dtk sampai `count>0` atau deadline → pesan konfirmasi/peringatan.

- [ ] **Step 1: Implementasi `cmd_enroll(rest)`**

- Parse `--host` (wajib, `die` bila kosong), `--agent`, `--wait` (int, default 0).
- `POST /bus/enroll` body `{"host": host, "agent": agent}` (`agent` hanya bila diisi); non-200 → `die(f"gagal enroll: {r}")`.
- `node_bus = BUS_URL[:-4] if BUS_URL.endswith("/bus") else BUS_URL` — Review Focus #5.
- Cetak (gaya pesan CLI lain, BI):
  ```
  ✓ terdaftar: <agent>  (token tampil sekali di sini)
  Tempel di host <host> lewat channel apa pun (TAT console, web shell, ssh):

    curl -fsSL https://raw.githubusercontent.com/MaximaLabs/armada/main/ops/install.sh | bash -s -- --bus <node_bus> --token <token> --host <host>
  ```
- `--wait N`: loop `time.sleep(5)`; tiap iter `GET /bus/messages?topic=health/<host>&limit=1`; `count>0` → cetak `✓ heartbeat pertama diterima — node hidup` dan return; deadline lewat → cetak `…belum ada heartbeat dalam Ns — node belum hidup, cek manual` (bukan exit 1 — enroll sendiri sudah sukses).
- Docstring modul: tambah baris `armada enroll --host H [--agent A] [--wait N]   daftarkan host baru (master saja)` di daftar perintah. Dispatch: `elif cmd == "enroll": cmd_enroll(rest)`.

- [ ] **Step 2: Verifikasi kompilasi + manual smoke (bus lokal temp)**

Run: `python3 -m py_compile cli/armada.py` → exit 0.
Smoke: jalankan `bus/server.py` lokal di port temp dengan `BUS_DB`/`BUS_TOKENS_FILE`/`BUS_TOKEN` temporer, lalu `BUS_URL=http://127.0.0.1:<port> BUS_TOKEN=<t> python3 cli/armada.py enroll --host demo` → baris bootstrap tercetak, `POST /bus/post` pakai token baru → 200. (Boleh via skrip sekali-jalan di /tmp — jangan dicommit.)

- [ ] **Step 3: Commit**

```bash
git add cli/armada.py
git commit -m "feat(cli): subperintah enroll — cetak bootstrap install.sh siap tempel"
```

---

### Task 3: Segarkan dokumen

**Files:**
- Modify: `README.md` (Quickstart langkah 2), `node/README.md` (bagian Install)

- [ ] **Step 1: Edit**

- `README.md` Quickstart: langkah 2 jadi `armada enroll --host db1` (di laptop) → tempel baris yang dicetak ke host lewat channel tersedia; sebutkan endpoint ini master-only dan `agents.json` tidak lagi disunting manual. Satu kalimat "enrollment tanpa SSH: baris bootstrap jalan di TAT console / web shell / ssh — host tetap tak membuka port".
- `node/README.md` bagian Install: baris `install.sh` tetap (memang itu yang dijalankan di host), tambah paragraf pendek: cara memperoleh token = `armada enroll` (bukan edit `agents.json` di bus).
- Jangan sentuh `policy.example.json`/`agents.example.json` (masih akurat sebagai bentuk file).

- [ ] **Step 2: Commit**

```bash
git add README.md node/README.md
git commit -m "docs: alur enroll tanpa jumphost — agents.json tidak disunting manual"
```

---

### Task 4: Verifikasi akhir branch

- [ ] **Step 1:** `make test` hijau penuh; `make compile` implisit.
- [ ] **Step 2:** `git log main..feat/enroll` — 4 commit (spec + 3 task), satu alasan per commit.
- [ ] **Step 3:** Tampilkan diff ke owner untuk review sebelum merge/push (repo publik, konvensi PR).

---

## Checklist operasional (di luar patch — sesudah merge)

1. **polywarroom** (`ssh warroom` — wstunnel :443, jalan dari kantor):
   - `cp /home/admin/bus/server.py` versi baru (scp/rsync dari repo).
   - `sudo cp /home/admin/bus/agents.json /var/lib/warroom-bus/agents.json` → `chown admin:admin` `chmod 640`.
   - Tambah `BUS_TOKENS_FILE=/var/lib/warroom-bus/agents.json` di `/etc/warroom/bus_token.env`.
   - `sudo -n systemctl restart warroom-bus` → `curl :8810/bus/health` → 200; uji `POST /bus/enroll` master → 200.
   - Kosongkan `~/bus/agents.json` lama setelah terbukti (jangan biarkan salinan token basi).
2. **Laptop**: `armada enroll --host vps-dash --wait 120` → tempel baris di VPS via `ssh -J warroom` (atau TAT console).
3. **VPS**: tulis `~/.config/armada/policy.json` (grant `health`/`allow`/`user` utk agen owner + `exec_allow` disetel layanan dashboard: `systemctl status *`, `journalctl -u * -n 200`, `pm2 list`, `pm2 describe *`, `tailscale status`, `df -h`, `uptime`, `free -m`, `ss -tlnp`); `loginctl enable-linger ubuntu`.
4. **Verifikasi**: `armada post --host vps-dash --mode allow -- df -h` → `watch` → `done`.
5. Alias `Host vps-dash` (ProxyJump warroom) di `~/.ssh/config` laptop — jalur darurat manusia.
