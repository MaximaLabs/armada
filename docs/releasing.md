# Releasing Armada

Armada tidak pakai semver. Rilis diukur **per fase** (P0–P4, lihat
`docs/superplan-armada-agen.md`); versi daemon hidup di `node/wr_node.py`
(`VERSION`) dan versi bus di `bus/server.py`. Tag git tetap `v*` agar
tooling GitHub senang, tapi isi changelog bicara fase.

## Checklist rilis

1. **Semua kerjaan fase masuk `main` lewat PR** — `main` diproteksi
   (PR wajib + review + CI hijau). Jangan tag commit yang belum CI-hijau.
2. **CHANGELOG diperbarui** — pindahkan isi `[Unreleased]` ke heading fase
   baru, mis. `## [P4 — bus publik] 2026-11-22`. Biarkan `[Unreleased]`
   kosong di atasnya.
3. **Naikkan `VERSION`** di `node/wr_node.py` bila protokol/job schema
   berubah — wr-node lama menolak diam-diam kalau tidak kompatibel.
4. **Uji lokal lengkap**: `make test` (pytest) + `make compile`
   (`python -m compileall bus node cli`) + `make art` (figure deterministik,
   `git diff --exit-code` harus kosong).
5. **Tag + release**:

   ```bash
   git tag -a v0.4.0 -m "P4 — bus publik via nginx+TLS"
   git push origin v0.4.0
   gh release create v0.4.0 \
     --title "P4 — bus publik via nginx+TLS" \
     --notes-file docs/release-notes/v0.4.0.md
   ```

   `docs/release-notes/` berisi ringkasan + status deploy per rilis
   (boleh tempel bagian "Terverifikasi" dari deploy doc).

6. **Deploy** mengikuti `docs/deploy-p2.md`: bus di host ops jalan sebagai
   `warroom-bus.service`, wr-node di tiap host menunjuk ke URL publik.
   Rollback = file `.bak` di host + `systemctl restart`.

## Apa yang TIDAK dirilis

- `agents.json`, token bus, file `node/policy.json` nyata — host-lokal,
  jangan pernah masuk git/release asset.
- Tidak ada artefak build — armada pure-stdlib; yang "dirilis" adalah
  source + changelog.

## Komunikasi

- Rilis fase besar (P2+) layak note di `#ops` / war-room: komponen mana
  yang berubah, host mana yang perlu rolling restart wr-node.
