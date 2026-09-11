# Weekly rules verification

Live central Sleeper reads completed September 9, 2026 at 00:20 Eastern
(04:20 UTC). Command: `python3 league_rules.py`. Private raw evidence and
per-request metadata: `data/league_rules/latest.json`.

Three successful network requests, zero cache hits. An earlier restricted attempt
returned HTTP 503. Network-permitted execution succeeded. No account changes or
FantasyPros/nflverse requests. Provider publication timestamps remain unknown.

## Confirmed API observations

- 14 teams. Nine starters: QB, RB, RB, WR, WR, TE, FLEX, K, DEF. Five bench slots.
- Full PPR, passing TD 4, passing interception -1, passing yard 0.04,
  rushing/receiving yard 0.1, rushing/receiving TD 6, fumble lost -2.
  Complete specialist and other scoring coefficients are saved in raw evidence.
- `reserve_slots=0`, `taxi_slots=0`, `max_subs=0`: no IR/taxi slots or automatic
  substitutions configured.
- Our roster `waiver_position=2`, `waiver_budget_used=0`.
- Raw settings: `waiver_type=0`, `waiver_budget=100`, `waiver_bid_min=0`,
  `waiver_day_of_week=2`, `waiver_clear_days=2`, `daily_waivers=0`,
  `daily_waivers_hour=0`, `daily_waivers_days=5461`, `bench_lock=0`,
  `disable_adds=0`.

Do not infer that FAAB is enabled from the budget field. Do not translate enum
codes into waiver type or a processing deadline without verified labels.

## Official platform behavior

Sleeper explains that started players remain locked in their starting positions.
A special processed-waiver drop can leave a player off-roster while their points
still count. Bench Lock affects these drops. A roster drop is not permission to
replace a locked starter's score.
Source: https://support.sleeper.com/en/articles/3473234-why-was-someone-able-to-drop-their-starter-after-they-have-played

After-game waivers, dropped-player waiting periods and custom daily waivers are
separate settings. A configured two-day dropped-player period means 48 hours.
Free-agent additions held less than 24 hours have a documented exception on drop.
These general definitions do not establish our league's exact processing time.
Source: https://support.sleeper.com/en/articles/3978868-waivers-for-regular-season-playoffs

## User screenshot confirmation

User supplied the website's League Settings panel on September 9, 2026.
The observed route was the LEAGUE tab. The top gear menu did not contain rules.
The screenshot confirms:

- Waiver Type: Rolling Waivers. FAAB is not the displayed waiver system. The raw
  budget field must not drive bid recommendations.
- Clear Waivers: Wednesday (3 AM EDT). This is the displayed schedule, not proof
  of an exact processing completion time. Preserve America/New_York timezone
  handling and recheck after daylight-saving changes.
- Waiver Time: 2 Days — Players stay on the waivers for 2 days.
- 14 teams. Six playoff teams starting week 15. Trade deadline week 11.
  Zero injured reserve slots. Draft pick trading allowed.

## Remaining settings not shown

September 11 integration: the saved screenshot confirmation now has a machine-readable record at
`data/automation/rules/1400628784381612032.json`.
The deadline collector matches its three confirmed raw settings against each collected league response.
It preserves the September 9 confirmation date and reports remaining exceptions separately.
Wednesday 3 AM EDT is the confirmed displayed schedule. The record does not invent a separate claim cutoff or guarantee processing completion.

Scoring confirmation: the user's complete pasted scoring settings on September 9,
2026 match every nonzero coefficient in the saved API report, including kicking,
team defense, special teams defense/player events and miscellaneous scoring.
The API additionally explicitly records zero for points allowed 21–27 and for
fumbles without a lost-fumble event. Neither is a discrepancy with the pasted
nonzero rules. Scoring coefficients are confirmed. Projection coverage remains
separate: missing projected categories, especially field-goal distance bands and
defense points-allowed bands, must not be silently filled with zero. Keep team
and individual special-teams stat categories distinct when mapping inputs.

The screenshot does not show these controls:

- Custom Daily Waivers.
- Bench Lock / preventing bench drops after game starts.
- Lock all free agent and waiver moves.

Their raw API values are recorded above.  UI labels remain unverified. If these
controls are unavailable on the website, the user can confirm them through the
mobile app or commissioner. These gaps do not block analysis of our owned lineup.
They matter before relying on particular acquisition/drop behavior.

For any actual acquisition, inspect that player's Add/Claim status and displayed
waiver-clear deadline in Sleeper. Unowned does not prove immediately addable.
Pending private claims/bids have no documented public endpoint to rely on.

No weekly optimizer, deadline scheduler or lineup submission was implemented by
this verification. The reusable rules collector has two mocked tests. The full
167-test suite passed. Future waiver analysis should use the screenshot-confirmed
rolling system and Wednesday 3 AM EDT display, plus each candidate's own deadline.
