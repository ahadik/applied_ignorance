# Frozen draft session: Sleeper-only fresh data

**Session closed:** the user authorized release after full league completion. `draft_session.py release` confirmed completion through Sleeper and released the guard at 2026-09-09T03:46:42Z. No FantasyPros/nflverse refresh was performed. The remaining text documents the historical draft freeze and its implementation.

User instruction: prefetch FantasyPros now, then fetch no new FantasyPros data
until after the actual draft. Only Sleeper data should be refreshed during the
session. This supersedes earlier pre-draft/15-minute alert-refresh instructions.

Completed September 8, 2026 at **6:35 p.m. Eastern**: 11 fresh FantasyPros requests,
15.0 seconds collection including Sleeper context, 18.9 seconds through board
creation/pinning. Feeds: external-ID player directory, draft PPR ECR, PPR ADP,
QB/RB/WR/TE/K/DST season projections, latest requested 100 news items, and current
week injuries. Original retrieval/publication timestamps remain intact.

The approved board is pinned at:

`data/draft_session/1400628785413394432/board.json`

The same approved board is in the usual `data/draft_board/2026/board.json`.
A private copy of the checksummed input collection sits beside the pinned board.
Historical nflverse evidence remains embedded in the board. No nflverse data was
refetched. The network guard is `data/draft_session/network_lock.json`.

## Guarantees and bounds

- Central FantasyPros and nflverse clients check the persistent guard before
  every network attempt, including retries and forced refreshes. Valid existing
  cache hits are still permitted. Cache misses/expired entries cannot trigger
  retrieval. Draft calculations read the frozen board directly.
- Only Sleeper may supply fresh data. Do not add fresh external news/web/data
  lookups during the freeze. Continue central-client reads for picks, draft state
  and relevant Sleeper information. Never substitute frozen picks for live state.
- Frozen candidate exports verify the entire board hash, league/draft identity,
  active session and approved window. The window lasts until **6:35 a.m. Eastern
  on September 9**. Normal 15-minute alert/one-hour context age limits do not force
  a new player-data fetch within this explicitly approved snapshot session.
- This is a fixed snapshot, not a claim that news/injuries cannot change. The
  original source times remain visible. Scoring limitations remain unchanged.
- Candidate/state fingerprints, the 20-second controller observation deadline,
  actual browser agreement and queue/selection safeguards remain in force.
- The network block has **no automatic time-based release**. Expiration of the
  approved board window blocks its use but does not permit fresh FantasyPros or
  nflverse calls. If a draft runs beyond it, resolve the session explicitly.
- Collection/alert-refresh commands reject an active freeze before changing
  inputs. The normal board-build command refuses to overwrite the frozen board.
  Do not bypass this by changing cache directories, guard files or timestamps.
- A failed prefetch activates a pending-validation block. It does not label
  incomplete data ready. Resolve such a failure explicitly rather than silently
  retrying from another caller.

## Commands

```sh
# Already completed; rerunning while frozen is rejected before network reads.
python3 -m fantasy_agent draft_session prefetch --season 2026

# Offline status and verification. Verification replaces transport with a
# forbidden stub, so even a guard regression cannot make a live FP request.
python3 -m fantasy_agent draft_session status
python3 -m fantasy_agent draft_session verify

# Existing live supervision, only after the separate operational authorization.
python3 -m fantasy_agent controller watch --draft 1400628785413394432 --strategy-board data/draft_session/1400628785413394432/board.json

# After the real draft: central Sleeper reads must confirm its completion before
# network access is re-enabled. This command itself fetches no FantasyPros data.
python3 -m fantasy_agent draft_session release
```

For a separately verified mock, use its actual draft ID, the same pinned board,
and controller `--allow-mock`. Completing a mock does not release the real-draft
freeze. The next mock must use seat 13/14, 14 rounds, one FLEX and the verified
league scoring, as described in `PRE_DRAFT_PLAN.md`.

Validation: frozen exports passed at current time and three hours later. A forced
FP refresh was stopped before reservation/transport. Offline tests cover FP cache
hits/misses, nflverse network denial, shared-default guard routing, content
tampering, session expiry, unchanged live-state freshness and completion-gated
release. Test clients use isolated temporary caches and synthetic transport.
