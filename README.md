# Armada — a control plane for fleets of AI agents

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="art/armada-flow.svg">
  <source media="(prefers-color-scheme: light)" srcset="art/armada-flow-light.svg">
  <img alt="Armada: agents drop job envelopes at the bus sorter; pneumatic tubes carry them to a wr-node tower on each host" src="art/armada-flow-light.svg" width="760">
</picture>

[![ci](https://github.com/verrysimatupang99/armada/actions/workflows/ci.yml/badge.svg)](https://github.com/verrysimatupang99/armada/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![deps: zero](https://img.shields.io/badge/runtime_deps-zero-brightgreen.svg)](#design-rules)

A lab project by [MaximaLabs](https://maximalabs.tech).

Armada lets AI agents (Devin, Hermes, agy CLI, DeepSeek, a cron bot — anything
that can hold a token) watch server health and run controlled jobs across many
machines — **without SSH fan-in and without opening a single inbound port on
any host**. Every component is a single Python-stdlib file you can read in one
sitting.

## Why it exists

Once your agents live on more than one machine, coordination becomes the
bottleneck: agents on different hosts can't leave each other notes without
being online at the same time, and SSH-ing into every box doesn't scale or
survive NAT. Armada inverts the flow: **one mailbox in the middle, one thin
outbound-only daemon per host**. Hosts poll out over :443; nothing listens in.

## Components

| Piece | What it is | Size |
|---|---|---|
| `bus/server.py` | Append-only SQLite mailbox + job queue + schedules + `/bus/ui` status board | ~430 lines |
| `node/wr_node.py` | Per-host daemon: heartbeat + job claim + capability-ladder executor | ~300 lines |
| `cli/armada.py` | Uniform CLI every agent uses to post jobs and read results | ~180 lines |
| `ops/` | systemd units + one-line `install.sh` | — |

## Quickstart

```bash
# 1. The bus — one host, bound to localhost, front it with HTTPS
BUS_DB=/var/lib/warroom-bus/bus.db BUS_TOKEN=<master> python3 bus/server.py

# 2. A node on each host — one line, user-level systemd, no root needed
bash ops/install.sh --bus https://bus.example.com --token <node-token> --host db1

# 3. Any agent, from anywhere — same CLI, same protocol
armada post --host db1 --mode allow -- df -h     # → job id
armada watch <id>                               # → claimed … done
armada tail <id>                                # → stdout/stderr + audit
```

`~/.config/armada/agent.env` holds `BUS_URL`/`BUS_TOKEN`/`ARMADA_AGENT` for the
CLI; `~/.config/armada/node.env` + `policy.json` configure the daemon.

## The capability ladder

The job mode is chosen by the agent, **granted or denied by the host's policy**
— the host always has veto:

| Mode | What runs | Grant needed |
|---|---|---|
| `health` | heartbeat + snapshot only | default |
| `allow` | exact-argv allowlist (`df -h`, `uptime`, …) | `allow` |
| `user` | arbitrary argv as the daemon's user | `user` |
| `root` | argv via `sudo -n` | `root` (daemon must already have sudo) |
| `sandbox` | argv inside `docker run --network none --read-only …` | `sandbox` + a `sandbox_profiles` entry |

`deny_always` beats every grant on every mode — checked first, always. Jobs are
idempotent (`dedupe`), orderable (`after_id` chains), cancellable, leased +
reaped on node death, and their full lifecycle lands in an append-only audit
topic. Secrets never cross the bus: `env_profile` names a local file the node
injects itself.

## Design rules

- **Zero runtime dependencies.** Python 3.10+ stdlib for everything; Docker is
  optional and only for `sandbox` mode; Node 20+ only if you rebuild the art.
- **Single files on purpose.** Each component ships as one copy-paste-able
  file — installing a node is `scp` + `systemctl --user`.
- **Append-only truth.** The bus never deletes: messages, job audits and
  results stay. Deny-first enforcement happens on the host, never in transport.
- **Host veto.** Policy lives on the target host (`/etc/armada/policy.json` or
  `~/.config/armada/policy.json`). A leaked agent token grants only what that
  agent could already do.

## Status & roadmap

Running in production on the MaximaLabs fleet (3 hosts: a webdock VPS, a
cloud box, a laptop). Working today: heartbeats, full job lifecycle, the whole
capability ladder, streaming output, `/bus/ui`. Roadmap:
`docs/superplan-armada-agen.md` — rate limiting, multi-bus HA, richer metrics.

## Docs

- [`docs/superplan-armada-agen.md`](docs/superplan-armada-agen.md) — the master plan (ID)
- [`docs/deploy-p2.md`](docs/deploy-p2.md) — production deploy + rollback
- [`bus/README.md`](bus/README.md) · [`node/README.md`](node/README.md)
- [SECURITY.md](SECURITY.md) — threat model, `/bus/ui` caveat, reporting
- [CONTRIBUTING.md](CONTRIBUTING.md) — workflow, tests, what we reject

## License

MIT — see [LICENSE](LICENSE). `art/iso-kit.mjs` is vendored from
[wheresryan22/anatomy](https://github.com/wheresryan22/anatomy) (MIT).
