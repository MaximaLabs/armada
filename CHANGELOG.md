# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/id/1.1.0/).
Proyek ini mengikuti penomoran fase (P0–P4) di `docs/superplan-armada-agen.md`,
bukan semver — versi daemon ada di `node/wr_node.py` (`VERSION`).

## [Unreleased]

### Added
- Tes integrasi `tests/test_bus_api.py`: spawn bus nyata di subprocess,
  15 grup kontrak (auth, append-only, siklus job, dedupe, cancel,
  kepemilikan hasil).
- CI: `ci` workflow — kompilasi + tes di Python 3.10–3.13, art build
  deterministik, jaga file secret.
- Dokumen komunitas: LICENSE (MIT), CONTRIBUTING, SECURITY (threat model +
  cara lapor), AGENTS, CHANGELOG, PR/issue templates.
- `Makefile` (`test`, `compile`, `art`, `clean`) + `ops/install.sh`.
- README baru: gambaran produk, quickstart, capability ladder, model keamanan.

### Fixed
- `armada health` tidak lagi melaporkan "ok" saat bus menjawab 401 —
  status code kini dibandingkan eksplisit.

### Removed
- `bus/_patch_tokens.py` — skrip migrasi sekali pakai dengan path produksi
  hardcode; fungsinya sudah jadi bagian `bus/server.py` sejak P0.
- `__pycache__/` yang ikut ter-commit; kini di-`.gitignore`.

## Sebelumnya (fase implementasi)

- **P0** — `bus/` diimpor dari produksi apa adanya (`ebdda2d`).
- **P1** — `wr-node` v0.1: heartbeat + snapshot + exec allowlist (`bd903ff`).
- **P2** — job queue + schedule + reaper + dedupe + cancel + `after_id` (`0ec9539`);
  `/bus/ui` (`4bfcdf0`); `armada` CLI (`de1eaae`).
- **P3** — capability ladder penuh (`user`/`root`/`sandbox`+docker),
  `env_profile`, streaming output, cancel saat eksekusi, kill switch
  (`c5e64e5`, `3766738`); node live di 3 host produksi (`453b7c5`).
- Figur "The Dispatch Bench" untuk README (`db87dac`).
