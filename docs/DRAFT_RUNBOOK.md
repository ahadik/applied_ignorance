# Draft operating runbook

**Active frozen session:** follow [DRAFT_SESSION.md](DRAFT_SESSION.md). The user
has prohibited non-Sleeper fresh data until the real draft completes. Earlier
instructions below to refresh expired player sources are superseded for this
approved session. Use the pinned board and retain live Sleeper/UI checks.

Read before drafting and after every compaction, reconnect, or interruption. Based on two completed mocks and the [partial advanced-strategy mock](MOCK_3_ADVANCED.md). The read-only monitor and selection-preparation checks are implemented in `controller.py`. Follow [controller instructions](CONTROLLER.md). Browser queue maintenance remains supervised, and these safeguards are not a guarantee against failure.

## Required operating changes from mock 3

- Before starting a clock, verify the central Sleeper controller works in the execution environment. Restricted runs returned HTTP 503. The same command succeeded with network permission. Use the approved network path and retain provider budgets/cooldowns. Do not assume every 503 means Sleeper is down.
- Search each target explicitly. The player list is virtualized, so a player outside its rendered portion may have no matching element. Wait for the filtered result before acting.
- Update the queue sequentially: add one player, wait for and inspect the visible queue update, then add the next. An initial six-click batch left only one confirmed entry. Reconcile actual names/order after every change. Never count attempted clicks as applied entries.
- Distinguish the player-list row from the same name in the queue. In this mock, `.name.col-border-right` identified the list name, `.queue-action` the queue control, and `.player-rank-item2 ... .draft-button` the selection control. These are observed hints, not permanent selectors: inspect the current DOM before reuse.
- Prepare between turns. Keep live reads and reporting compact. Do not dump entire candidate files or full draft trees into the conversation. UI inspection and observation transfer consumed more operational attention than calculation in this rehearsal. No precise latency attribution has been measured.
- If browser and API differ, wait for agreement and fresh calculation before prepare/select. The five-second watcher sleep adds network/computation time. Provider update lag has not been isolated. Never restamp old observations to pass the freshness gate.
- Manual takeover: stop agent browser actions, then use `draft_now.py`. See [MANUAL_DRAFT.md](MANUAL_DRAFT.md). Stopping this process or the watcher does not pause Sleeper or disable ongoing autopick.
- Remaining engineering work, not implemented by these notes: reduce observation-transfer overhead, measure end-to-end freshness/latency, and preserve an append-only per-pick strategy audit. Existing recommendation and submission files overwrite earlier results.

## Before the draft

- Read [the assigned-seat update](PRE_DRAFT_PLAN.md): last verified seat 13/14,
  14 rounds, one FLEX. These supersede the earlier mock format. Verify again.

- Verify actual league ID 1400628784381612032, draft ID and URL, account ahadik, scoring, roster slots, clock, and assigned seat. Do not assume mock seat 7 or identify a draft by title alone: the second mock inherited the first mock's title.
- Confirm current data source timestamps and injury flags. Recompute league-specific values and roster coverage when the calculation tools are available. Clearly disclose any missing independent data or model.
- Open the verified live room early, confirm computer/session readiness, and populate Sleeper's native queue before the clock starts. Keep ongoing auto-pick off for supervised drafting.
- Maintain a saved ranked fallback list and the checkpoint below. Do not rely on chat history for current state.

## Between turns

1. Reconcile new picks and current roster from fresh state. Use controller `--strategy-board data/draft_board/2026/board.json` for milestone 3 recomputation/reuse, then read its current candidates and `strategy_result.json`. See `MILESTONE_3.md`. Exact-state fingerprints and source deadlines must pass. Strategic reasoning should use those outputs.
2. Refill the native queue with acceptable alternatives, accounting for intervening picks. Aim for at least three surviving alternatives near our turn, and more when many teams pick before us. A count is not a guarantee of coverage.
3. Verify the actual displayed queue order and Next Pick. Remove obsolete positional targets. Remove/re-add moves an entry to the end. Drag ordering was not tested.
4. Update the checkpoint after our selections and material queue/strategy changes. Queue entries are fallbacks for the current situation, not a fixed season-long or multi-round plan.
5. Keep observations compact: current turn, roster changes, candidate rows, queue and auto-pick state. Avoid sending the entire draft board into the conversation repeatedly.

## On our turn

1. Verify the live room, active pick, our seat and clock from a fresh observation.
2. Verify the first surviving queue entry is appropriate and available. Use prepared analysis. Target selection within 30 seconds. This is an operating target, not a measured service guarantee.
3. Confirm the exact rendered player row immediately before submission. Searches can finish after another team takes the target. An empty or changed result requires a new choice, never a blind click.
4. Use the verified player-row plus control to submit. Player-name clicks open details. Do not reuse screen coordinates or accessibility IDs without a fresh observation of the current layout.
5. Verify the named pick and updated roster before doing anything else. If submission is uncertain, reconcile first. Do not retry blindly.
6. If time is short, select the best verified prepared alternative promptly. Avoid starting new research or UI experiments. Keep the native queue populated as the fallback if interaction cannot finish.

## Timeout, compaction, or connection recovery

Manual terminal fallback: `python3 -m fantasy_agent draft_now` prints fresh advice without a
browser or active agent. See [MANUAL_DRAFT.md](MANUAL_DRAFT.md). Stop agent browser
actions before taking over. The command itself does not stop them.

1. Read this runbook and the saved checkpoint, then inspect live state. The checkpoint can be stale. Live selections are authoritative.
2. Immediately inspect the auto-pick banner/switch. In mock 2, one timeout selected the first queued player AND enabled ongoing auto-pick. After the remaining queue emptied, Sleeper made the next pick automatically without a fresh two-minute decision window.
3. Turn ongoing auto-pick off to regain supervised control. Reconcile every intervening selection, roster needs, and the surviving queue before another pick.
4. Reopen the saved correct room if the tab is stale. This recovered mock 1. Do not assume browser-disconnection behavior or offline queue persistence has been tested.
5. Refill and verify the queue immediately. A queue protects a choice only while suitable candidates remain. It cannot replace active supervision for an extended absence.

## External checkpoint

Use the controller's per-draft `data/drafts/DRAFT_ID/checkpoint.json` (superseding the previously proposed single live checkpoint). Refresh after each of our picks and material queue changes. Keep it concise and write unknown values as null. Record:

- observation time with timezone. League ID, draft ID and URL. Assigned seat.
- last verified overall pick and our next pick.
- our selected player IDs/names/positions and remaining roster needs.
- ordered queue as actually observed, with its observation time.
- observed auto-pick state.
- ordered recommended alternatives, data timestamps and short strategic rationale.
- any pending selection, verification uncertainty or recovery action.

Do not create a live checkpoint using mock data. A reader must refresh from Sleeper before acting. Browser handles and old accessibility IDs are not durable state.

## Strategic limits from the mocks

- Both mocks used Sleeper's displayed rankings/projections, not independent optimization. Do not claim they establish an advantage or reuse the resulting rosters as a draft plan.
- Account for injury uncertainty, positional coverage and concentrated bye weeks without making bye avoidance an absolute rule.
- Mock bots provide no reliable evidence of real league members' agent strategies.
- Keep kicker/defense and bench decisions responsive to league rules, availability and roster needs. Clear stale queue candidates as needs change.

## Evidence

- [Mock 1: direct selection and recovery](MOCK_1.md)
- [Mock 2: queue and timeout behavior](MOCK_2_QUEUE.md)

The mocks verified these functions:

- Add and remove queue entries.
- Move an entry to the end through removal and addition.
- Automatically remove drafted entries.
- Use queue precedence on timeout.
- Continue auto-pick after timeout.
- Recover manually.
- Complete rosters.

Mock 3 verified four iterations of the deterministic recommendation → observed queue → prepare → browser selection → API reconciliation loop. See [MOCK_3_ADVANCED.md](MOCK_3_ADVANCED.md).

The mocks did not verify these functions:

- Preserve the queue while offline.
- Handle timeout in the actual league.
- Use the draft button in the queue panel.
- Change queue order through drag controls.
- Maintain the queue without supervision.
- Complete a draft with the advanced engine.
- Cover late rounds in the browser.
- Recover through compaction in the integrated workflow.
