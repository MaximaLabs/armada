# AGENTS.md — bekerja di repo armada

Repo ini adalah control plane eksekusi jarak jauh. Agen yang menyuntingnya
wajib memegang dua aturan di bawah ini sebelum aturan gaya mana pun.

## Batas keras

1. **Policy engine adalah batas keamanan.** Jangan mengubah `allowed()`,
   `mode_granted()`, `_denied()`, atau urutan deny-first tanpa tes baru yang
   membuktikan `deny_always` masih menang. `tests/test_policy.py` adalah
   kontraknya — jalankan `make test` sebelum commit.
2. **Tidak ada secret di repo.** `agents.json`, `*.env`, token bus, dan
   path produksi yang mengandung kredensial tidak pernah di-commit.
   File contoh memakai placeholder `<token-agen>`. `.gitignore` dan job
   `secrets` di CI menjaga ini — jangan dilemahkan.
3. **File tunggal + stdlib.** Jangan memecah `server.py`/`wr_node.py`/
   `armada.py` menjadi paket, dan jangan menambah impor non-stdlib.
   Portabilitas satu-file adalah fitur produk.

## Konvensi

- Komentar/docstring menjawab *kenapa*, bukan *apa*. Bahasa Indonesia di
  docstring internal konsisten dengan kode yang ada; dokumen front-door
  (README, SECURITY, CONTRIBUTING) boleh Inggris.
- Commit: Conventional Commits Bahasa Indonesia (`feat(node): …`),
  tanpa atribusi AI, satu alasan per commit.
- Bug fix disertai tes yang gagal sebelum fix (red-test-first bila memungkinkan).
- `art/` diregenerasi dengan `make art` — jangan menyunting SVG hasil
  generate secara manual.

## Verifikasi

```bash
make test      # py_compile + tests/test_policy.py + tests/test_bus_api.py
make art       # regenerasi figur README (butuh node 20+)
```

CI (`ci` workflow) menjalankan hal yang sama di Python 3.10–3.13 dan
memverifikasi art build deterministik.
