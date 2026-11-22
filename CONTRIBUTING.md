# Contributing

Terima kasih sudah mampir. Armada sengaja kecil — satu file per komponen,
Python stdlib murni — dan kami ingin tetap seperti itu.

## Prinsip repo

- **Nol dependensi runtime.** Kalau fitur butuh pip package, itu sinyal
  untuk pikir ulang desainnya — bukan untuk menambah `requirements.txt`.
- **Stdlib, satu file.** `bus/server.py`, `node/wr_node.py`, `cli/armada.py`
  masing-masing harus tetap bisa disalin satu-file ke host dan jalan.
- **Fakta > klaim.** Deskripsikan perubahan lewat bukti perintah
  (output tes, `curl`, `systemctl status`), bukan "seharusnya bekerja".
- **Policy adalah fitur keamanan.** Perubahan di `wr_node.py` yang
  menyentuh `allowed()`/`mode_granted()`/`deny_always` wajib disertai
  tes baru di `tests/test_policy.py` yang membuktikan deny tetap menang.

## Alur kerja

1. Branch dari `main`: `<tipe>/<ringkas-dengan-dash>`
   (`feat/`, `fix/`, `docs/`, `test/`, `chore/`, `refactor/`).
2. Commit memakai Conventional Commits Bahasa Indonesia:
   `feat(node): …` — ringkas ≤72 karakter, imperatif, tanpa atribusi AI.
3. `make test` wajib hijau (compile + unit + integrasi, semuanya stdlib).
4. PR mengisi `.github/pull_request_template.md` — terutama bagian
   *Sudah dicek*.
5. Satu perubahan = satu alasan. Pisahkan refactor dari perubahan perilaku.

## Menjalankan bus lokal untuk uji

```bash
# bus lokal dengan DB temporer
BUS_DB=/tmp/armada-bus.db BUS_PORT=18910 BUS_TOKEN=dev python3 bus/server.py &

# node lokal yang mengarah ke sana
BUS_URL=http://127.0.0.1:18910 BUS_TOKEN=dev WR_HOST=devbox \
  python3 node/wr_node.py
```

`tests/test_bus_api.py` menunjukkan cara spawn server di subprocess untuk
tes otomatis — pakai pola yang sama untuk tes baru.

## Yang kemungkinan ditolak

- Dependensi eksternal untuk runtime (dependensi CI/dev masih bisa dibahas).
- Endpoint baru tanpa pertimbangan auth (`/bus/ui` sengaja terbuka —
  baca SECURITY.md sebelum mengusulkan pola yang sama).
- "Fitur pintar" yang memindahkan keputusan policy dari host ke bus —
  host selalu punya hak veto.

## Proses rilis

Armada tidak memakai semver — penomoran fase P0–Pn di
`docs/superplan-armada-agen.md`; versi daemon di `node/wr_node.py` (`VERSION`).

1. Pastikan CI hijau di `main` + `CHANGELOG.md` ter-update (bagian Unreleased).
2. Tag rilis: `git tag -a pN -m "P<N>: <judul>"` lalu `git push origin pN`.
3. Deploy produk: `ops/install.sh` atau salin `bus/server.py` +
   `node/wr_node.py` ke host; rollback = file `.bak` sebelum replace.
