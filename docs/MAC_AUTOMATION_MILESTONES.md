# Implementation milestones for Mac-based season management

September 10, 2026. Implementation plan for [MAC_AUTOMATION_DESIGN.md](MAC_AUTOMATION_DESIGN.md). No new automation modules, schedules, Git commits or deployments are delivered by this document. Build on this Mac; publish reviewed source via GitHub; install and commission the awake Mac.

Milestone order: M0 → M1 → M2 → M3 → M4 → M5 → M6. M7 expands roster management after dependable lineup operation. Offline M1/M2 work may proceed while account capability verification awaits owner access; live orchestration remains gated by M0.

**M0 — Prove the ChatGPT runtime boundary**

Deliver a reusable harmless probe command and capability report schema. The command writes host/time/project/release evidence locally, contains no credentials, and has no Sleeper writes. In an interactive session, set up an explicitly identified disposable scheduled task using supported controls. Observe an actual fresh scheduled run rather than pressing Run now alone.

Probe project/interpreter selection, unattended file permissions, centrally controlled read access, browser availability and native read-only Sleeper inspection. Separately test complete task inventory, create, change time/prompt, disable/cancel, one-off semantics, reported time zone and firing latency. Clean up disposable tasks and verify removal. Test behavior after closing a chat and after restarting the app. Record app/account/machine-specific limitations and scheduling limits without guessing their values.

Acceptance: capability matrix has evidence for every feature the chosen mode uses. Browser inspection makes no lineup changes. Failed or missing features select an explicit fallback mode from the design. Exit deliverable states whether dynamic scheduling plus browser execution is feasible; it must not merely report that an interactive tool worked. Repeat key probes on the runtime Mac at M5.

**M1 — Durable contracts and run records**

Implement `automation_store.py`, schemas, example policy and `automation.py init/status`. Add run/event records, mode gates, atomic claims, proposal/action references and schema migration versioning. Default new automation to disabled until setup is verified. Assume only one Mac operates at a time. Reuse `storage.save_atomic` for exports and existing shared provider stores unchanged.

Define typed errors for stale revision, unknown schema, missing state and incomplete prior execution. Build a compact context packet with references to relevant weekly records; do not put the season's conversation history into prompts.

Acceptance: tests under `tests/` cover duplicate claims, crash recovery, expired leases, atomic persistence, unknown schemas and preservation of append-only history. Explicit clock injection makes tests reproducible. Existing weekly/draft tests remain green.

**M2 — Deterministic deadline planning**

Implement `automation_deadlines.py` and `automation_plan.py`. Proposed CLI: `automation.py collect-deadlines` uses documented central clients; `automation.py plan --observations PATH --policy PATH --as-of UTC` is offline and writes an immutable canonical plan. Use exact season/week, verified fixtures, relevant owned alternatives and league waiver settings. Explain collection effects and actual cache/network evidence in command output.

Generate desired checks, rendered prompt payloads, stable IDs/revisions, capacity findings and coverage intervals. Preserve plans and source timestamps. Support midnight/week boundaries, daylight saving, postponements, earlier backup locks, deadline changes, overdue work and incomplete inputs. Never start another draft or mock.

Acceptance: hand-calculated fixture cases match exact UTC times. Same inputs/policy/clock yield byte-stable canonical specs. Changing a kickoff changes the revision/time while preserving logical identity. Missing data cannot silently erase coverage; expired actions do not become future executable work. All tests use synthetic provider fixtures under `tests/`.

**M3 — Scheduler reconciliation with verified read-back**

Implement `automation_reconcile.py` and proposed commands `schedule-import`, `schedule-diff`, `schedule-record`, `schedule-verify`. These commands validate saved control results; they do not independently call a private ChatGPT API. Render exact allowlisted scheduling operations for the agent to apply using the M0-verified interface.

Add protected daily-anchor handling, scoped ownership markers, fresh complete inventory requirements, returned task IDs, operation receipts and unknown-outcome recovery. Serialize scheduling changes. Handle duplicate tasks, task caps, malformed timestamps, stale observations and a timeout after successful creation. Only verified observed task state counts as coverage.

Acceptance: fake inventories cover missing, matching, changed, duplicate and unrelated tasks. Repeating reconciliation after success yields no changes. Incomplete inventory cannot trigger mass creation/deletion. A harmless live cycle creates, verifies, updates and removes a test check without touching unrelated tasks. If M0 cannot support inventory/read-back, ship manual schedule instructions and label automatic reconciliation unavailable.

**M4 — Bounded daily and deadline workflows**

Implement `automation_run.py`, `automation_health.py` and versioned daily/check prompt templates. Proposed commands: `begin`, `context`, `finish`, `health` and `pause/resume`. Daily work ensures coverage through the next planner plus overlap, then prepares football decisions. Deadline runs claim their check and use the existing weekly analysis, proposal-history and validator services.

First mode is observe/propose. Separate desired, scheduled, running and completed status. Store provider acquisition counts and failure causes. Add a runbook with exact recovery for missing login, quota cooldown, missed planner, changed ownership and incomplete execution. Integrate an owner-selected notification route only after authorization and a delivery test; no unsolicited messages to other managers.

Acceptance: scheduled harmless end-to-end runs save receipts and verified future coverage across two planning cycles. Restart after claiming work and after scheduler creation; prove recovery produces neither blind duplicates nor false success. Verify a superseded prompt exits before external work. Daily and deadline runs cannot simultaneously claim a mutating workflow.

**M5 — Commit the project and set up the awake Mac**

Commit the source, tests, documentation and all `data/` to the existing Git repository. Exclude `.env` and credentials. Run `python3 -m unittest discover -v` before release, then push the completed checkpoint when requested. No clean-history export, separate data-transfer tooling or host-isolation system is required.

On the awake Mac, clone/pull the repository, install the tested Python environment, configure `.env`, and sign in to ChatGPT and Sleeper. Repeat M0 scheduling/browser probes there and configure tasks for that checkout. Begin in propose mode.

Only one Mac runs at a time. Finish work and commit/push data before switching; pull before starting on the other Mac. This carries provider ledgers, lock history and pending-action evidence with the code. Preserve timestamps and revalidate current league state before acting. Configure task definitions and permissions on the new Mac separately.

Acceptance: the second Mac has the same committed code/data, tests pass, credentials remain excluded, and an actual scheduled run accesses the correct checkout and browser. Document these steps in a short `docs/RUNTIME_MAC_RUNBOOK.md`.

**M6 — Verified lineup execution and limited autonomy**

Resolve the existing browser/API starter disagreement first. Add durable weekly execution transitions and bounded reconciliation, authority checks and a pre-action native-state record. Reuse the independent validator; add authoritative availability evidence and a narrowly scoped, auditable review-resolution contract where required. This is necessary because current near-kickoff validation cannot issue a clean pass from the existing feeds alone.

Begin with owner-supervised legitimate lineup operations. Record each visible change and full reload/API read-back. Exercise disconnect-after-click and stale-state recovery with simulated execution evidence; do not manufacture unnecessary real roster changes to test failures. Unknown outcomes suspend conflicting writes.

Acceptance: exact proposal hash, authority, fresh inputs and native locks gate every write; duplicate runs cannot replay an action blindly. At least two supervised relevant game windows complete with no unexplained execution outcome, plus simulated failure exercises. This is an engineering promotion gate, not statistical proof. Only then enable explicitly delegated unlocked-starter changes. Keep trades, protected drops and unresolved reviews outside that authority.

**M7 — Waivers, IR and season planning**

Extend application services with exact add/drop plans, ordered rolling-waiver claims, priority cost, full-roster value, bye coverage and IR eligibility/return consequences. Validate league-specific rules and supported scoring before specialist streaming. Model claim submission, pending state and won/lost/cancelled outcomes separately. Analyze trades without sending offers or messages unless authorized.

Acceptance: tests cover common-drop dependencies, earlier successful claims invalidating later ones, changed ownership, transaction locks, IR activation and incomplete valuations. Supervised platform reconciliation matches the exact transaction plan before expanding standing authority. Preserve numerical advice versus agent overrides and evaluate against chronological prediction-time baselines.

**Release and verification checklist for every milestone**

- State what is implemented, what is only simulated, and what has actual account evidence.
- Run the focused tests during development and `python3 -m unittest discover -v` for release; no live providers in automatic discovery.
- Record scripts/commands, files changed, failures and real cache/API counts for any live diagnostic.
- Commit source, tests, docs and runtime data; keep `.env` and credentials excluded.
- Revalidate task templates and stored schema compatibility before a runtime update. Pause scheduling, wait for in-flight actions to resolve, then pull the tested release and resume with a fresh schedule/state check.
- Declare remaining owner duties explicitly: initial account setup, failed scheduling/browser permissions, login recovery, unresolved availability, unknown application outcomes and non-delegated transactions.

Completion means the awake Mac reliably starts fresh sessions, maintains independently verified future checks, preserves durable decisions and reports what was actually applied. Writing a plan or creating a task is not that acceptance result.
