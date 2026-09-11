# Roster and season services

## Implemented scope

`roster_operations.py` supports supervised rolling-waiver claims, free-agent additions, drops, claim cancellation, IR placement and IR activation.
It stores plans and action transitions in the same transaction database as lineup execution.
Conflicting prepared or uncertain roster and lineup actions block each other.
The service never calls an undocumented account-write API.
The agent performs each authorized action through the visible browser.

`season_strategy.py` compares whole rosters across supplied forecast weeks.
It maximizes legal starter assignments and adds an explicit, uncalibrated bench-replacement term.
Current-week game locks remain fixed. Missing future forecasts remain unknown.
The season calendar checks positional bye coverage without inventing future player projections.
Trade packages use the same comparison service, without sending offers or messages.

Live transaction acceptance is pending. Automatic transactions remain disabled.
The current league has zero IR slots, so legitimate IR placement is unavailable here.
Simulated tests exercise IR capacity and return restrictions for supported configurations.

## Integrated review

```sh
python3 agent_cycle.py --season 2026 --week 1
python3 agent_cycle.py --replay RESULT_FILE
```

The live command collects through central clients and saves an immutable review package.
It includes a lineup proposal, independent validation, forecast pool, roster observation and season calendar.
It compares the top five unowned offensive candidates against unlocked bench drops.
That bounded candidate selection is not an exhaustive search or a proven winning strategy.
Rolling-priority opportunity cost remains a separate strategic judgment.

The replay command uses the original evidence time and makes no external calls.
Replay output cannot authorize platform changes or replace current validation.
Use `--notify` only on a live review when a phone notification is intended.
For scheduler execution, M4 recipes can select `operation: integrated_review` in propose mode.
Daily recipes can select `decision_operation: integrated_review`.
Existing policies must explicitly allow that operation.

## Collect and prepare a plan

```sh
python3 roster_operations.py collect --season 2026 --week 1
python3 roster_operations.py plan --api API_FILE --steps STEPS_FILE --protected PLAYER_IDS --output PLAN_FILE
python3 roster_operations.py register --plan PLAN_FILE --approval APPROVAL_FILE
```

Collection uses central Sleeper context, all league rosters and the documented weekly transactions endpoint.
Private pending claims require an actual browser observation.
The API does not establish whether an unowned player is immediately addable.

Each step supplies a unique `claim_key` and a `kind`:

| Kind | Required action fields |
|---|---|
| `waiver` | `add`, optional `drop`, exact native `deadline` |
| `free_agent` | `add`, optional `drop` |
| `drop` | `drop` |
| `cancel_claim` | exact `platform_claim_id` |
| `ir_place` | owned player ID in `add` |
| `ir_activate` | reserved player ID in `add` |

`depends_on` can identify an earlier ordinal that must lose, cancel or become invalid before this step proceeds.
Without that field, ordered alternative claims can share a drop while earlier claims remain pending.
An earlier successful claim consumes that drop and blocks later preparation.
Do not silently replace the drop with another player.

Approval requires `basis: explicit_owner_transaction_approval`, exact `plan_hash` and the actual `owner_statement`.
Protected drops also require the specific ID in `explicit_protected_drops`.
First move an unlocked starter to the bench through a separate approved lineup plan before dropping it.
Locked players cannot move through these transaction services.

## Native evidence

Use the lineup observation fields from `docs/M5_EXECUTION.md`.
Also record these fields from actual platform observations:

- `reserve`: the ordered IDs in reserve slots.
- `transactions_observed: true` and `pending_claims` from the private claims page.
- `acquisitions_unlocked`, `rules_confirmed` and `ir_roster_legal`.
- `waiver_type: Rolling Waivers` when preparing a waiver claim.
- `candidates`: player IDs mapped to observed `action` and exact `deadline` when applicable.
- `ir_eligible_player_ids` when preparing IR placement.
- `claim_results` for observed completed, lost or cancelled claims.

Each pending claim supplies `claim_id`, `add`, `drop` and one-based `priority`.
Each result supplies its actual claim identity, matching players and status.
A won result also supplies the public `transaction_id`.
Never infer a lost or cancelled result merely because a claim disappeared.

Native and mutable API evidence must be within 60 seconds.
Reconciliation observations must follow dispatch.
The exact user profile retains the central five-minute cache exception.

## Prepare and reconcile one action

```sh
python3 roster_operations.py prepare --plan-id PLAN_ID --ordinal 0 --api API_FILE --native NATIVE_FILE --valuation COMPARISON_FILE
python3 roster_operations.py dispatch --action-id ACTION_ID --token TOKEN
python3 roster_operations.py reconcile --action-id ACTION_ID --api API_FILE --native NATIVE_FILE
```

An acquisition requires a complete, unexpired comparison for the exact add/drop package and current ownership.
The service recomputes that comparison from its hash-bound pool and checks league rules and season.
Specialist streaming stops when projected scoring categories are incomplete.
No FAAB amount is inferred from a raw budget field.

Preparation checks native restrictions, ownership, locks, rolling priority, deadline, roster capacity and claim order.
IR activation cannot overfill the main roster. Create space through a separate approved plan first.
Preparation creates one token with a maximum 30-second lifetime.
Dispatch consumes it before the browser action.
Perform that exact action before its deadline. Do not repeat it after uncertainty.

Reload the relevant native pages after the action.
Collect fresh API evidence and reconcile the saved action.
States distinguish `outcome_unknown`, `pending`, `won`, `lost`, `cancelled`, `applied` and `invalidated`.
Winning requires the exact public transaction and expected native/API ownership.
Submission alone never proves acquisition.
Use at most three read-only observation attempts per reconciliation session.
If uncertainty persists, retain it and notify the owner.

An expired undispatched token can use `retire-unused --action-id ACTION_ID --evidence FILE`.
The evidence requires `basis: explicit_owner_recovery`, the exact action ID and the owner's reason.
A dispatched uncertain action cannot use that recovery path.
Retirement requires a new plan instead of replaying the old action.

## Forecasts and evaluation

```sh
python3 season_strategy.py pool --snapshot SNAPSHOT --output POOL_FILE
python3 season_strategy.py compare --pool POOL_FILE --owned PLAYER_IDS --add PLAYER_IDS --drop PLAYER_IDS --priority-cost 0 --output COMPARISON_FILE
python3 season_strategy.py evaluate --records RECORDS_FILE --output EVALUATION_FILE
```

Repeat `--snapshot` only for distinct, supported forecast weeks with consistent league scope.
Current collection supplies the current week. Future forecasts require independently available, validated inputs.
The system does not convert the current forecast into future weeks.
The default bench coefficient is 0.1 and is not calibrated.
Priority cost uses comparable modeled units. Zero means no estimated cost, not that priority has no value.

Evaluation records require prediction, kickoff, source-observation and outcome-observation times.
The evaluator rejects sources observed after the prediction and predictions made after kickoff.
It reports paired actual differences against the supplied prediction-time baseline.
Small samples and simulated outcomes do not prove a winning edge.
