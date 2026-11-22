#!/usr/bin/env python3
"""Backup konsisten bus.db (SQLite WAL) -> gzip, retensi 14 hari.
Dipakai cron admin di webdock. Aman dijalankan saat bus hidup (pakai backup API).
"""
import gzip
import os
import shutil
import sqlite3
import sys
import time

SRC = "/var/lib/warroom-bus/bus.db"
DEST_DIR = "/home/admin/backups/bus"
KEEP_DAYS = 14

os.makedirs(DEST_DIR, exist_ok=True)
stamp = time.strftime("%Y%m%d-%H%M%S")
tmpdb = os.path.join(DEST_DIR, f".bus-{stamp}.db")
out = os.path.join(DEST_DIR, f"bus-{stamp}.db.gz")

try:
    src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
    dst = sqlite3.connect(tmpdb)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()

    with open(tmpdb, "rb") as f_in, gzip.open(out, "wb", compresslevel=9) as f_out:
        shutil.copyfileobj(f_in, f_out)

    os.unlink(tmpdb)

    # verifikasi hasil backup bisa dibaca
    with gzip.open(out, "rb") as f:
        head = f.read(16)
    if not head.startswith(b"SQLite format 3"):
        raise RuntimeError("hasil backup bukan SQLite valid")

    size = os.path.getsize(out)
    print(f"OK {out} ({size} byte)")
except Exception as e:
    print(f"GAGAL backup bus.db: {type(e).__name__}: {e}", file=sys.stderr)
    if os.path.exists(tmpdb):
        os.unlink(tmpdb)
    sys.exit(1)

# rotasi
cutoff = time.time() - KEEP_DAYS * 86400
removed = 0
for name in os.listdir(DEST_DIR):
    if not (name.startswith("bus-") and name.endswith(".db.gz")):
        continue
    p = os.path.join(DEST_DIR, name)
    if os.path.getmtime(p) < cutoff:
        os.unlink(p)
        removed += 1
if removed:
    print(f"rotasi: {removed} backup lama dihapus")
