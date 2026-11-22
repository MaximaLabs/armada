# Security Policy

Armada is a remote-execution control plane. It is *designed* to run commands on
your machines — the security boundary is the **policy engine + token model**,
not the transport. Please read this before deploying, and before reporting.

## Threat model in one paragraph

The bus authenticates writers by bearer token; `wr-node` decides *what may run
on this host* via a local policy file that no remote caller can edit. A stolen
agent token grants only what that agent's policy grant allows on each host —
an agent with `allow` on host A can do nothing on host B. There is no shell in
the job path: `argv` is exec'd directly, and `deny_always` is evaluated before
any allow rule.

## Reporting a vulnerability

**Do not open a public issue** for anything that crosses a real boundary:
policy bypass, token impersonation, remote code execution beyond an agent's
grant, or secrets exposure.

Instead: email **security@maximalabs.tech** (or use GitHub private Security
Advisories on this repo). Include:

- the boundary you crossed (e.g. "an `allow`-only agent executed `user` mode")
- a minimal repro against a local bus (`tests/test_bus_api.py` shows how to
  spawn one in a subprocess)
- the version/commit you tested

We aim to acknowledge within 72 hours. Hardening suggestions that do not
cross a boundary (better defaults, clearer docs, stronger sandbox flags) are
ordinary public issues/PRs.

## Deployment guidance

| Surface | Recommendation |
|---|---|
| Bus port | Bind `127.0.0.1` only (the default). Expose to agents through an HTTPS reverse proxy (`/bus/*`) with TLS — never open a plaintext port to the internet. |
| `/bus/ui` | **Unauthenticated** by design — it leaks hostnames, job ids and exit codes. Front it with proxy auth, or restrict at nginx (`allow/deny`), if your bus is public. |
| Tokens | `agents.json` is plaintext by design (rotation without restart). Store it mode `600`, never in git; prefer per-agent tokens over the master `BUS_TOKEN`. |
| `root` mode | Requires the daemon's own sudo rights — grant sparingly via `agents` section. Most fleets should never grant it. |
| Kill switch | `touch /etc/warroom/fleet-deny` (or `/etc/armada/deny`) halts all execution on that node immediately. Keep the path on a root-owned filesystem. |
| `env_profile` | Secrets live in `~/.config/armada/env/*.env` (mode 600) on the **target** host — they never transit the bus or land in the audit log. |
| Audit | Messages and job results are append-only. Do not post secrets into job stdout — they are retained forever by design. |

## Known non-goals

- No rate limiting yet — a token holder can flood the queue. Deploy behind a
  proxy with limits, or accept it for trusted-fleet use.
- `sqlite` file is the single point of truth; see `bus/backup_bus_db.py` for
  the backup pattern.
