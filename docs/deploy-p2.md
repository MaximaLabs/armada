# Deploy P2 ke produksi (owner, ~2 menit)

Kode baru `bus/server.py` menambah job queue + `/bus/ui`. Bus yang berjalan
masih versi lama — wr-node sudah toleran (404 = tanpa job).

```bash
# di polywarroom (perlu sudo)
sudo cp /home/admin/bus/server.py /home/admin/bus/server.py.bak.$(date +%Y%m%d)
sudo cp <repo>/bus/server.py /home/admin/bus/server.py
sudo systemctl restart warroom-bus
curl -s http://127.0.0.1:8810/bus/health            # {"ok":true,...}
curl -s http://127.0.0.1:8810/bus/ui | head -5      # halaman status
```

Rollback: `sudo mv /home/admin/bus/server.py.bak.* /home/admin/bus/server.py && sudo systemctl restart warroom-bus`

Setelah restart: posting job dari mana pun → wr-node polywarroom
mengklaimnya dalam ~7 detik (mode `allow`, policy aktif).
