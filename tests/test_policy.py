"""Tes kontrak perilaku policy engine wr-node (mode_granted, allowed, deny-first)."""
import importlib.util
import os
import sys

spec = importlib.util.spec_from_file_location(
    "wr_node", os.path.join(os.path.dirname(__file__), "..", "node", "wr_node.py"))
wr = importlib.util.module_from_spec(spec)
sys.modules["wr_node"] = wr
spec.loader.exec_module(wr)

wr.HOST = "testhost"

POLICY = {
    "agents": {
        "devin": {"testhost": ["health", "allow", "user", "root", "sandbox"]},
        "weak": {"testhost": ["health", "allow"]},
    },
    "exec_allow": {"testhost": ["df -h", "uptime", "git -C /repo *"]},
    "sandbox_profiles": {"default": {"image": "alpine"}},
    "deny_always": ["rm -rf", "shutdown"],
}


def job(agent, mode, argv):
    return {"agent": agent, "mode": mode, "argv": argv}


def test_deny_first_beats_allow():
    assert not wr.allowed(["rm", "-rf", "/"], POLICY)
    assert not wr.allowed(["sh", "-c", "rm -rf x"], POLICY)


def test_allow_strict_tokens():
    assert wr.allowed(["df", "-h"], POLICY)
    assert not wr.allowed(["df"], POLICY)          # arg hilang
    assert not wr.allowed(["df", "-h", "/"], POLICY)  # arg ekstra
    assert wr.allowed(["git", "-C", "/repo", "status"], POLICY)
    assert not wr.allowed(["git", "-C", "/repo", "push", "x"], POLICY)


def test_mode_ladder():
    assert wr.mode_granted(job("devin", "user", ["id"]), POLICY)
    assert wr.mode_granted(job("devin", "root", ["id"]), POLICY)
    assert wr.mode_granted(job("devin", "sandbox", ["id"]), POLICY)
    assert not wr.mode_granted(job("weak", "user", ["id"]), POLICY)
    assert not wr.mode_granted(job("weak", "root", ["id"]), POLICY)
    assert not wr.mode_granted(job("ghost", "allow", ["df", "-h"]), POLICY)


def test_allow_still_strict_under_agents():
    assert wr.mode_granted(job("weak", "allow", ["df", "-h"]), POLICY)
    assert not wr.mode_granted(job("weak", "allow", ["df"]), POLICY)


def test_deny_always_covers_all_modes():
    for m in ("allow", "user", "root", "sandbox"):
        assert not wr.mode_granted(job("devin", m, ["rm", "-rf", "/"]), POLICY)


def test_legacy_policy_no_agents_allows_only_allow():
    legacy = {"exec_allow": {"testhost": ["df -h"]}, "deny_always": []}
    assert wr.mode_granted(job("x", "allow", ["df", "-h"]), legacy)
    assert not wr.mode_granted(job("x", "user", ["id"]), legacy)


if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"OK — {len(fns)} tes policy lolos")
