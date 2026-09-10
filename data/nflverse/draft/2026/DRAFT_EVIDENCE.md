# Historical evidence for tonight's draft

Analysis time: 2026-09-08T22:35:08.145592+00:00
Historical seasons: 2024, 2025

Player records: 960; current depth roles: 607; teams: 32.
Unmatched historical snap identities: 6; unmatched current depth rows: 1.
Stale depth teams: none.

| Season | Regular-season games in stats | Teams | Weeks |
|---|---:|---:|---|
| 2024 | 272 | 32 | 1–18 |
| 2025 | 272 | 32 | 1–18 |

Historical records excluded for missing identity/game ID: 36.

## Collected sources

- players : asset published 2026-09-08T12:28:24Z; https://github.com/nflverse/nflverse-data/releases/download/players/players.csv
- depth_charts 2026: asset published 2026-09-08T11:57:06Z; https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2026.csv
- player_stats 2024: asset published 2026-08-13T16:49:11Z; https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2024.csv
- snap_counts 2024: asset published 2025-10-06T06:51:21Z; https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_2024.csv
- player_stats 2025: asset published 2026-08-13T16:51:22Z; https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv
- snap_counts 2025: asset published 2026-02-09T13:39:51Z; https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_2025.csv

## Interpretation limits

- Historical production is not a current-season projection.
- Per-game means use recorded rows, not assumed games played; absent/missing values are not zero.
- Late usage uses the last four observed league regular-season weeks, not a player's last four appearances.
- Snap percentages are unweighted means across recorded games, not season-wide snap shares.
- Depth rank is within a listed formation/slot; it does not guarantee workload or injury replacement.
- PPR points use the source scoring, not an exact recomputation of our league settings.
- Current-team changes and missing history require review, especially rookies.
- Player matching uses GSIS/PFR/ESPN IDs; Sleeper/FantasyPros integration remains separate.
- Latest corrected historical files are not prediction-time snapshots suitable for leakage-free backtests.

Detailed per-player totals, observed-game averages, late usage, depth roles and quarantined matches are in `draft_evidence.json`. This report is evidence, not a draft ranking.
