#!/usr/bin/env python3
"""bus — papan diskusi asinkron lintas agent & lintas komputer.

Kenapa ada: agent di mesin berbeda (Webdock, cyber1, instabox, laptop) perlu
saling meninggalkan catatan tanpa harus online bersamaan dan tanpa SSH fan-in.
Server ini satu-satunya tempat menulis; semua klien cukup HTTPS.

Desain:
- SQLite append-only (atomic, berurutan, aman untuk penulis bersamaan).
- Tiap agent punya cursor sendiri -> "apa yang belum saya baca" itu murah.
- Tidak ada penghapusan lewat API. Jejak diskusi tidak boleh hilang diam-diam.

Auth: header `X-Bus-Token` (dibaca dari file, mode 600).
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DB = os.environ.get("BUS_DB", "/var/lib/warroom-bus/bus.db")
PORT = int(os.environ.get("BUS_PORT", "8810"))
MAX_TEXT = 20000


def token() -> str:
    # Dibaca dari environment systemd (EnvironmentFile, mode 640 root:admin),
    # bukan dari disk: service jalan sebagai `admin` dan tidak perlu hak baca
    # ke /etc/warroom.
    return os.environ.get("BUS_TOKEN", "").strip()


def agent_tokens() -> dict:
    """token -> nama agent. File JSON, dibaca ulang tiap request (rotasi tanpa restart)."""
    path = os.environ.get("BUS_TOKENS_FILE", "/home/admin/bus/agents.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        toks = data.get("tokens") or {}
        return {str(v).strip(): str(k).strip() for k, v in toks.items() if str(v).strip()}
    except Exception:
        return {}


def db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB, timeout=15)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS msg (
            seq      INTEGER PRIMARY KEY AUTOINCREMENT,
            ts       REAL NOT NULL,
            topic    TEXT NOT NULL,
            agent    TEXT NOT NULL,
            host     TEXT DEFAULT '',
            kind     TEXT DEFAULT 'note',
            text     TEXT NOT NULL,
            refs     TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_topic_seq ON msg(topic, seq);
        CREATE TABLE IF NOT EXISTS cursor (
            agent TEXT NOT NULL,
            topic TEXT NOT NULL,
            seq   INTEGER NOT NULL,
            PRIMARY KEY (agent, topic)
        );
        CREATE TABLE IF NOT EXISTS job (
            id           TEXT PRIMARY KEY,
            host         TEXT NOT NULL,
            agent        TEXT NOT NULL,
            kind         TEXT NOT NULL DEFAULT 'exec',
            mode         TEXT NOT NULL DEFAULT 'allow',
            argv         TEXT NOT NULL,
            dedupe       TEXT,
            priority     INTEGER NOT NULL DEFAULT 50,
            after_id     TEXT,
            ttl_sec      INTEGER NOT NULL DEFAULT 86400,
            timeout_sec  INTEGER NOT NULL DEFAULT 300,
            state        TEXT NOT NULL DEFAULT 'queued',
            lease_until  REAL,
            claim_agent  TEXT,
            claim_host   TEXT,
            cancel_req   INTEGER NOT NULL DEFAULT 0,
            exit_code    INTEGER,
            stdout       TEXT,
            stderr       TEXT,
            ts_post      REAL NOT NULL,
            ts_claim     REAL,
            ts_done      REAL
        );
        CREATE INDEX IF NOT EXISTS idx_job_claim ON job(host, state, priority, ts_post);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_job_dedupe ON job(dedupe) WHERE dedupe IS NOT NULL;
        CREATE TABLE IF NOT EXISTS schedule (
            id         TEXT PRIMARY KEY,
            host       TEXT NOT NULL,
            agent      TEXT NOT NULL,
            mode       TEXT NOT NULL DEFAULT 'allow',
            argv       TEXT NOT NULL,
            every_sec  INTEGER NOT NULL,
            next_due   REAL NOT NULL,
            enabled    INTEGER NOT NULL DEFAULT 1
        );
    """)
    # migrasi ringan untuk DB lama
    cols = {r[1] for r in con.execute("PRAGMA table_info(job)")}
    if "env_profile" not in cols:
        con.execute("ALTER TABLE job ADD COLUMN env_profile TEXT")
    return con


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # senyap; journal sudah cukup
        pass

    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth(self) -> bool:
        supplied = (self.headers.get("X-Bus-Token", "") or "").strip()
        mapping = agent_tokens()
        if supplied and supplied in mapping:
            self.identity = mapping[supplied]
            return True
        want = token()
        if not want:
            self._send(500, {"error": "server token belum diset"})
            return False
        if supplied != want:
            self._send(401, {"error": "token salah"})
            return False
        self.identity = "*"  # token lama = master, boleh bertindak atas nama agent mana pun
        return True

    def _agent_allowed(self, requested: str) -> bool:
        ident = getattr(self, "identity", "*")
        return ident == "*" or not requested or requested == ident

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self) -> None:
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}

        if u.path == "/bus/health":
            return self._send(200, {"ok": True, "ts": time.time()})
        if u.path == "/bus/ui":
            return self._ui()
        if not self._auth():
            return

        con = db()
        if u.path == "/bus/messages":
            topic = q.get("topic", "warroom")
            limit = min(int(q.get("limit", 50)), 500)
            since = q.get("since")
            agent = q.get("agent")
            cur = con.execute(
                "SELECT seq,ts,topic,agent,host,kind,text,refs FROM msg "
                "WHERE topic=? AND seq>? ORDER BY seq LIMIT ?",
                (topic, int(since or 0), limit),
            )
            rows = [dict(zip(("seq", "ts", "topic", "agent", "host", "kind", "text", "refs"), r, strict=True))
                    for r in cur.fetchall()]
            out = {"topic": topic, "count": len(rows), "messages": rows}
            if agent:
                # tandai sudah dibaca sampai pesan terakhir
                if rows:
                    last = rows[-1]["seq"]
                    con.execute(
                        "INSERT INTO cursor(agent,topic,seq) VALUES(?,?,?) "
                        "ON CONFLICT(agent,topic) DO UPDATE SET seq=excluded.seq",
                        (agent, topic, last),
                    )
                    con.commit()
                out["read_until"] = rows[-1]["seq"] if rows else int(since or 0)
            return self._send(200, out)

        if u.path == "/bus/unread":
            agent = q.get("agent", "")
            con2 = db()
            rows = con2.execute("""
                SELECT m.topic, COUNT(*) FROM msg m
                LEFT JOIN cursor c ON c.agent=? AND c.topic=m.topic
                WHERE m.seq > COALESCE(c.seq,0) AND m.agent != ?
                GROUP BY m.topic
            """, (agent, agent)).fetchall()
            return self._send(200, {"agent": agent,
                                    "unread": [{"topic": t, "n": n} for t, n in rows]})

        if u.path == "/bus/topics":
            rows = con.execute(
                "SELECT topic, COUNT(*), MAX(ts) FROM msg GROUP BY topic ORDER BY MAX(ts) DESC"
            ).fetchall()
            return self._send(200, {"topics": [{"topic": t, "n": n, "last_ts": ts}
                                               for t, n, ts in rows]})

        if u.path == "/bus/job/claim":
            host = q.get("host", "")
            now = time.time()
            cur = con.execute(
                "SELECT id, argv, mode, timeout_sec, agent, env_profile FROM job "
                "WHERE state='queued' AND (host=? OR host='*') "
                "AND (after_id IS NULL OR after_id IN "
                "  (SELECT id FROM job WHERE state='done')) "
                "ORDER BY priority, ts_post LIMIT 1", (host,))
            row = cur.fetchone()
            if not row:
                return self._send(200, {})
            jid = row[0]
            n = con.execute(
                "UPDATE job SET state='claimed', lease_until=?, "
                "claim_agent=?, claim_host=?, ts_claim=? "
                "WHERE id=? AND state='queued'",
                (now + 300, self.identity, host, now, jid)).rowcount
            con.commit()
            if not n:
                return self._send(200, {})
            return self._send(200, {"id": jid, "argv": json.loads(row[1]),
                                    "mode": row[2], "timeout_sec": row[3],
                                    "agent": row[4], "env_profile": row[5]})

        if u.path == "/bus/job/status":
            row = con.execute(
                "SELECT state, cancel_req, exit_code FROM job WHERE id=?",
                (q.get("id", ""),)).fetchone()
            if not row:
                return self._send(404, {"error": "tidak ada"})
            return self._send(200, {"state": row[0], "cancel_req": bool(row[1]),
                                    "exit_code": row[2]})

        if u.path == "/bus/job/list":
            st = q.get("state")
            w = "WHERE state=?" if st else ""
            rows = con.execute(
                "SELECT id, host, agent, mode, state, claim_agent, exit_code, "
                "ts_post, ts_done FROM job " + w +
                " ORDER BY ts_post DESC LIMIT 100", (st,) if st else ()).fetchall()
            keys = ("id","host","agent","mode","state","claim_agent",
                    "exit_code","ts_post","ts_done")
            return self._send(200, {"jobs": [dict(zip(keys, r)) for r in rows]})

        if u.path == "/bus/agents":
            rows = con.execute(
                "SELECT agent, host, COUNT(*), MAX(ts) FROM msg GROUP BY agent, host"
            ).fetchall()
            return self._send(200, {"agents": [{"agent": a, "host": h, "n": n, "last_ts": ts}
                                               for a, h, n, ts in rows]})
        return self._send(404, {"error": "tidak ada"})

    def _ui(self) -> None:
        now = time.time()
        con = db()
        hosts = {}
        for topic, ts in con.execute(
                "SELECT topic, MAX(ts) FROM msg WHERE topic LIKE 'health/%' "
                "GROUP BY topic").fetchall():
            hosts[topic.split("/", 1)[1]] = now - ts
        jobs = con.execute(
            "SELECT id, host, agent, mode, state, exit_code, ts_post "
            "FROM job ORDER BY ts_post DESC LIMIT 25").fetchall()
        tr = "".join(
            f"<tr class='{r[4]}'><td>{r[0][:20]}</td><td>{r[1]}</td>"
            f"<td>{r[2]}</td><td>{r[3]}</td><td>{r[4]}</td>"
            f"<td>{r[5] if r[5] is not None else ''}</td>"
            f"<td>{int(now - r[6])}d lalu</td></tr>" for r in jobs)
        th = "".join(
            f"<tr class='{('stale' if a > 300 else 'ok')}'>"
            f"<td>{h}</td><td>{int(a)} dtk lalu</td></tr>"
            for h, a in sorted(hosts.items()))
        html = f"""<!doctype html><html><head><meta charset=utf-8>
<title>Armada — status</title><meta http-equiv=refresh content=30>
<style>body{{font:14px/1.5 monospace;background:#0d1117;color:#c9d1d9;padding:2em}}
table{{border-collapse:collapse;margin:1em 0}}td,th{{border:1px solid #30363d;padding:4px 10px}}
.ok td{{color:#3fb950}}.stale td{{color:#f85149}}.done td{{color:#8b949e}}
.queued td{{color:#d29922}}.claimed td{{color:#58a6ff}}h1{{font-size:1.3em}}</style>
</head><body><h1>Armada — status armada</h1>
<h2>Host (heartbeat)</h2><table><tr><th>host</th><th>terakhir</th></tr>{th or '<tr><td colspan=2>belum ada</td></tr>'}</table>
<h2>Job terakhir</h2><table><tr><th>id</th><th>host</th><th>agen</th><th>mode</th><th>state</th><th>exit</th><th>diposting</th></tr>{tr or '<tr><td colspan=7>belum ada</td></tr>'}</table>
<p style=color:#8b949e>refresh 30d · armada by MaximaLabs</p></body></html>"""
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in ("/bus/post", "/bus/job/post",
                        "/bus/job/result", "/bus/job/cancel"):
            return self._send(404, {"error": "tidak ada"})
        if not self._auth():
            return
        b = self._body()

        if path == "/bus/job/post":
            argv = b.get("argv")
            if not isinstance(argv, list) or not argv or not all(
                    isinstance(a, str) for a in argv):
                return self._send(400, {"error": "argv wajib array string"})
            jid = b.get("id") or f"{int(time.time())}-{os.urandom(4).hex()}"
            dd = b.get("dedupe")
            if dd:
                old = db().execute(
                    "SELECT id,state FROM job WHERE dedupe=?", (dd,)).fetchone()
                if old:
                    return self._send(200, {"id": old[0], "state": old[1],
                                            "deduped": True})
            con = db()
            con.execute(
                "INSERT INTO job(id,host,agent,kind,mode,argv,dedupe,priority,"
                "after_id,ttl_sec,timeout_sec,env_profile,state,ts_post) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'queued',?)",
                (jid, (b.get("host") or "")[:64], self.identity[:64],
                 (b.get("kind") or "exec")[:24], (b.get("mode") or "allow")[:24],
                 json.dumps(argv), dd, int(b.get("priority") or 50),
                 b.get("after_id"), int(b.get("ttl_sec") or 86400),
                 int(b.get("timeout_sec") or 300),
                 (b.get("env_profile") or "")[:64] or None, time.time()))
            con.commit()
            return self._send(200, {"id": jid, "state": "queued"})

        if path == "/bus/job/result":
            jid = b.get("id") or ""
            con = db()
            row = con.execute(
                "SELECT state, claim_agent FROM job WHERE id=?", (jid,)).fetchone()
            if not row or row[0] != "claimed" or (
                    self.identity != "*" and row[1] != self.identity):
                return self._send(409, {"error": "bukan job-mu / sudah selesai"})
            con.execute(
                "UPDATE job SET state='done', exit_code=?, stdout=?, stderr=?, "
                "ts_done=? WHERE id=?",
                (b.get("exit_code"), (b.get("stdout") or "")[-65536:],
                 (b.get("stderr") or "")[-65536:], time.time(), jid))
            con.execute(
                "INSERT INTO msg(ts,topic,agent,host,kind,text,refs) "
                "VALUES(?,?,?,?,?,?,?)",
                (time.time(), f"job/{jid}", self.identity[:64], "",
                 "result", json.dumps({"exit_code": b.get("exit_code"),
                                       "stdout": (b.get("stdout") or "")[-4000:],
                                       "stderr": (b.get("stderr") or "")[:4000]}),
                 "[]"))
            con.commit()
            return self._send(200, {"ok": True})

        if path == "/bus/job/cancel":
            jid = b.get("id") or ""
            con = db()
            row = con.execute("SELECT state FROM job WHERE id=?", (jid,)).fetchone()
            if not row:
                return self._send(404, {"error": "tidak ada"})
            if row[0] == "queued":
                con.execute("UPDATE job SET state='cancelled' WHERE id=?", (jid,))
            elif row[0] == "claimed":
                con.execute("UPDATE job SET cancel_req=1 WHERE id=?", (jid,))
            con.commit()
            return self._send(200, {"ok": True})

        text = (b.get("text") or "").strip()
        if not text:
            return self._send(400, {"error": "text wajib"})
        if len(text) > MAX_TEXT:
            return self._send(400, {"error": f"text > {MAX_TEXT} karakter"})
        agent = (b.get("agent") or "anonymous").strip()[:64]
        if not self._agent_allowed(agent):
            return self._send(403, {"error": f"token milik '{getattr(self, 'identity', '?')}', "
                                             f"tidak boleh post sebagai '{agent}'"})
        topic = (b.get("topic") or "warroom").strip()[:64]
        con = db()
        cur = con.execute(
            "INSERT INTO msg(ts,topic,agent,host,kind,text,refs) VALUES(?,?,?,?,?,?,?)",
            (time.time(), topic, agent, (b.get("host") or "")[:64],
             (b.get("kind") or "note")[:24], text, json.dumps(b.get("refs") or [])),
        )
        con.commit()
        return self._send(200, {"ok": True, "seq": cur.lastrowid, "topic": topic})


if __name__ == "__main__":
    def _reaper() -> None:
        while True:
            time.sleep(60)
            try:
                now = time.time()
                con = db()
                con.execute(
                    "UPDATE job SET state='queued', lease_until=NULL, "
                    "claim_agent=NULL, claim_host=NULL, ts_claim=NULL "
                    "WHERE state='claimed' AND lease_until<?", (now,))
                con.execute(
                    "UPDATE job SET state='expired' WHERE state='queued' "
                    "AND ts_post + ttl_sec < ?", (now,))
                con.execute(
                    "UPDATE job SET state='cancelled' WHERE after_id IN "
                    "(SELECT id FROM job WHERE state IN ('failed','cancelled'))"
                    " AND state='queued'")
                due = con.execute(
                    "SELECT id,host,agent,mode,argv,every_sec FROM schedule "
                    "WHERE enabled=1 AND next_due<?", (now,)).fetchall()
                for sid, shost, sagent, smode, sargv, sev in due:
                    con.execute(
                        "INSERT INTO job(id,host,agent,kind,mode,argv,state,ts_post) "
                        "VALUES(?,?,?,'sched',?,?,'queued',?)",
                        (f"{sid}-{int(now)}", shost, sagent, smode, sargv, now))
                    con.execute("UPDATE schedule SET next_due=? WHERE id=?",
                                (now + sev, sid))
                con.commit()
            except Exception:
                pass

    threading.Thread(target=_reaper, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()