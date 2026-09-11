# Autonomous Fantasy Football Agent

A personal agent for managing a Sleeper fantasy football team through conversation, repeatable software, and checked actions.
It combines football data with your league's rules to review lineups, compare roster changes, and plan around game deadlines.

The product goal is to run the team for you.
Your role is to observe, ask questions, and intervene when the agent fails, becomes confused, or makes a seriously incorrect decision.
The implementation includes continuing reviews, supervised execution, and standing management permission with acceptance gates.

Phone notifications keep you informed about team changes.
Before games involving your players, a short notice lists the matchup, starters, and bench players.
After each confirmed final result, a brief recap gives the score and your starters' fantasy points.
The agent checks these notices on its recurring wakeup. Live game timing remains subject to acceptance checks.

## The pieces of the system

The Python implementation is grouped by responsibility under `fantasy_agent/`.
See [the code layout](docs/CODE_LAYOUT.md) for directories, commands, and scheduled-run optimizations.

| Component | Role |
|---|---|
| **Sleeper** | The league platform. It holds your roster, league rules, matchups, and transactions. The agent makes authorized changes through its browser interface. |
| **FantasyPros** | A data supplier for player projections, injury information, and news. Projections estimate future performance. |
| **nflverse** | A data supplier for NFL schedules, player information, and historical football data. |
| **Local Python scripts** | Perform repetitive work: collect data, calculate options, check rules, plan deadlines, and save results. |
| **ChatGPT** | The key conversational interface. The agent explains activity, interprets evidence, makes final decisions, and coordinates the scripts and browser. |
| **Scheduled tasks and Pushover** | Start configured reviews and send phone alerts when attention is needed. |

## Runs on an always-on Mac

After setup, open the repository in Codex and say **“Start managing my league.”**
The agent establishes a recurring wakeup, checks your account and league, and identifies the league's current phase.
It gathers missing weekly data through the existing provider clients and prepares the appropriate review.
Draft phases use the saved draft procedures.

Every completed review retains a verified recurring wakeup and a next review time.
Specific obligations, including pending claims, remain saved until the agent records their resolution.
The [manager procedure](docs/LEAGUE_MANAGER.md) describes startup, recovery, and stopping.

The operating model places ChatGPT and the project on an always-on Mac.
The desktop agent session supplies access to local scripts, scheduled tasks, and the Sleeper browser.
The project uses those capabilities through the Codex desktop environment.
The Python scripts and saved records remain on the same machine.

The Mac needs power, internet access, a working desktop session, and a signed-in Sleeper browser.
Scheduled work also needs configured tasks and the required account and machine permissions.
Only one Mac operates the team at a time.
This repository does not supply a hosted cloud service or an independent mobile application.

## Repeatable work belongs in scripts

Most team management repeats the same operations with new data.
The system therefore codifies as much work as possible in saved, executable Python scripts.
Routine operation calls those scripts instead of generating fresh code for each review.

Scripts own data retrieval, identity matching, calculations, rule checks, deadline planning, and saved state.
The same inputs and settings should produce the same calculation results.
Shared provider modules manage access rules, request limits, and reuse of saved data.
Tests use simulated responses to check behavior without changing a real team.

Flexible inference belongs at the interaction layer and the final decision layer.
ChatGPT interprets your questions, explains results, weighs evidence, and chooses among the options that the scripts calculate.
It can account for strategic concerns that the numerical model does not capture.
Those judgments must remain distinct from source facts and computed scores.

This division makes recurring actions stable and reviewable while preserving judgment where football decisions require it.
Saved records let the agent resume work without depending on conversation memory alone.

## What the agent does

**Reviews starting lineups.** It compares legal combinations using available projections and your league's scoring rules.
It preserves players whose games already started and considers later replacement options.

**Evaluates roster changes.** It compares available players with your team and supports plans for additions, drops, and ordered waiver requests.
A waiver request asks the league to award a player after processing competing requests.
The system tracks submission separately from winning or losing that request.

**Plans around the season.** It checks game deadlines and weeks when players have no game.
It identifies gaps in roster coverage and preserves missing forecasts as unknown.
Draft tools also support player selection and retain draft decisions.

**Checks actions and keeps records.** Before a change, it checks ownership, restrictions, fresh evidence, and permission.
After a browser action, it checks the saved Sleeper result against a separate data read.
An uncertain outcome blocks conflicting actions until the agent resolves it.

**Coordinates scheduled reviews.** Configured workflows collect data, prepare decisions, retain results, and arrange subsequent checks.
Phone alerts provide a route for exceptions that need attention.
A saved schedule alone does not establish that a review completed.

## Observe through conversation

You can ask, “What are you doing?”, “Why did you keep that player?”, or “What needs attention?”
The agent answers from the available data and saved decisions.
Asking about a choice does not itself instruct the agent to change strategy.

The intended experience keeps routine work independent of your attendance.
When human help is necessary, an alert should explain the problem, attempted recovery, and the decision or action needed.
You retain control over the agent's operating permission and can stop or correct it.

## Operating boundaries

The code separates analysis from permission to act.
Supervised changes require approval for the exact plan.
Limited delegation permits unlocked starter changes within an expiry and a daily action limit, subject to acceptance checks.
That delegation does not cover additions, drops, waiver requests, or trades.
Standing manager permission separately supports routine roster operations after their live acceptance gate passes.
It checks each final decision, expected account, future scheduling, and daily action limit before dispatch.
Trades and standalone drops require separate permission.

The remaining autonomy gates include live execution acceptance and the quality of final football decisions.
The manager preserves recurring coverage through ordinary review failures and reports missed wakeups after it resumes.
External monitoring of a silent Mac failure is outside scope.
The Mac cannot send an alert while it has no power or internet access.

Football judgment has limits too.
Candidate comparisons cover a bounded set, future forecasts can be incomplete, and some scoring categories lack sufficient data.
Estimated points are not guaranteed results, and the system does not establish a proven winning advantage.

The [autonomy gap plan](docs/AUTONOMY_GAPS.md) describes these boundaries and the evidence needed to extend them.
Dated test results and operating checkpoints belong in [project progress](docs/PROGRESS.md).

## Installation and maintenance

The project uses Python 3.13 on macOS.
Setup connects the desktop agent, local project, provider credentials, Sleeper account, and scheduled workflows.
Normal team management happens through conversation.

For a new installation, create a Python environment from the project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
```

If `.env` does not exist, copy `.env.example` to `.env`.
Add your approved FantasyPros key and both Pushover credentials to that file.
Set `SLEEPER_LEAGUE_ID` in `.env` to your Sleeper league ID.
Set `SLEEPER_USER_ID` to the expected Sleeper account ID.
Neither setting has a default. League operations stop if either setting is missing or empty.
Process environment variables with these names take precedence over `.env`.
Before a team change, the agent observes the signed-in username in Sleeper's account menu.
The code checks that username against the provider profile, configured user ID, and roster owner.
Opening the correct league page alone does not prove the account is correct.
Keep credentials out of chat and Git.
Review `config.json` before using another league.
That file contains the Sleeper username and time zone.
Changing leagues does not transfer saved approvals, roster records, or scheduled workflows to the new league.
Configure scheduled work through the [scheduled operation guide](docs/M4_AUTOMATION.md).

The integrated review command is `agent_cycle.py`, with `--season` and `--week` selecting the review period.
It reads providers through the shared access modules and saves a local report.
It does not change your Sleeper team. The optional `--notify` flag sends a Pushover alert.

To test the software without contacting providers, run:

```sh
python3 -m unittest discover -v
```

The repository tracks project data and decision records for transfer between Macs.
It excludes credentials and the large depth-chart files under `data/nflverse/local/`.
After cloning, use `setup_repo.py --season` with the required season to restore those files through the shared nflverse module.
That command may contact the provider and save current data. It does not reproduce an earlier snapshot.
Provider licensing and personal league information limit how this repository can be shared.

## Further reading

- [Autonomy gap plan](docs/AUTONOMY_GAPS.md): remaining capabilities and acceptance requirements.
- [Lineup changes](docs/M5_EXECUTION.md): approval, confirmation, and limited delegation.
- [Roster changes](docs/M6_ROSTER_OPERATIONS.md): additions, drops, waiver requests, and season planning.
- [Scheduled operation](docs/M4_AUTOMATION.md): configuration, alerts, and recovery.
- [Data access](docs/DATA_ACCESS.md): provider rules and shared access modules.
- [Project progress](docs/PROGRESS.md): dated results and operating checkpoints.
