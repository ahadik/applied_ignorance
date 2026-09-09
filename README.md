# Fantasy Football Agent Lab

A personal experiment in managing a Sleeper fantasy football team with deterministic software and agent-assisted analysis. Python owns data access, validation and calculations; the agent interprets evidence, explains choices and supervises authorized browser actions.

The 2026 draft is complete: a 14-team, 14-round PPR league, drafting from seat 13. The first two picks were automatic before takeover and the remaining 12 were supervised. This is an experimental decision system, not a demonstrated winning strategy.

## Start here

- [Current progress and next steps](docs/PROGRESS.md)
- [Final roster, decisions and lessons](docs/REAL_DRAFT_RESULT.md)
- [Agent operating instructions](AGENTS.md)
- [Saved draft context](DRAFT_CONTEXT.md)

Weekly lineup management, waivers, cloud hosting and mobile MCP access are future work. There is no unattended weekly service running.

## Architecture

```text
FantasyPros       Sleeper       nflverse
     |               |             |
central clients: authentication, caching, limits, retries
                     |
          collectors and local snapshots
                     |
        joined board and scoring coverage
                     |
       deterministic A/B strategy engine
                     |
        controller / manual advice CLI
                     |
       agent review + supervised browser
```

| Component | Responsibility |
|---|---|
| `fantasypros.py`, `sleeper.py`, `nflverse.py` | Shared provider access and request policies |
| `draft_inputs.py`, `draft_history.py` | Collect reusable source inputs and historical evidence |
| `draft_board.py` | Join identities and calculate supported scoring |
| `draft_strategy.py`, `draft_ab.py` | Roster-aware, bounded opponent-scenario planning |
| `controller.py` | Live state, readiness checks and selection reconciliation |
| `draft_now.py` | Terminal recommendation for manual drafting |
| `specialist_review.py` | Offline kicker/defense and bench-value review |
| `draft_session.py` | Prefetch, pin, verify and release a draft snapshot |
| `tests/` | Offline tests with simulated providers |

Application services should remain independent of chat history. A future MCP adapter will wrap those services; it is [designed](docs/MCP_DESIGN.md), not deployed. Sleeper's public API is read-only; the controller does not execute browser selections.

## Local setup

Developed with Python 3.13 on macOS using the standard library. File locking uses POSIX `fcntl`; use macOS, Linux or WSL.

```sh
python3 -m venv .venv
source .venv/bin/activate
cp .env.example .env
```

Set `FANTASYPROS_API_KEY` in `.env` to your personal approved key. Never paste it into chat, logs or Git. Review `config.json` before collection. This repository contains personal league IDs and some command defaults tied to the completed draft; changing one config file is not a complete migration to another league.

```sh
python3 -m unittest discover -v
```

Tests use simulated responses and temporary storage. The latest recorded suite has 165 passing tests. See [test guidance](tests/README.md).

Generated data is deliberately excluded. A fresh clone cannot generate meaningful advice until inputs are collected and validated. Follow [data access](docs/DATA_ACCESS.md), [board collection](docs/MILESTONE_2.md), [FantasyPros guidance](docs/FANTASYPROS.md) and [nflverse guidance](docs/NFLVERSE.md).

## Commands and data effects

Run commands from the project root. Read the relevant runbook before using draft operations.

| Command | Effect |
|---|---|
| `python3 draft_session.py status` | Inspect local snapshot/guard status |
| `python3 controller.py sync --draft 1400628785413394432` | Read Sleeper through the central client; update local draft state |
| `python3 draft.py sync` | Refresh saved context through Sleeper |
| `python3 draft_now.py` | Read live Sleeper state and calculate advice using the configured board |
| `python3 specialist_review.py --draft 1400628785413394432` | Review saved state and board offline; save a local report |
| `python3 draft_session.py release` | Verify full draft completion through Sleeper and release the network freeze |

These draft commands are retained for reproducibility. **Do not restart the completed draft or treat its frozen board as current weekly advice.** The guard was released with user authorization at 2026-09-09 03:46:42 UTC; release did not refresh FantasyPros or nflverse.

For future draft operation, consult the [runbook](docs/DRAFT_RUNBOOK.md), [controller guide](docs/CONTROLLER.md) and [manual fallback](docs/MANUAL_DRAFT.md). Recommendations are not executed selections; verify the room, turn and player identity before any browser action.

## Data and model boundaries

All retrieval must use the central clients. Do not bypass their ledgers with direct HTTP calls or alternate cache directories. Mutable Sleeper state is read live. FantasyPros and nflverse use their documented cache and publication policies; local quota accounting is not an authoritative provider balance.

The approved personal FantasyPros allowance is one request per second and 500 per day, for personal, non-commercial use. Keep licensed payloads and API access private. The client reserves headroom with a 400-attempt routine budget, a 500-attempt hard ceiling and 1.05-second spacing. See [provider guidance](docs/FANTASYPROS.md) before collection.

Strategy scores are uncalibrated utilities, not win probabilities. A/B planning explores capped alternatives. Static replacement floors, incomplete specialist scoring and qualitative injury/bye adjustments remain limitations. The manual CLI reports model advice, which can differ from a documented agent override. A unified append-only override audit is still outstanding.

## Publishing to GitHub

Publish source, tests and curated documentation. `.env` and all of `data/` are ignored; keep a separate private backup of local snapshots. Review league IDs, usernames and roster details in documentation before sharing.

```sh
git status --short
git diff --check
git diff --cached --check
git ls-files .env 'data/*'
```

The last command should return nothing. **Generated data was previously tracked in this repository. Untracking it does not remove older commits.** Before a public push, audit and sanitize history or create a separate clean source-only repository. This README does not establish that existing Git history is safe to publish.

## Next steps

Prepare the Week 1 lineup from fresh availability data; build reusable lineup/waiver services and reminders; evaluate draft-model limitations; then deploy an authenticated backend and test mobile MCP access. See [progress](docs/PROGRESS.md) for the handoff.
