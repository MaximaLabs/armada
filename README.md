# Armada — by MaximaLabs

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="art/armada-flow.svg">
  <source media="(prefers-color-scheme: light)" srcset="art/armada-flow-light.svg">
  <img alt="Armada: agen menitip job ke bus; tabung mengantar ke wr-node di tiap host" src="art/armada-flow-light.svg" width="760">
</picture>

> Proyek lab [MaximaLabs](https://maximalabs.tech)

Fabric agen lintas server: mailbox + daemon tipis per host (`wr-node`),
supaya agen (Devin, Hermes, agy CLI, DeepSeek, bot memoh) bisa melihat
kesehatan server dan mengeksekusi tugas terkontrol dari jaringan mana pun —
tanpa SSH fan-in, tanpa port inbound baru.

Rencana induk: [`docs/superplan-armada-agen.md`](docs/superplan-armada-agen.md)

## Batas

- Infrastruktur lintas-server (webdock, cyber1, instabox, laptop) —
  **bukan** bagian repo warroom; warroom hanya salah satu host + agen.
- Domain terlarang tetap tertutup: VM2 Azure, `/opt/polymarket`, Tencent,
  gate poly-pilot.
- Host tidak pernah membuka port baru — semua lewat koneksi keluar :443
  ke mailbox.
