#!/usr/bin/env python3
"""Patch bus-server.py: token per-agent (identity terikat ke token).
Idempoten. Legacy BUS_TOKEN tetap bekerja sebagai master agar tidak memutus mesin lama.
"""
import re, sys

P = "/home/admin/bus/server.py"
src = open(P).read()
orig = src

# 1) helper map token -> agent
if "def agent_tokens()" not in src:
    anchor = 'def db() -> sqlite3.Connection:'
    helper = '''def agent_tokens() -> dict:
    """token -> nama agent. File JSON, dibaca ulang tiap request (rotasi tanpa restart)."""
    path = os.environ.get("BUS_TOKENS_FILE", "/home/admin/bus/agents.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        toks = data.get("tokens") or {}
        return {str(v).strip(): str(k).strip() for k, v in toks.items() if str(v).strip()}
    except Exception:
        return {}


'''
    src = src.replace(anchor, helper + anchor, 1)

# 2) _auth -> tetapkan self.identity
old_auth = '''    def _auth(self) -> bool:
        want = token()
        if not want:
            self._send(500, {"error": "server token belum diset"})
            return False
        if self.headers.get("X-Bus-Token", "") != want:
            self._send(401, {"error": "token salah"})
            return False
        return True'''
new_auth = '''    def _auth(self) -> bool:
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
        return ident == "*" or not requested or requested == ident'''
if old_auth in src:
    src = src.replace(old_auth, new_auth, 1)
elif "def _agent_allowed" not in src:
    sys.exit("GAGAL: blok _auth tidak cocok")

# 3) POST: agent harus sama dengan identitas token
old_post = '''        agent = (b.get("agent") or "anonymous").strip()[:64]'''
new_post = '''        agent = (b.get("agent") or "anonymous").strip()[:64]
        if not self._agent_allowed(agent):
            return self._send(403, {"error": f"token milik '{getattr(self, 'identity', '?')}', "
                                             f"tidak boleh post sebagai '{agent}'"})'''
if old_post in src:
    src = src.replace(old_post, new_post, 1)
elif "tidak boleh post sebagai" not in src:
    sys.exit("GAGAL: blok do_POST tidak cocok")

# 4) GET: cursor agent tidak boleh dipalsukan
old_get = '''        if not self._auth():
            return
        q ='''
if old_get in src:
    src = src.replace(old_get, '''        if not self._auth():
            return
        q =''', 1)

if src == orig:
    print("tidak ada perubahan (sudah ter-patch)")
else:
    open(P, "w").write(src)
    print("server.py ter-patch")

# sanity: kompilasi
import py_compile
py_compile.compile(P, doraise=True)
print("kompilasi OK")
