# 002 — Evidence tables: downtime, substitution, staffing, walkway closure, comp change

Goal: `pipeline/analysis.py` computes the evidence behind our claims and writes `site/data/analysis.json`
plus a human-readable `docs/evidence/analysis_report.md` (tables of the numbers below).

ROOT = `F:\CYH\projects\datathon\challenges\dashboard-royale`. Data (read-only): `ROOT/data-repo/data/`.
Column docs: `ROOT/data-repo/reference/DATA_DICTIONARY.md`. Python: `ROOT/.venv/Scripts/python.exe`
(duckdb 2.x, pandas, numpy available; DuckDB 2.x: use `.fetchall()` / `.df()`, no `fetchmany`).
Money rules: `_cents` = integer cents, `_usd` = dollars. Always ratio of sums. Exclude inactive machine rows.
Theo for an hour of `machine_hour` = coin_in_cents * (1 - configured_rtp) / 100, with config_id taken from
`machine_day` for the same (machine_id, gaming_date) and rtp from `game_math`.

## Sections (each → a key in analysis.json; arrays aligned to the lists given)

### A. `downtime`
Per active machine-hour (`machine_hour.active`): down_s = max(0, 3600 - available_seconds).
Expected theo rate r(machine, local_hour) = sum theo / sum(available_seconds/3600) over all active hours of that
machine at that local_hour (whole window). lost_theo = down_s/3600 * r. (State in report: upper bound, assumes no
substitution to other machines.)
Output:
- `by_date`: arrays aligned to the 181 gaming dates: `down_h`, `lost_theo`
- `by_hour`: 24 local hours: `down_h`, `lost_theo`
- `by_mfr_month`: list of {mfr, month, down_h, lost_theo, faults (fault_repair tickets opened that month), repair_cost}
- `by_machine`: list of {machine_id, down_h, lost_theo, faults} for all machines, sorted by lost_theo desc
- `total`: {down_h, lost_theo, theo_total, share}

### B. `substitution` (competing explanation: do players just move to a neighbour when a machine is down?)
Bank of a machine-hour = bank of its location (floor_locations: slot → parent bank). For each (bank, hour_start_utc):
k = number of machines in the bank with down_s >= 1800 that hour. For machines NOT down in that hour, occupancy =
sum occupied_seconds / sum available_seconds. Compare mean occupancy of the other machines in bank-hours with k>=1
vs bank-hours with k=0 **matched on same bank, local_hour and weekday** (compute difference within each
(bank, local_hour, weekday) cell that has both, then weight by number of k>=1 bank-hours).
Output {treated_bank_hours, weighted_mean_diff_occ, baseline_occ, ratio = diff/baseline, and a 95% CI by bootstrap over
cells (1000 resamples, seed 42)}.

### C. `staffing` (natural experiment: day-shift slot techs were short in Apr–May)
Use `shift_roster` role='slot_tech'. For each fault_repair ticket: shift = roster row whose [start_utc,end_utc)
contains opened_at_utc; understaffed = actual_headcount < planned_headcount; wait_h = work_started - opened (hours).
Output:
- `by_shift`: list {shift, understaffed, n, mean_wait_h, median_wait_h, mean_actual_headcount}
- `by_hour`: 24 local hours: n faults, mean wait_h
- `roster_month`: list {month, shift, planned_mean, actual_mean}
- Regression (statsmodels OLS, HC1 SE): wait_h ~ C(shift) + actual_headcount_per_open_fault... keep it simple:
  wait_h ~ C(shift) + actual_headcount. Report coef, SE, p, n.

### D. `closure` (walkway W-ENT-B40 closed 2025-03-03 14:00 UTC → 2025-04-07 13:00 UTC)
From prepared_daily_view (active rows): per ISO week (week starting Monday) and per gaming date:
B40 = zone 'Z-B40'; rest = all other zones. rate = sum theo_usd / sum available_hours.
- `weekly`: list {week_start, b40_rate, rest_rate, ratio}
- `daily_ratio`: array aligned to dates
- pre = 2025-01-01..2025-03-02, closure = 2025-03-03..2025-04-06, post = 2025-04-07..2025-06-30:
  `periods`: {pre_ratio, closure_ratio, post_ratio} (ratio of sums within the period)
- `lost_theo_closure` = sum over closure dates of (rest_rate_d * pre_ratio * B40 available_hours_d - B40 theo_d).
- Zone traffic: from zone_traffic_hourly, use only rows with counter_status in ('ok','partial') and coverage_minutes>0;
  coverage-adjusted entries = entries_count * 60 / coverage_minutes. Per zone per ISO week: sum adjusted entries /
  number of sensor-hours used * 24 (= mean daily entries per sensor). Output `traffic_weekly`: list {zone_id, week_start,
  entries_per_sensor_day}. Gaming date for an hour = calendar_day interval containing hour_start_utc.

### E. `comp` (redemption point price changed around 2025-05-01)
From loyalty_ledger (event_type='redeem'), gaming date via calendar_day interval on event_at_utc; keep dates in window.
- `daily`: arrays aligned to dates: points_redeemed (positive), face_usd, cost_usd (economic_cost_cents/100),
  n_redemptions, pts_per_face_usd = points_redeemed / face_usd
- detect the change date: first date d where the 7-day mean of pts_per_face_usd after d is < 0.7 × 7-day mean before d.
  Output `change_date`, `pts_per_usd_before`, `pts_per_usd_after` (ratio of sums Jan 1..change-1 / change..Jun 30).
- `monthly` from player_period: {month, players, tracked_coin_in, theo, comp_cost, comp_face, reinvestment = comp_cost/theo,
  redemptions = comps_redeemed, points_earned, points_redeemed}
- Difference-in-differences, carded vs uncarded coin-in (prepared_daily_view: carded = carded_coin_in_usd,
  uncarded = coin_in_usd - carded_coin_in_usd; daily floor sums): pre = 2025-03-01..2025-04-30, post = 2025-05-01..06-30.
  DiD = ln(carded_post/carded_pre) - ln(uncarded_post/uncarded_pre) using daily means. Bootstrap 95% CI by resampling
  days within each period (1000, seed 42). Repeat for "placebo": pre=Jan 1–Feb 28 vs post=Mar 1–Apr 30. Output both.
- Same DiD on tracked theo per active player-month (player_period, Mar–Apr vs May–Jun) is NOT possible without a
  control, so instead output by opening_tier: {tier, theo_pre_per_player_month, theo_post_per_player_month,
  comp_cost_pre, comp_cost_post} for pre=Mar–Apr, post=May–Jun.

### F. `events`
For each row of `events`: mean daily property coin-in during the event dates vs mean of the same weekdays in the
4 weeks before the event start (excluding other event dates). Output {id, name, type, start, end, lift_pct,
lift_usd_per_day, n_days}.

## Acceptance
1. `ROOT/.venv/Scripts/python.exe ROOT/pipeline/analysis.py` runs < 5 min, writes both files, prints key numbers.
2. Sanity (assert in script, print PASS): downtime.total.down_h between 4,800 and 5,300; closure.periods.closure_ratio
   < pre_ratio; comp.change_date == "2025-05-01"; sum of downtime.by_date.down_h == total.down_h within 1 h;
   len(by_date arrays) == 181.
Report the printed key numbers (all section summaries) in your final report.
