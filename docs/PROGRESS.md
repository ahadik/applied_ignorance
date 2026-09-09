# Current project handoff

Updated September 9, 2026 (UTC), following the September 8 draft in Eastern time.

## Verified state

- Real draft `1400628785413394432` is complete: 196 league selections, all 14 of our selections reconciled, zero required-position needs, no pending submission.
- The first two selections were automatic before takeover; the remaining 12 were supervised. Full roster and numerical-versus-agent choices: [draft result](REAL_DRAFT_RESULT.md).
- The read-only watcher is stopped. Do not resume draft actions.
- Final state was saved using `controller.py sync --draft 1400628785413394432` and `draft.py sync`, through central Sleeper reads. Local snapshots live under `data/`; `DRAFT_CONTEXT.md` records the completed context.
- User authorized `draft_session.py release`. It verified full completion and set the guard inactive at **2026-09-09T03:46:42Z**. No FantasyPros or nflverse data was refreshed. Preserve the frozen board as historical evidence.
- No cloud backend, mobile MCP connection, weekly automation, or Week 1 starting lineup has been completed.

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

1. Collect current Week 1 availability through central clients and determine the starting lineup. Draft-day data is historical.
2. Build reusable weekly lineup and waiver services, then reminders and recovery procedures. No scheduled service currently exists.
3. Audit draft decisions and evaluate model changes with paired simulations and sensitivity checks.
4. Implement the planned authenticated cloud MCP adapter and verify phone access on the user's account; see [MCP design](MCP_DESIGN.md).

## Local storage and publication

All `data/` files and `.env` stay local; GitHub does not back them up. Preserve a separate private backup. Publish source, tests and curated documentation only. Generated files previously entered Git history: removing them from the index does not sanitize older commits. Audit history or create a clean source-only repository before public publication.
