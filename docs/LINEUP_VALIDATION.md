# Independent lineup validation

The pipeline now exports `data/weekly/SEASON/WEEK/proposed_lineup.json` on a
successful recommendation. The format is documented in
`schemas/lineup.schema.json`.  `lineup_validation.check_document` implements the
required shape checks without third-party dependencies. An agent or person can
edit the assignments or create their own document using the same contract.

Each assignment specifies the exact zero-based league slot index, slot label and
Sleeper player ID. Repeated RB/WR slots are separate entries. Scope includes
league ID, roster ID, season and week. Creation time and optional origin retain
provenance. Additional claimed health/ownership/lock flags are ignored. Null
represents an empty slot and fails lineup validation.

## Rationale and append-only history

New proposals use schema version 2 and require a nonempty free-text `rationale`.
The normal pipeline fills it with an evidence-based summary of the objective,
changes, projected gain and availability caveats. To supply an agent-written
overall explanation, use `--rationale-file PATH` with `run`, `recommend` or
`export`. `rationale_source` distinguishes a deterministic summary from supplied
text. Validation still ignores prose as an assertion of health or legality.

Every new proposal is appended as `proposals/<lineup_id>.json`, with `recorded_at`
and `previous_lineup_id`. The exclusive atomic writer refuses overwrites.
`proposed_lineup.json` remains a convenience copy of the latest record. Its prior
contents are preserved before replacement, including legacy or manually edited
versions. Existing history is not retroactively rewritten or assigned invented
reasoning. Legacy v1 documents remain readable/validatable. New writes require v2.
The original `created_at` remains the analysis time.  `recorded_at` records the new
history entry. No entry implies the lineup was applied.

```sh
# Append an explanation/revision to an existing proposal, retaining old versions.
python3 lineup_history.py record --lineup data/weekly/2026/1/proposed_lineup.json --rationale-file explanation.txt

# Review saved versions, explanations and assignments chronologically; offline.
python3 lineup_history.py list --season 2026 --week 1
```

To revise assignments, edit a working copy and pass that file to `record`. Do not
edit archived files. Editing even just the rationale creates a new proposal hash
and requires a new validation. History is local/private under `data/`, so a private
backup is still needed. Append-only behavior is enforced by these commands, not
protection against someone manually deleting files. History regression tests cover
version links, exact preservation, legacy/manual-copy retention and overwrite refusal.
The full suite passed 197 tests after this addition.

## Commands

```sh
# Generate fresh advice and a structured proposal using the existing pipeline.
python3 weekly_lineup.py run --season 2026 --week 1

# Or export the most recent saved recommendation without fetching anything.
# This preserves its original date and does not validate current availability.
python3 weekly_lineup.py export --season 2026 --week 1

# Independently validate the exact proposal against current provider evidence.
python3 lineup_validate.py --lineup data/weekly/2026/1/proposed_lineup.json
```

Validation uses `weekly_data.collect(validation_only=True)` for Sleeper league,
week, roster, starters and player directory. Nflverse schedule checks. And
FantasyPros identities, injuries and news. It skips projections and never calls
the optimizer or trusts its inferred player flags. The validator shares tested
identity/slot/schedule utilities, so it is an independent decision check, not an
independent second data provider for every fact. All reads retain central cache,
quota, retry and cooldown policies. Ownership/settings are checked again after
collection. No command submits a lineup or changes a player transaction.

## Outcomes and exit codes

| Outcome | Exit | Meaning |
|---|---:|---|
| PASS | 0 | No errors or review flags detected in this evidence |
| FAIL | 1 | Definite legality/availability problem, or stale evidence |
| REVIEW | 2 | Unresolved availability, concerning evidence or near-kickoff confirmation needed |
| UNAVAILABLE | 3 | Collection, schema or another required validation step failed |

Checks cover:

- Correct league, roster, season/week, slot count/order and slot labels.
- Owned player IDs, position eligibility, no duplicates and no empty slots.
- Weekly games/byes, started bench players, locked starters in their exact slots
  and conservative persistent kickoff/lock history. A locked off-roster starter
  can be retained, but cannot be moved or replaced.
- Out, inactive, suspended or reserve injury labels are errors for adjustable
  starters. Questionable/doubtful, unknown statuses, or an uncalibrated provider
  playing probability below 0.5 require review. No invented medical severity
  score or universal injury multiplier is used.
- Injury/news identity ambiguity requires review. Missing news is not proof of
  health. Conservative keyword screening flags injury/workload language for a
  person to read, with original source text/links/timestamps in the saved result.
  It can flag old or negated stories and miss subtle reports. It never diagnoses
  a player or treats narrative extraction as an official inactive announcement.
- Inside 90 minutes of a selected unlocked player's kickoff, require official
  active/inactive and native lock confirmation. That authoritative inactive feed
  is not integrated. The script cannot issue a clean automated pass for those
  players solely because the existing feeds have no injury label.

A health flag on a locked starter is REVIEW, not a suggested illegal repair.
This validator checks the supplied lineup. It does not change assignments to
hide mistakes, optimize projections, or certify a winning strategy.

## Durable evidence and future scheduling

The validator saves `latest_validation.json` and an immutable
`validation/<id>.json` under the week directory, along with checksummed input
snapshots. Findings have severity, machine-readable code, player ID and slot.
The result includes the proposal hash, complete input hash, league-state hash,
check time, expiry, acquisition evidence, player reports and source limitations.
Collection failure writes UNAVAILABLE instead of silently serving an old pass.

For future orchestration: generate inference → save proposal → run validator →
inspect exit/status. Only an unexpired PASS for the exact same proposal hash and
unchanged relevant live state is eligible for the next execution check. FAIL,
REVIEW and UNAVAILABLE must not be treated as success. A proposed change to the
lineup requires a new validation, as does material new news or a state change.
There is no automatic override or review-acknowledgment bypass in this version.

Expiry is capped at five minutes and shortened to the relevant input freshness
deadline or next selected-player kickoff. Unknown provider publication times stay
unknown. Fresh retrieval does not guarantee current underlying information.
Immediately before browser application, verify native locks and availability.
After application, use `weekly_lineup.py verify` for read-back reconciliation.
That existing `verify` command checks actual assignments, whereas this validator
checks whether the proposed assignments have a detected problem.

## Verified checkpoint

September 9, 2026: 193 tests passed. Tests include provider-failure invalidation and attempts to spoof health flags. They also cover:

- Duplicate slots/players.
- Wrong ownership/position/week.
- Stale evidence.
- Byes.
- Moves of locked starters and bench players.
- Injury concerns.
- Missing identity joins.
- Review near kickoff.
 The live check at 04:52 UTC returned REVIEW for Flowers and
Swift availability and Flowers news, with no structural errors. It made 11 Sleeper API attempts. It reused three FP cache entries with zero new FP attempts. It made one nflverse metadata request with cached schedule bytes. No lineup
changes, cloud scheduling or notifications were performed.
