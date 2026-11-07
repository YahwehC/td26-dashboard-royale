# 001 — Build dashboard data files (core, players, ops)

Goal: one script `pipeline/build_data.py` that reads the parquet data and writes compact JSON files the static
dashboard loads. No analysis here, only faithful extraction + light reshaping.

Folder root: `F:\CYH\projects\datathon\challenges\dashboard-royale` (call it ROOT).
Data: `ROOT/data-repo/data/` (read-only; never write there). Docs: `ROOT/data-repo/reference/DATA_DICTIONARY.md`.
Python: `ROOT/.venv/Scripts/python.exe`. **Use only `duckdb` + Python stdlib** (json, math, datetime). Do NOT
import numpy/pandas (not installed). DuckDB 2.x: use `con.sql(q).fetchall()` (no fetchmany/df).

## Output files (all in `ROOT/site/data/`, create dir). JSON, no NaN (use null), separators=(",",":").

### `core.json`
```
{
 "meta": {"generated_utc": "...", "source": "tamu-datathon-org/dashboard-royale data/ (release 0.9.0-draft)"},
 "dates": ["2025-01-01", ...],            # 181 gaming dates from calendar_day, ascending; index = date idx
 "weekday": ["Wednesday", ...],           # calendar_day.local_weekday, aligned with dates
 "sched_h": [24.0, ...],                  # calendar_day.scheduled_seconds/3600 (2025-03-08 = 23.0)
 "holiday": [null|"name", ...],
 "events": [{"id","name","type","start","end","announced","scope"}],      # events table, dates as ISO strings
 "walkways": [{"id","a","b","len_m","closed_from_utc","closed_to_utc","reason"}],
 "zones": [{"id","name","x","y"}],         # floor_locations node_type='zone'; sorted by id
 "banks": [{"id","zone","x","y"}],         # node_type='bank'; zone = index into zones; sorted by id
 "entrances": [{"id","zone","name","x","y"}], "outlets": [{"id","zone","name","x","y"}],
 "configs": [{"id","theme","rtp","var_mult","hit_p","max_mult","vol"}],  # game_math; rtp/var_mult/hit_p as float
 "machines": [{"id","mfr","theme","lease","install","retire"}],         # machines table, sorted by id
 "md": { columnar arrays, one element per row of prepared_daily_view WHERE active = true, ordered by gaming_date, machine_id }
 "pd": { columnar arrays aligned with "dates", from property_day }
}
```
`md` keys (all arrays of equal length N; N must equal the count of active rows, expected 55,092):
- `d` date idx (int), `m` machine idx (int), `b` bank idx (int), `c` config idx (int)
- `ah` available_hours (round 3), `oh` occupied_hours (round 3), `sh` machine_day.scheduled_seconds/3600 (round 3)
- `ci` coin_in_usd (round 2), `hw` house_win_usd (round 2), `th` theo_usd (round 2)
- `v` = machine_day.sum_bet_squared * game_math.payout_multiplier_variance / 10000 (variance of the day's house win
  in dollars^2; round 0). Join machine_day on (machine_id, gaming_date) and game_math on machine_day.config_id.
- `sp` paid_spins, `hs` machine_day.payout_positive_spins (ints)
- `f` faults_opened (int), `rc` repair_cost_usd (round 2),
  `cost` = lease_cost_usd + service_cost_usd + power_cost_usd + repair_cost_usd (round 2)
- `cc` carded_coin_in_usd (round 2)
Nulls in money columns → 0 only if the row is active and the column is null (report how many if any).

`pd` keys (from property_day, aligned with `dates`): `ci, pay, hw, th, avail_mh, occ_mh, carded_share, pos_cash,
pos_cogs, comp_face, comp_cost, faults, incidents, ent_entries, tot_entries, counter_cov, mach_cost, tech_cost,
contrib, active_machines` (money round 2, ratios round 4).

### `players.json`
Columnar, one element per row of `player_period` (148,893 rows):
```
{"tiers":[...], "ages":[...], "regions":[...], "months":["2025-01",...,"2025-06"],
 "rows": {"p": [player idx], "mo": [month idx], "t": [opening_tier idx], "a": [age_band idx, null→"unknown"],
          "r": [home_region idx], "ci": [tracked_coin_in_usd round 0], "net": [tracked_net_usd round 1],
          "th": [theo_usd round 1], "cc": [comp_cost_usd round 2], "cf": [comp_face_value_usd round 1],
          "vis": [observed_visits], "hrs": [carded_play_hours round 1], "pe": [points_earned], "pr": [points_redeemed],
          "cash": [linked_pos_cash_usd round 1], "cogs": [linked_pos_cogs_usd round 1]}}
```
Player idx: dense index over distinct player_id sorted. Do not ship player_id strings.

### `ops.json`
Fault tickets only (`operations.event_type='fault_repair'`) plus a separate small list of all other operations.
```
{"faults": {"m": [machine idx], "d": [gaming date idx], "hour": [local hour of opened_at_local],
            "wait_h": [(work_started_at_utc - opened_at_utc) hours round 3],
            "fix_h": [(available_at_utc - work_started_at_utc) hours round 3],
            "down_h": [(available_at_utc - opened_at_utc) hours round 3],
            "cost": [direct_cost_cents/100], "shift": [shift name or null], "understaffed": [bool]},
 "other": [{"m","type","opened_local","available_utc","location","cost"}]}
```
Gaming date of a ticket: the calendar_day row whose [gaming_day_start_utc, gaming_day_end_utc) contains opened_at_utc.
`shift`: the `shift_roster` row with role='slot_tech' whose [start_utc, end_utc) contains opened_at_utc (if several,
take the first by start_utc; if none, null). `understaffed` = that roster row's actual_headcount < planned_headcount.

## Acceptance (run all, paste real output in the report)
1. `ROOT/.venv/Scripts/python.exe ROOT/pipeline/build_data.py` finishes < 120 s and prints row counts + file sizes in MB.
2. Add `pipeline/check_build.py` that loads the JSON and asserts:
   - len(md.d) == 55092; all md arrays equal length; len(dates)==181; sched_h[dates.index("2025-03-08")]==23.0
   - sum(md.ci) equals sum(pd.ci) within $1; sum(md.hw) equals sum(pd.hw) within $1; sum(md.th) within $5
   - len(players.rows.p)==148893; sum(net) within $200 of -15,585,460.6; len(faults.m)==1207
   - share of faults with shift != null > 0.95 (print the share and the count by shift and understaffed flag)
   Prints "ALL CHECKS PASSED" on success. Run it and report its output.
