# Implementation milestones for Mac-based season management

September 10, 2026. Implementation plan for [MAC_AUTOMATION_DESIGN.md](MAC_AUTOMATION_DESIGN.md). No new automation modules, schedules, Git commits or deployments are delivered by this document. Build and test every component on this Mac first. Move the tested system to the second Mac only after local acceptance.

Milestone order: M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7. Complete M0–M6 on this Mac. M7 moves the tested system to the second Mac. Offline M1/M2 work may proceed while account capability verification awaits owner access. Live orchestration remains gated by M0.

**M0 — Prove the ChatGPT runtime boundary**

The [probe command and runbook](M0_PROBE.md) now exist.
The IDE session cannot access the required scheduling controls or browser.
Test these capabilities in the ChatGPT app with its in-app browser.
M0 capability evaluation is complete with a limited operating mode. See [the exit report](M0_EXIT_REPORT.md).
Full dynamic scheduling remains unaccepted because natural one-time expiration was not verified.
Use the documented fallback while implementing M1 and offline M2.

Deliver a reusable harmless probe command and capability report schema. The command writes host/time/project/release evidence locally, contains no credentials, and has no Sleeper writes. In an interactive session, set up an explicitly identified disposable scheduled task using supported controls. Observe an actual fresh scheduled run rather than pressing Run now alone.

Probe these functions:

- Select the project and interpreter.
- Use file permissions without supervision.
- Read data through the central clients.
- Access the browser.
- Inspect Sleeper without changes.

Separately test these task functions:

- Read the complete task inventory.
- Create a task.
- Change the task time and prompt.
- Disable or cancel a task.
- Run a task once.
- Report the time zone.
- Measure the delay before a task starts.

Remove disposable tasks. Verify their removal. Test behavior after you close a chat. Test behavior after you restart the app. Record app/account/machine-specific limits. Record scheduling limits without guesses.

Acceptance: capability matrix has evidence for every feature the chosen mode uses. Browser inspection makes no lineup changes. Failed or missing features select an explicit fallback mode from the design. Exit deliverable states whether dynamic scheduling plus browser execution is feasible. It must not merely report that an interactive tool worked. Repeat key probes on the second Mac at M7.

**M1 — Durable contracts and run records**

Implementation: [local contracts, run records and recovery commands](M1_AUTOMATION.md) now exist.
New installations start disabled. M1 does not execute external operations.
Local acceptance passed on September 11, 2026. All 228 tests passed, including 20 M1 tests.

Implement `automation_store.py`, schemas, example policy and `automation.py init/status`. Add run/event records, mode gates, atomic claims, proposal/action references and schema migration versioning. Default new automation to disabled until setup is verified. Assume only one Mac operates at a time. Reuse `storage.save_atomic` for exports and existing shared provider stores unchanged.

Define typed errors for stale revision, unknown schema, missing state and incomplete prior execution. Build a compact context packet with references to relevant weekly records. Do not put the season's conversation history into prompts.

Acceptance: tests under `tests/` cover duplicate claims, crash recovery, expired leases, atomic persistence, unknown schemas and preservation of append-only history. Explicit clock injection makes tests reproducible. Existing weekly/draft tests remain green.

**M2 — Deterministic deadline planning**

Implementation and local acceptance are complete. See [the M2 guide](M2_AUTOMATION.md).
All 251 tests passed on September 11, 2026, including 23 M2 tests.
Live ownership and fixture collection passed. The replay reports missing verified waiver/review timing without inventing coverage.
Subsequent correction incorporated the owner's September 9 waiver confirmation. All 253 tests now pass.
Basic weekly waiver timing is known. Player-specific exceptions and agent-review coverage remain separate operational checks.
Automation remains disabled. No scheduler operation occurred.

Implement `automation_deadlines.py` and `automation_plan.py`. Proposed CLI: `automation.py collect-deadlines` uses documented central clients.  `automation.py plan --observations PATH --policy PATH --as-of UTC` is offline and writes an immutable canonical plan. Use exact season/week, verified fixtures, relevant owned alternatives and league waiver settings. Explain collection effects and actual cache/network evidence in command output.

Generate desired checks, rendered prompt payloads, stable IDs/revisions, capacity findings and coverage intervals. Preserve plans and source timestamps. Support midnight/week boundaries, daylight saving, postponements, earlier backup locks, deadline changes, overdue work and incomplete inputs. Never start another draft or mock.

Acceptance: hand-calculated fixture cases match exact UTC times. Same inputs/policy/clock yield byte-stable canonical specs. Changing a kickoff changes the revision/time while preserving logical identity. Missing data cannot silently erase coverage. Expired actions do not become future executable work. All tests use synthetic provider fixtures under `tests/`.

**M3 — Scheduler reconciliation with verified read-back**

Implementation and local acceptance passed on September 11, 2026. See [the M3 runbook](M3_AUTOMATION.md).
All 274 tests passed, including 21 M3 tests.
The paused live probe passed create, update and deletion verification. Final local inventory was empty.
Production deadline scheduling retains M0's manual fallback. Automatic exact one-time reconciliation remains unavailable.

Implement `automation_reconcile.py` and proposed commands `schedule-import`, `schedule-diff`, `schedule-record`, `schedule-verify`. These commands validate saved control results. They do not independently call a private ChatGPT API. Render exact allowlisted scheduling operations for the agent to apply using the M0-verified interface.

Add protected daily-anchor handling, scoped ownership markers, fresh complete inventory requirements, returned task IDs, operation receipts and unknown-outcome recovery. Serialize scheduling changes. Handle duplicate tasks, task caps, malformed timestamps, stale observations and a timeout after successful creation. Only verified observed task state counts as coverage.

Acceptance: fake inventories cover missing, matching, changed, duplicate and unrelated tasks. Repeating reconciliation after success yields no changes. Incomplete inventory cannot trigger mass creation/deletion. A harmless live cycle creates, verifies, updates and removes a test check without touching unrelated tasks. If M0 cannot support inventory/read-back, ship manual schedule instructions and label automatic reconciliation unavailable.

**M4 — Bounded daily and deadline workflows**

M4 local acceptance passed on September 11, 2026, in bounded recurring-dispatch mode.
See [M4_AUTOMATION.md](M4_AUTOMATION.md) for the current boundary and recovery procedures.
The owner confirmed the Pushover phone test on September 11, 2026.
Two actual scheduled harmless cycles saved receipts and verified future configuration coverage.
The daily-planner integration passed with simulated provider evidence. All 299 offline tests passed.
The test dispatcher was deleted, cleanup was verified and automation is disabled again.

Notification choice: Pushover, selected by the owner. Add a central provider client
and reusable CLI with credentials in `.env`, bounded retries, incident
deduplication and saved send results. Test with simulated responses, then verify
an actual alert on the owner's phone during setup. Browser failures must not
prevent the notification command from running. An offline Mac still requires a
separate external heartbeat monitor.  Pushover integration alone does not detect it.

Implement `automation_run.py`, `automation_health.py` and versioned daily/check prompt templates. Proposed commands: `begin`, `context`, `finish`, `health` and `pause/resume`. Daily work ensures coverage through the next planner plus overlap, then prepares football decisions. Deadline runs claim their check and use the existing weekly analysis, proposal-history and validator services.

First mode is observe/propose. Separate desired, scheduled, running and completed status. Store provider acquisition counts and failure causes. Add a runbook with exact recovery for missing login, quota cooldown, missed planner, changed ownership and incomplete execution. Integrate an owner-selected notification route only after authorization and a delivery test. No unsolicited messages to other managers.

Acceptance: scheduled harmless end-to-end runs save receipts and verified future coverage across two planning cycles. Restart after claiming work and after scheduler creation. Prove recovery produces neither blind duplicates nor false success. Verify a superseded prompt exits before external work. Daily and deadline runs cannot simultaneously claim a mutating workflow.

**M5 — Verified lineup execution and limited autonomy on this Mac**

Resolve the existing browser/API starter disagreement first. Add durable weekly execution transitions and bounded reconciliation, authority checks and a pre-action native-state record. Reuse the independent validator. Add authoritative availability evidence and a narrowly scoped, auditable review-resolution contract where required. This is necessary because current near-kickoff validation cannot issue a clean pass from the existing feeds alone.

Begin with owner-supervised legitimate lineup operations. Record each visible change and full reload/API read-back. Exercise disconnect-after-click and stale-state recovery with simulated execution evidence. Do not manufacture unnecessary real roster changes to test failures. Unknown outcomes suspend conflicting writes.

Acceptance: exact proposal hash, authority, fresh inputs and native locks gate every write. Duplicate runs cannot replay an action blindly. At least two supervised relevant game windows complete with no unexplained execution outcome, plus simulated failure exercises. This is an engineering promotion gate, not statistical proof. Only then enable explicitly delegated unlocked-starter changes. Keep trades, protected drops and unresolved reviews outside that authority.

**M6 — Waivers, IR and season planning on this Mac**

Extend application services with exact add/drop plans, ordered rolling-waiver claims, priority cost, full-roster value, bye coverage and IR eligibility/return consequences. Validate league-specific rules and supported scoring before specialist streaming. Model claim submission, pending state and won/lost/cancelled outcomes separately. Analyze trades without sending offers or messages unless authorized.

Acceptance: tests cover common-drop dependencies, earlier successful claims invalidating later ones, changed ownership, transaction locks, IR activation and incomplete valuations. Supervised platform reconciliation matches the exact transaction plan before expanding standing authority. Preserve numerical advice versus agent overrides and evaluate against chronological prediction-time baselines.

**M7 — Move the tested system to the second Mac**

Start this milestone only after M0–M6 pass on this Mac. Include a live Pushover delivery test and scheduled browser runs in local acceptance.

Commit source, tests, documentation and tracked data to the existing Git repository. Keep the large depth-chart directory ignored. Exclude `.env` and credentials. Run `python3 -m unittest discover -v` before release, then push the completed checkpoint when requested. No clean-history export, separate data-transfer tooling or host-isolation system is required.

Clone or pull the repository on the second Mac. Install the tested Python environment. Configure `.env`. Sign in to ChatGPT. Sign in to Sleeper. Run `python3 setup_repo.py --season 2026` to restore the ignored depth data. Repeat M0 scheduling/browser probes there and configure tasks for that checkout. Begin in propose mode.

Only one Mac runs at a time. Finish work and commit/push data before switching. Pull before starting on the other Mac. This carries provider ledgers, lock history and pending-action evidence with the code. Preserve timestamps and revalidate current league state before acting. Configure task definitions and permissions on the new Mac separately.

Acceptance: the second Mac has the same committed code/data, tests pass, credentials remain excluded, and an actual scheduled run accesses the correct checkout and browser. Document these steps in a short `docs/RUNTIME_MAC_RUNBOOK.md`.

**Release and verification checklist for every milestone**

- State what is implemented, what is only simulated, and what has actual account evidence.
- Run the focused tests during development and `python3 -m unittest discover -v` for release. No live providers in automatic discovery.
- Record scripts/commands, files changed, failures and real cache/API counts for any live diagnostic.
- Commit source, tests, docs and runtime data. Keep `.env` and credentials excluded.
- Revalidate task templates and stored schema compatibility before a runtime update. Pause scheduling, wait for in-flight actions to resolve, then pull the tested release and resume with a fresh schedule/state check.
- Declare remaining owner duties explicitly: initial account setup, failed scheduling/browser permissions, login recovery, unresolved availability, unknown application outcomes and non-delegated transactions.

Local acceptance requires fresh sessions, verified future checks, saved decisions and accurate reports of applied changes. The second Mac must repeat these checks after transfer. Writing a plan or creating a task is not that acceptance result.
