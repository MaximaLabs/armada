"""Tes integrasi API bus: spawn server sungguhan di port acak + DB temporer.

Kontrak yang dijaga: auth per-agen, append-only messages, siklus hidup job
(post → claim → result → audit), dedupe, cancel, kepemilikan hasil.

Jalankan:  python tests/test_bus_api.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

ROOT = os.path.join(os.path.dirname(__file__), "..")
spec = importlib.util.spec_from_file_location(
    "bus_server", os.path.join(ROOT, "bus", "server.py"))


def req(method, port, path, token=None, body=None):
    r = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"X-Bus-Token": token} if token else {})})
    def _parse(raw):
        try:
            return json.loads(raw or b"{}")
        except Exception:
            return raw.decode("utf-8", "replace")
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, _parse(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, _parse(e.read())
        except Exception:
            return e.code, {}


class Bus:
    """Server nyata di subprocess — sama seperti produksi."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.port = 18810 + (os.getpid() % 400)
        self.agents = os.path.join(self.tmp.name, "agents.json")
        with open(self.agents, "w") as f:
            json.dump({"tokens": {"node-1": "tok-node",
                                  "agent-1": "tok-agent"}}, f)
        env = dict(os.environ,
                   BUS_DB=os.path.join(self.tmp.name, "bus.db"),
                   BUS_PORT=str(self.port),
                   BUS_TOKEN="tok-master",
                   BUS_TOKENS_FILE=self.agents)
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "bus", "server.py")],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                c, _ = req("GET", self.port, "/bus/health")
                if c == 200:
                    return
            except Exception:
                pass
            time.sleep(0.1)
        raise RuntimeError("bus tidak naik dalam 5 detik")

    def stop(self):
        self.proc.terminate()
        self.proc.wait(timeout=5)
        self.tmp.cleanup()


def main() -> int:
    bus = Bus()
    try:
        # --- auth -----------------------------------------------------
        c, _ = req("GET", bus.port, "/bus/messages")                     # tanpa token
        assert c == 401, c
        c, _ = req("GET", bus.port, "/bus/messages", token="salah")
        assert c == 401, c
        c, _ = req("GET", bus.port, "/bus/messages", token="tok-master") # master
        assert c == 200, c

        # --- messages append-only ------------------------------------
        c, r = req("POST", bus.port, "/bus/post", token="tok-agent",
                   body={"topic": "t1", "agent": "agent-1", "text": "halo"})
        assert c == 200 and r["seq"] >= 1, (c, r)
        # token node-1 tidak boleh post sebagai agent-1
        c, _ = req("POST", bus.port, "/bus/post", token="tok-node",
                   body={"topic": "t1", "agent": "agent-1", "text": "palsu"})
        assert c == 403, c
        c, r = req("GET", bus.port, "/bus/messages?topic=t1", token="tok-master")
        assert r["count"] == 1 and r["messages"][0]["text"] == "halo", r

        # --- job lifecycle -------------------------------------------
        c, r = req("POST", bus.port, "/bus/job/post", token="tok-agent",
                   body={"host": "h1", "mode": "allow",
                         "argv": ["df", "-h"], "dedupe": "d1"})
        assert c == 200 and r["state"] == "queued", (c, r)
        jid = r["id"]
        # dedupe: post ulang → job yang sama
        c, r2 = req("POST", bus.port, "/bus/job/post", token="tok-agent",
                    body={"host": "h1", "mode": "allow",
                          "argv": ["df", "-h"], "dedupe": "d1"})
        assert r2["id"] == jid and r2.get("deduped"), r2
        # host lain tidak mengambil job h1
        c, r = req("GET", bus.port, "/bus/job/claim?host=h2", token="tok-node")
        assert c == 200 and not r.get("id"), r
        # host benar mengklaim
        c, r = req("GET", bus.port, "/bus/job/claim?host=h1", token="tok-node")
        assert r["id"] == jid and r["argv"] == ["df", "-h"], r
        # kedua kalinya kosong (sudah claimed)
        c, r = req("GET", bus.port, "/bus/job/claim?host=h1", token="tok-node")
        assert not r.get("id"), r
        # agen lain tidak boleh menyerahkan hasil job node-1
        c, _ = req("POST", bus.port, "/bus/job/result", token="tok-agent",
                   body={"id": jid, "exit_code": 0, "stdout": "x"})
        assert c == 409, c
        # pemilik boleh
        c, r = req("POST", bus.port, "/bus/job/result", token="tok-node",
                   body={"id": jid, "exit_code": 0, "stdout": "Filesystem…"})
        assert c == 200, (c, r)
        c, r = req("GET", bus.port, f"/bus/job/status?id={jid}", token="tok-node")
        assert r["state"] == "done" and r["exit_code"] == 0, r
        # audit: hasil muncul di topik job/<id>
        c, r = req("GET", bus.port, f"/bus/messages?topic=job/{jid}",
                   token="tok-master")
        assert r["count"] == 1 and r["messages"][0]["kind"] == "result", r

        # --- cancel ---------------------------------------------------
        c, r = req("POST", bus.port, "/bus/job/post", token="tok-agent",
                   body={"host": "h1", "mode": "allow", "argv": ["sleep", "60"]})
        j2 = r["id"]
        c, _ = req("POST", bus.port, "/bus/job/cancel", token="tok-agent",
                   body={"id": j2})
        assert c == 200, c
        c, r = req("GET", bus.port, "/bus/job/claim?host=h1", token="tok-node")
        assert not r.get("id"), r  # cancelled tidak ter-claim
        c, r = req("GET", bus.port, f"/bus/job/status?id={j2}", token="tok-node")
        assert r["state"] == "cancelled", r

        # --- unauthenticated surface ---------------------------------
        c, _ = req("GET", bus.port, "/bus/ui")
        assert c == 200, c

        # --- enroll: hanya master --------------------------------------
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

        print("OK — 16 grup tes integrasi bus lolos")
        return 0
    finally:
        bus.stop()


if __name__ == "__main__":
    sys.exit(main())
