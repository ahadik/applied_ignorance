# Data access and draft workflows

Provider access is independent of draft decisions. Saved application commands
or future MCP services call these shared entry points. Agents do not issue
one-off HTTP calls.

| Layer | Entry point | Responsibility |
|---|---|---|
| Sleeper provider | `sleeper.get_sleeper(path, **options)` | Public GET reads with endpoint cache policy, shared cooldown and bounded retries. No draft assumptions |
| FantasyPros provider | `fantasypros.get_fantasypros(path, params, ...)` | General supported NFL feeds with shared authentication, cache, quota, cooldown and retry policy |
| nflverse provider | `nflverse.get_nflverse(dataset, season, ...)` | Published CSV assets with revision-based caching, checksums, metadata revalidation, persistent request budgets/cooldowns and bounded retries |
| Persistence | `storage.save_atomic(path, data)` | Replace local JSON only after serialization succeeds. No provider or strategy dependencies |
| Weekly collection | `weekly_data.context`, `weekly_data.collect` | Validated live league/week state, weekly FP feeds and nflverse schedules. Isolated snapshots |
| Weekly analysis | `weekly_model.build`, `weekly_model.optimize` | Offline scoring, exact legal assignment, persistent-lock inputs, injury alternatives |
| Weekly commands | `weekly_lineup.py run/recommend/verify` | Collect/analyze, fresh-snapshot recomputation, or read-back verification. No account writes |
| Deadline collection | `automation.py collect-deadlines` | Shared Sleeper ownership/rules reads and nflverse fixtures. Immutable observations and acquisition evidence |
| Deadline planning | `automation.py plan` | Offline desired checks, capacity findings, prior obligations and coverage gaps. No scheduler writes |
| Scheduler evidence | `automation.py schedule-import/schedule-diff/schedule-record/schedule-verify` | Local inventory, serialized operation records and read-back verification. The agent applies supported scheduler controls separately |
| Shared scoring | `player_scoring.py` | Identity joins and explicit scoring coverage, shared by draft and weekly analysis |
| Draft collection | `draft_data.read_draft_context(config)` | Assemble league rules, user identity, draft, picks and rosters. Validate resource scope |
| Live draft collection | `draft_data.read_live_draft(draft_id)` | Read draft metadata, trades and picks. Reject unknown or unsupported traded-pick ownership |
| Draft commands | `draft.py`, `controller.py` | Save snapshots, calculate snake order/scoring, supervise picks and queue readiness |
| Draft history | `draft_history.py`, `draft_history_analysis.py` | Collect selected nflverse inputs, then calculate historical usage and current depth context offline |
| Draft inputs | `draft_inputs.py` | Collect league context, player directories, FP projections/consensus/ADP/alerts through central clients. Save checksummed inputs |
| Integrated board | `draft_board.py` | Offline ID joins, scoring coverage, starter value, historical evidence, review report and expiring candidate export |
| Draft strategy | `draft_strategy.py` | Offline roster marginal value, seeded two-pick scenarios and state-bound candidate export. No provider access |
| Strategy evaluation | `draft_strategy_evaluate.py` | Offline examples/replays, paired simulated drafts, stress checks and provenance-checked report |
| A/B strategy | `draft_ab.py`, `draft_ab_evaluate.py` | Bounded short-gap maximin, long-gap future-pair simulations and offline timing/comparison. No provider reads |
| Static order preparation | `draft_preplan.py`, `draft_data.read_pre_draft_context` | Seven logical central Sleeper reads. Validated owner/slot mapping, saved actual-seat mock profile and offline opening scenarios |

See `PRE_DRAFT_PLAN.md` for static order integration and offline `draft_inputs.py
adopt-context`. That command preserves player-data timestamps and requires a
subsequent board rebuild. It does not claim fresh player inputs.

See `NFLVERSE.md` for the third provider's data, collection/analysis commands and
freshness rules. It has no FantasyPros or Sleeper dependency and uses no API key.
See `NFLVERSE_RESEARCH.md` for the cited source/schedule/schema research and future
feed guidance. `python3 nflverse_collect.py usage` inspects local budgets without
HTTP calls.  `--revalidate` checks metadata without forcing unchanged downloads.
See `MILESTONE_2.md` for integrated collection/build/review commands and measured
coverage. The candidate export is a separate review file, not an applied queue.

The dependency direction is application → domain collection → provider. Provider
clients do not import draft code. The FantasyPros diagnostic reads NFL state
directly through the general Sleeper client and saves reports through `storage`.
It no longer imports `draft.py`. Future lineup and waiver services can reuse both
provider clients without importing draft workflows.

## Existing commands

Run from the project root:

| Command | Effect |
|---|---|
| `python3 draft.py sync` | Five logical Sleeper reads through `draft_data`. User profile may be cached, remaining resources are live. Saves validated `data/snapshot.json` and renders `DRAFT_CONTEXT.md` |
| `python3 draft.py summary` | Reads the saved snapshot and rewrites `DRAFT_CONTEXT.md`. No API reads |
| `python3 controller.py sync --draft DRAFT_ID` | Up to three live Sleeper reads through `draft_data`, without automatic retries. Controller validates the board before saving state |
| `python3 fantasypros_diagnostic.py --season 2026` | Shared cache-first FantasyPros access probes plus a Sleeper NFL-state read when reached. Saves private reports |
| `python3 -m unittest discover -v` | Offline tests using simulated provider responses and temporary storage |

See `CONTROLLER.md` for user IDs, watch mode and browser observation requirements.
These commands retain their existing arguments and output paths. Do not use the
live diagnostic as an automatic test.

## Provider policies and limits

`get_sleeper` returns the decoded provider JSON by default. It accepts plain
relative resource paths, fixes the API host, refuses redirects, uses a five-second
socket timeout per attempt, and returns safe errors. Network reads request HTTP
cache revalidation with `Cache-Control: no-cache`. This does not establish when
the provider last published data. Null remains null. Empty lists remain empty.
Domain collectors own identity, completeness, and season/league validation.

### Sleeper cache policy

| Resource | Maximum local cache age | Reason |
|---|---:|---|
| Exact `user/{id_or_username}` profile | 300 seconds | Profile/identity lookup, not roster state |
| Draft metadata, picks, traded picks | 0 | Changes during a draft must be visible on the next read |
| League settings, rosters, matchups, transactions | 0 | Ownership, scoring, settings and results may change |
| NFL state, full player records, trending players | 0 | Week/status, injury, team and trend data may change |
| All other paths, including user league listings | 0 | Unknown resources default to live reads |

Only profile responses are cached. The player directory contains mutable fields
and is intentionally not cached. Avoid repeatedly fetching the full directory.
If a future identity-only collector needs a long-lived directory, design a
separate snapshot of verified stable fields without reusing it as current
injury/team evidence. There are no push invalidation subscriptions.

Saved commands can use these options on the central entry point:

- `max_age`: shorten the endpoint's age, including zero to require a new read.
  Attempts to extend the endpoint policy are rejected, so a caller cannot enable
  caching for picks or other live resources.
- `refresh=True`: bypass a profile cache entry and replace it after a successful
  refresh. Failure raises. It does not return the previous entry as a fallback.
- `invalidate_sleeper(path)`: delete a known-changed profile before its next read.
  Omit the path to invalidate all profile entries. Invalidation never resets the
  request ledger or cooldown. A failed refresh preserves the last good cache.
  Invalidate first if a known change makes even that still-unexpired entry invalid.
- `validator=...`: run domain validation before a cache write and on every hit.
- `with_metadata=True`: return `data`, `fetched_at`, `cache_hit`,
  `cache_age_seconds`, `network_attempts` and an explicitly unknown
  `source_updated_at`. Without this option the existing payload interface stays
  unchanged. Retrieval time is never substituted for source publication time.

Cache entries expire at their original fetch deadline. Reads do not extend it.
Server `no-store`, `no-cache`, `max-age` and `Age` may shorten or disable caching,
never lengthen it. Null/empty and invalid results are not cached. Expired entries
are never served on failure. The ignored `data/sleeper/` SQLite store and process
lock persist the cache, attempt ledger and cooldown across local commands and
coalesce concurrent profile cache misses. Mutable reads are not coalesced into
cached results. This is local process coordination, not distributed cloud locking.

### Sleeper retry policy

Provider errors expose safe diagnostic fields for connection failures, HTTP failures and cooldowns.
These fields include the category, HTTP status when available, attempt count and cache-hit flag.
Connection failures retain their category after retries. They are not reported as observed HTTP 503 responses.
Unknown diagnostic fields remain null. Raw transport messages and response bodies remain excluded.

- Default: at most two retries (three total attempts) for connection/timeouts and
  HTTP 500/502/503/504, with one- then two-second backoff. Each network attempt is
  recorded before sending. Local attempts are spaced at least 0.1 seconds apart.
  The socket timeout is not a strict total command deadline, including lock waits.
- HTTP 429 saves a shared cooldown and returns immediately. Transient HTTP errors
  with `Retry-After` do the same. Parse seconds or HTTP dates. Malformed/missing
  cooldown values fall back to 60 seconds. Later calls respect the cooldown.
  Valid profile cache hits can still be served without a request during cooldown.
- Other HTTP failures and invalid JSON/data are not retried. Nothing silently
  substitutes stale data. `retries=0` disables transient retries but still honors
  cooldowns.  `read_live_draft` uses it for every read to protect draft timing.
- `Sleeper.usage()` reads local attempts over the preceding 24 hours. It is not
  provider-wide usage or a provider quota guarantee. All operational callers must
  use the default shared directory. Separate hosts do not share state.

Offline verification: 51 tests pass across the project. The tests include cache expiration, restart persistence, mutable-resource freshness, invalidation and concurrent misses. They also include retry limits, Retry-After, invalid data and live-draft retry overrides. No live
API calls were made to implement or verify these policies.

FantasyPros keeps its existing metadata envelope and all existing safeguards in
`fantasypros.py`. Its SQLite location and singleton remain unchanged. See
`FANTASYPROS.md` for the provider contract. Providers have different response and
quota semantics. This refactor does not pretend they share identical policies.

Separate Sleeper requests are not a transactional snapshot. The controller still
checks pick sequences, draft identity, freshness and browser agreement. Failed
collection does not replace a good snapshot. Milestone 2 provides validated identity
joins and partial scoring. Milestone 3 adds roster-specific scenario planning.
See `MILESTONE_3.md` for its explicit assumptions and evaluation limits. The
controller's `--strategy-board` option performs this local calculation after
central-client reads without adding any FantasyPros/nflverse requests.
