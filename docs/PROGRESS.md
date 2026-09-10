# Current project handoff

September 10 update: the user authorized committing all `data/` to Git and assumes only one Mac runs at a time. Use Git for code/data handoff; keep `.env` and credentials excluded. This supersedes older local-only data and separate-transfer guidance.

Updated September 9, 2026 (UTC), following the September 8 draft in Eastern time.

## Verified state

- Initial Week 1 lineup applied September 9 around 05:04 UTC: Purdy replaced Mahomes through native Sleeper controls; full browser reload confirmed Purdy starting. Other eight starters retained. Flowers/Swift remain questionable; manual return-to-practice review supports provisional retention, not medical clearance. Automated validator remains REVIEW. Public API reconciliation still failed after a short settling interval because roster and matchup starters disagree; do not repeat the swap blindly. See private `data/weekly/2026/1/APPLICATION.md` and archived rationale. No automation scheduled. This supersedes older statements below that no Week 1 browser application occurred; API reconciliation remains outstanding.

- Real draft `1400628785413394432` is complete: 196 league selections, all 14 of our selections reconciled, zero required-position needs, no pending submission.
- The first two selections were automatic before takeover; the remaining 12 were supervised. Full roster and numerical-versus-agent choices: [draft result](REAL_DRAFT_RESULT.md).
- The read-only watcher is stopped. Do not resume draft actions.
- Final state was saved using `controller.py sync --draft 1400628785413394432` and `draft.py sync`, through central Sleeper reads. Local snapshots live under `data/`; `DRAFT_CONTEXT.md` records the completed context.
- User authorized `draft_session.py release`. It verified full completion and set the guard inactive at **2026-09-09T03:46:42Z**. No FantasyPros or nflverse data was refreshed. Preserve the frozen board as historical evidence.
- The weekly recommendation pipeline is implemented: see [weekly guide](WEEKLY_LINEUP.md).
  First live Week 1 collection/optimization succeeded September 9 at 04:38 UTC.
  All 14 owned players have matched weekly projections; scoring remains partial.
  No cloud backend, mobile MCP connection, scheduled weekly automation, or verified
  application of a Week 1 starting lineup has been completed.
- Weekly checkpoint: 182 tests passed. Final live run at 04:44 UTC reused all nine
  FP feeds; read-back at 04:45 UTC confirmed Mahomes still starts while the saved
  model recommends Purdy. This is an unapplied recommendation, with injury review
  and partial-scoring caveats. Run again for fresh advice before taking action.

## Delivered milestones

1. Central FantasyPros, Sleeper and nflverse clients, with provider-specific caching, request budgets/retries and historical evidence collection.
2. Joined draft board with identity quarantine, source timestamps, scoring coverage and review exports. See [milestone 2](MILESTONE_2.md).
3. Deterministic roster-aware strategy, opponent scenarios and bounded A/B planning for alternating short and long gaps. See [milestone 3](MILESTONE_3.md) and [A/B strategy](AB_STRATEGY.md).
4. Frozen draft session, live controller, queue/runbook procedures, manual `draft_now.py` fallback and offline specialist review.
5. Completed real draft, documented decisions and late operational fixes. Latest recorded suite: 165 passing tests.

## Lessons to preserve

- The model and agent sometimes chose different players. At pick 156, the script favored Kamara; Shaheed was selected for receiver/bye coverage and qualitative injury concerns. The result document records scores and reasons. This does not prove the override improved expected wins.
- Implement an append-only decision record containing model leader, selected player, exact input fingerprint, evidence and override reason. This is outstanding; the manual CLI does not currently incorporate agent judgment.
- Static replacement baselines can encourage waiting too long as the available pool changes. Evaluate availability-sensitive baselines, backup value, injury handling and bye coverage offline before relying on them next season.
- Specialist timing is a heuristic. Incomplete kicker/defense scoring prevents exact cross-position comparisons. The late-round allowance expanded from two to four; no reviewed-choice file was applied, and actual specialists were selected in the final two rounds.
- A/B planning searches capped scenarios; opponent plausibility and utility scores are not calibrated probabilities. No measured advantage over other agents has been established.
- Missing opponent Jayden Higgins identity halted planning while live state continued advancing. Engine version 3 accepts verified live pick metadata for opponent roster counts only, without inventing values or adding available candidates. Missing owned valuations still fail closed. Inspect `health.json` as well as the checkpoint.
- Browser operations sometimes took tens of seconds. Search explicitly in virtualized lists, maintain queues between turns, verify each update sequentially, and reconcile clicks through the API. A live process alone does not prove a healthy planner.
- Our final pick and full league completion are different events. Only verified full completion permitted freeze release.
- User questions are informational unless they explicitly direct a change. Explain uncertainty without treating repeated questions as a strategy instruction.

## Next work

Lineup proposals now use schema v2 with an overall free-text rationale and
append-only version records. `lineup_history.py list --season 2026 --week 1`
reviews history offline. Run/export and explicit record all preserve prior versions;
197 tests passed. See LINEUP_VALIDATION.md for writing and validating revisions.

Independent lineup validation is now implemented: [guide](LINEUP_VALIDATION.md).
The proposal JSON is exported by the weekly pipeline or its offline `export`
command. `lineup_validate.py --lineup data/weekly/2026/1/proposed_lineup.json`
collects fresh validation evidence without projections. 193 tests passed; the
04:52 UTC live validation returned REVIEW for Flowers/Swift availability and
Flowers news. A pass is time- and proposal-bound, not medical clearance or a
guarantee of participation. No lineup submission occurred.

1. Re-run `python3 weekly_lineup.py run --season 2026 --week 1`, review injuries,
   and apply/verify the starting lineup. Draft-day data is historical. Early live
   schedule observation puts Shaheed's game Wednesday evening; do not assume the
   first relevant deadline is Thursday. Reverify the current schedule before use.
2. Extend the implemented weekly pipeline with waiver services, richer inputs,
   reminders and recovery procedures. No scheduled service currently exists.
3. Audit draft decisions and evaluate model changes with paired simulations and sensitivity checks.
4. Implement the planned authenticated cloud MCP adapter and verify phone access on the user's account; see [MCP design](MCP_DESIGN.md).

## Local storage and publication

All `data/` files and `.env` stay local; GitHub does not back them up. Preserve a separate private backup. Publish source, tests and curated documentation only. Generated files previously entered Git history: removing them from the index does not sanitize older commits. Audit history or create a clean source-only repository before public publication.
