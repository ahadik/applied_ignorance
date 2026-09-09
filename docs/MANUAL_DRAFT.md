# Terminal fallback for tonight

Confirmed actual room: https://sleeper.com/draft/nfl/1400628785413394432 .
At 7:06 p.m. Eastern September 8, the default command successfully read this room
and calculated using the approved frozen board: pre_draft, seat 13, zero picks,
next pick 13. The snapshot and live roster-format validation passed. A preview
before the draft starts is expected; rerun when on the clock. This was a read-only
preflight, not a guarantee of future provider availability. The user has finished
rehearsals; do not initiate another mock.

Stop the agent's browser actions before taking over manually. This command does
not stop an agent, disable Sleeper autopick, or submit a selection.

From any terminal, run:

```sh
python3 "/Users/alex/Projects/Fantasy Football/draft_now.py"
```

It prints one recommended player and up to two alternatives. `DRAFT NOW` means
the fresh API observation placed you on the clock. `PREVIEW ONLY` means you must
wait and rerun when your turn arrives. Always check the room and availability
before clicking; API observations and browser selections are not atomic.

For just the name on standard output:

```sh
python3 "/Users/alex/Projects/Fantasy Football/draft_now.py" --name-only
```

That mode prints no name and exits 2 when it is not your turn. Failures exit 1
without substituting old advice. Progress/errors go to standard error.

The default always reads tonight's real draft; it does not detect the browser tab.
For a separately verified mock with matching roster settings, supply its URL's ID:

```sh
python3 "/Users/alex/Projects/Fantasy Football/draft_now.py" --mock 1403185547618349056
```

Every invocation displays the target room URL on standard error. Check it against
the room you are using. `--mock` rejects real-league drafts and retains roster,
identity, snapshot and freshness validation. It does not start or resume a mock.

The command uses the actual draft ID 1400628785413394432 and ahadik's user ID.
It reads metadata, traded picks and selections through
`draft_data.read_live_draft` → `sleeper.get_sleeper`, with no mutable-data cache
or retries. Only Sleeper's normal local request ledger/cooldown may change.
It calculates using the pinned board and shared A/B engine, candidate validation
and roster filters. FantasyPros and nflverse are not contacted. The frozen
snapshot's approval/hash/expiry checks remain enforced, and a total read plus
calculation over 20 seconds fails closed. No browser, active chat, or watcher is
required. Python and a working Sleeper connection are required.

Rerun after each new pick. Backups are alternatives for the current pick, not
instructions for future rounds. The command neither reads stale recommendations
nor overwrites the live controller's files. If a previous browser submission is
uncertain, inspect the actual roster before selecting again. Check ongoing
autopick after any timeout. This fallback remains available during conversation
compaction, but cannot provide fresh advice during a Sleeper API outage.
