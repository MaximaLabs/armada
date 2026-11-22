#!/usr/bin/env python3
"""armada — klien CLI seragam untuk semua agen.

Stdlib Python, satu file. Konfigurasi ~/.config/armada/agent.env:
    BUS_URL=https://<host>/bus   (atau http://127.0.0.1:8810 lokal)
    BUS_TOKEN=<token agen>
    ARMADA_AGENT=<nama agen>     (opsional; dari token juga terbaca)

Perintah:
    armada health                          snapshot armada (host + antrian)
    armada post --host H --mode M -- arg…  enqueue job  (contoh: -- df -h)
    armada post --host H --mode M --argv '["df","-h"]'
    armada watch <id>                      pantau job sampai selesai
    armada tail <id>                       lihat hasil job
    armada jobs [--state queued]
    armada cancel <id>
    armada note [-t topik] "teks"          posting catatan diskusi
    armada read [-t topik] [-n 20]         baca pesan topik
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error

def _env() -> None:
    p = os.path.expanduser("~/.config/armada/agent.env")
    if os.path.exists(p):
        for line in open(p):
            k, _, v = line.partition("=")
            if k.strip() and not k.startswith("#"):
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_env()
BUS_URL = os.environ.get("BUS_URL", "http://127.0.0.1:8810").rstrip("/")
TOKEN = os.environ.get("BUS_TOKEN", "")


def http(method: str, path: str, body=None):
    req = urllib.request.Request(
        BUS_URL + path, method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"X-Bus-Token": TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def cmd_health() -> None:
    c, b = http("GET", "/bus/messages?topic=health&limit=1")
    c2, topics = http("GET", "/bus/topics")
    print("bus:", "ok" if c == 200 or c2 == 200 else "unreachable")
    for t in (topics.get("topics") or []):
        if t["topic"].startswith("health/"):
            print(f"  {t['topic']:28} {t['n']:>5} pesan")


def cmd_post(argv: list) -> None:
    host, mode, after = "laptop", "allow", None
    av = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--host": host = argv[i + 1]; i += 2
        elif a == "--mode": mode = argv[i + 1]; i += 2
        elif a == "--after": after = argv[i + 1]; i += 2
        elif a == "--argv": av = json.loads(argv[i + 1]); i += 2
        elif a == "--": av = argv[i + 1:]; break
        else: i += 1
    if not av:
        die("butuh argv: -- <cmd…> atau --argv '[..]'")
    body = {"host": host, "mode": mode, "argv": av}
    if after:
        body["after_id"] = after
    c, r = http("POST", "/bus/job/post", body)
    print(r if c != 200 else f"{r['id']}  state={r.get('state')}")


def _job(jid: str) -> dict | None:
    c, r = http("GET", "/bus/job/list")
    for j in r.get("jobs") or []:
        if j["id"].startswith(jid):
            return j
    return None


def cmd_watch(jid: str) -> None:
    while True:
        j = _job(jid)
        if not j:
            die("job tidak ditemukan")
        st = j["state"]
        print(f"{jid[:20]}  {st}  claim={j.get('claim_agent') or '-'}")
        if st in ("done", "failed", "expired", "cancelled"):
            return
        time.sleep(3)


def cmd_tail(jid: str) -> None:
    c, r = http("GET", f"/bus/messages?topic=job/{jid}&limit=50")
    for m in r.get("messages") or []:
        print(f"[{m['agent']}] {m['text'][:500]}")
    j = _job(jid)
    if j:
        print(f"-- state={j['state']} exit={j.get('exit_code')}")


def cmd_jobs(state: str | None) -> None:
    q = f"?state={state}" if state else ""
    c, r = http("GET", "/bus/job/list" + q)
    for j in (r.get("jobs") or [])[:30]:
        print(f"{j['id'][:20]:22} {j['host']:14} {j['agent']:18} "
              f"{j['mode']:8} {j['state']:9} exit={j.get('exit_code')}")


def cmd_cancel(jid: str) -> None:
    c, r = http("POST", "/bus/job/cancel", {"id": jid})
    print(r)


def cmd_note(argv: list) -> None:
    topic = "warroom"
    if argv[:2] == ["-t"]:
        topic, argv = argv[1], argv[2:]
    text = " ".join(argv)
    agent = os.environ.get("ARMADA_AGENT") or os.uname().nodename
    c, r = http("POST", "/bus/post", {
        "topic": topic, "agent": agent, "kind": "note", "text": text})
    print(r if c == 200 else f"gagal: {r}")


def cmd_read(argv: list) -> None:
    topic, n = "warroom", "20"
    if "-t" in argv:
        topic = argv[argv.index("-t") + 1]
    if "-n" in argv:
        n = argv[argv.index("-n") + 1]
    c, r = http("GET", f"/bus/messages?topic={topic}&limit={n}")
    for m in r.get("messages") or []:
        ts = time.strftime("%H:%M", time.localtime(m["ts"]))
        print(f"{ts} [{m['agent']}] {m['text'][:200]}")


def main() -> int:
    if not TOKEN:
        die("BUS_TOKEN kosong — isi ~/.config/armada/agent.env")
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = a[0], a[1:]
    if cmd == "health": cmd_health()
    elif cmd == "post": cmd_post(rest)
    elif cmd == "watch": cmd_watch(rest[0])
    elif cmd == "tail": cmd_tail(rest[0])
    elif cmd == "jobs": cmd_jobs(rest[1] if rest[:1] == ["--state"] else None)
    elif cmd == "cancel": cmd_cancel(rest[0])
    elif cmd == "note": cmd_note(rest)
    elif cmd == "read": cmd_read(rest)
    else:
        die(f"perintah tak dikenal: {cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
