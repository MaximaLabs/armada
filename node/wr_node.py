#!/usr/bin/env python3
"""wr-node — daemon armada per host (tier health + exec allowlist).

Satu file, Python stdlib saja, mengikuti gaya bus/server.py.

Kerja:
  - heartbeat + snapshot ke topik health/<host> tiap HEALTH_SEC ± jitter
  - poll GET /bus/job/claim?host=<host> tiap JOB_SEC; eksekusi hanya
    perintah dalam allowlist policy lokal; hasil ke /bus/job/result
  - endpoint job belum ada di bus lama (404) → diperlakukan "tanpa job"

Konfigurasi lewat env (systemd EnvironmentFile atau export):
  BUS_URL      default http://127.0.0.1:8810
  BUS_TOKEN    token agen daemon ini (wajib)
  WR_HOST      nama host di armada (default: hostname)
  WR_POLICY    path file policy JSON (default: /etc/armada/policy.json
               atau ~/.config/armada/policy.json)
  HEALTH_SEC   default 90
  JOB_SEC      default 7
"""
from __future__ import annotations

import json
import os
import random
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error

BUS_URL = os.environ.get("BUS_URL", "http://127.0.0.1:8810").rstrip("/")
TOKEN = os.environ.get("BUS_TOKEN", "").strip()
HOST = os.environ.get("WR_HOST") or socket.gethostname()
HEALTH_SEC = float(os.environ.get("HEALTH_SEC", "90"))
JOB_SEC = float(os.environ.get("JOB_SEC", "7"))
TIMEOUT_SEC = int(os.environ.get("JOB_TIMEOUT_SEC", "300"))
MAX_OUT = 65536
VERSION = "0.1.0"

POLICY_CANDIDATES = [
    os.environ.get("WR_POLICY", ""),
    "/etc/armada/policy.json",
    os.path.expanduser("~/.config/armada/policy.json"),
]


def load_policy() -> dict:
    for p in POLICY_CANDIDATES:
        if p and os.path.exists(p):
            try:
                return json.load(open(p))
            except Exception:
                pass
    return {}


def http(method: str, path: str, body: dict | None = None, timeout: int = 15):
    req = urllib.request.Request(
        BUS_URL + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-Bus-Token": TOKEN, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception:
        return 0, {}


def post_note(topic: str, kind: str, text: str) -> bool:
    code, _ = http("POST", "/bus/post", {
        "topic": topic, "agent": f"wr-node-{HOST}", "host": HOST,
        "kind": kind, "text": text,
    })
    return code == 200


# ---------- health snapshot ----------

def _read(path: str) -> str:
    try:
        return open(path).read()
    except Exception:
        return ""


def snapshot() -> dict:
    up = float((_read("/proc/uptime").split() or ["0"])[0])
    load = _read("/proc/loadavg").split()[:3]
    mem = {}
    for line in _read("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        if k in ("MemTotal", "MemAvailable"):
            mem[k] = int(v.split()[0])
    try:
        df = subprocess.run(["df", "-h", "/"], capture_output=True,
                            text=True, timeout=10).stdout.splitlines()[-1]
    except Exception:
        df = "n/a"
    failed = []
    try:
        out = subprocess.run(["systemctl", "--user", "--no-legend",
                              "list-units", "--state=failed"],
                             capture_output=True, text=True, timeout=15).stdout
        failed = [l.split()[0] for l in out.splitlines() if l.strip()][:10]
    except Exception:
        pass
    return {
        "v": VERSION, "uptime_h": round(up / 3600, 1),
        "load": load, "mem_mb": mem, "df_root": df,
        "failed_units": failed, "ts": time.time(),
    }


# ---------- job exec (mode 'allow' saja di versi ini) ----------

def allowed(argv: list, policy: dict) -> bool:
    """Strict-match: program exact + tiap arg terhadap pola per-arg.

    policy['exec_allow'][HOST] = ["df -h", "uptime", "git -C /path *"]
    Pola per-token: '*' bebas, selain itu harus persis sama.
    """
    cmd = " ".join(argv)
    if any(d in cmd for d in policy.get("deny_always", [])):
        return False
    for rule in policy.get("exec_allow", {}).get(HOST, []):
        rp = rule.split()
        if len(rp) != len(argv):
            continue
        if all(r == "*" or r == a for r, a in zip(rp, argv)):
            return True
    return False


def run_job(job: dict, policy: dict) -> None:
    jid = job.get("id", "?")
    argv = job.get("argv") or []
    if isinstance(argv, str):
        try:
            argv = json.loads(argv)
        except Exception:
            argv = []
    res = {"id": jid, "exit_code": None, "stdout": "", "stderr": ""}
    if not argv or not allowed(argv, policy):
        res["exit_code"], res["stderr"] = 126, "ditolak policy"
    else:
        try:
            r = subprocess.run(argv, capture_output=True, text=True,
                               timeout=int(job.get("timeout_sec") or TIMEOUT_SEC))
            res.update(exit_code=r.returncode,
                       stdout=r.stdout[-MAX_OUT:],
                       stderr=r.stderr[-MAX_OUT:])
        except subprocess.TimeoutExpired:
            res.update(exit_code=124, stderr=f"timeout {TIMEOUT_SEC}s")
        except Exception as e:
            res.update(exit_code=1, stderr=f"{type(e).__name__}: {e}")
    http("POST", "/bus/job/result", res)


def claim_once(policy: dict) -> None:
    code, body = http("GET", f"/bus/job/claim?host={HOST}", timeout=10)
    if code != 200 or not isinstance(body, dict) or not body.get("id"):
        return
    run_job(body, policy)


def main() -> int:
    if not TOKEN:
        print("BUS_TOKEN kosong — isi env dulu", file=sys.stderr)
        return 2
    policy = load_policy()
    next_health = 0.0
    print(f"wr-node {VERSION} host={HOST} bus={BUS_URL} health~{HEALTH_SEC}s")
    while True:
        now = time.time()
        if now >= next_health:
            snap = snapshot()
            ok = post_note(f"health/{HOST}", "health", json.dumps(snap))
            next_health = now + HEALTH_SEC + random.uniform(-10, 10)
            if not ok:
                next_health = now + 30  # bus down → retry lebih cepat
        try:
            claim_once(policy)
        except Exception:
            pass
        time.sleep(JOB_SEC + random.uniform(0, 2))


if __name__ == "__main__":
    sys.exit(main())
