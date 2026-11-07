# 003 — Models with time-based holdout (machine demand model + floor coin-in forecast)

Goal: `pipeline/model.py` → `site/data/model.json` + `docs/evidence/model_report.md`.
ROOT = `F:\CYH\projects\datathon\challenges\dashboard-royale`. Data (read-only): `ROOT/data-repo/data/`.
Python `ROOT/.venv/Scripts/python.exe` (duckdb 2.x, pandas, numpy, scipy). No sklearn needed.
Use `prepared_daily_view` rows with `active = true AND available_hours > 0` for model A, `property_day` for model B.
NO LEAKAGE: anything fitted for a holdout prediction may use only rows with gaming_date <= the train end.

## Model A — "Which machines are really weak?" multiplicative demand model
Periods: TRAIN = 2025-01-01..2025-04-30, HOLD = 2025-05-01..2025-06-30.
Eligible machines: >= 28 rows in TRAIN and >= 28 rows in HOLD.
Per machine-day row r: ah = available_hours, th = theo_usd, hw = house_win_usd, zone = zone_id, cfg = config_id,
wd = local_weekday. Closure flag: zone == 'Z-B40' and 2025-03-03 <= date <= 2025-04-06 → use zone level "Z-B40#closed"
(the walkway closure was known and had ended before May 1; for HOLD predictions use plain 'Z-B40').

Fit on a set of rows S, shrinkage k:
  E[th_r] = ah_r * Z[zone_r] * C[cfg_r] * W[wd_r] * U[m_r]
  1. Init Z=C=W=1. Repeat 50 iterations (or until max relative change < 1e-9) of IPF updates, U fixed at 1:
     Z[z] = sum_{r in z} th / sum_{r in z} ah*C*W ; then C[c] similarly; then W[w] similarly. Normalise so that the
     ah-weighted mean of C over S is 1 and the ah-weighted mean of W over S is 1 (put the scale into Z).
  2. Machine effect with gamma-Poisson style shrinkage: e_m = sum_{r in m} ah*Z*C*W, t_m = sum_{r in m} th,
     U[m] = (t_m + k) / (e_m + k).   (k in dollars of expected theo; k=0 → no shrinkage, k=1e9 → U≈1)
Prediction of a machine's per-available-hour theo for a target set T_m of its rows:
  pred_rate_m = sum_{r in T_m} ah*Z[zone_r]*C*W*U[m] / sum_{r in T_m} ah   (zone_r from the target rows, so a machine
  that moved is predicted at its new zone; if a zone/config/weekday level is unseen use 1.0 and log it).
Choose k by inner validation: fit on 2025-01-01..2025-02-28, evaluate MAE of pred_rate vs actual theo/ah on
2025-03-01..2025-04-30 (eligible = >=28 rows in each), grid k ∈ {0, 250, 500, 1000, 2000, 5000, 10000, 20000, 50000, 1e9}.
Refit on all TRAIN with the chosen k; predict HOLD.

Baselines (TRAIN only):
- `B_hw_rate`: machine's TRAIN sum hw / sum ah (raw "earnings per open hour")
- `B_theo_rate`: machine's TRAIN sum th / sum ah (luck removed, no location/game adjustment)
- `B_total` (decision only, not a forecast): TRAIN sum hw (the GM's ranking: total house win)
Targets in HOLD: `y_theo` = sum th / sum ah, `y_hw` = sum hw / sum ah.
Metrics over eligible machines, for model and each forecast baseline, against both targets:
MAE, RMSE, Spearman rank correlation. Paired bootstrap over machines (2000 resamples, seed 7) for
MAE(model) - MAE(B_hw_rate) and MAE(model) - MAE(B_theo_rate) against y_theo: mean + 95% CI.
Decision test: for each of B_total, B_hw_rate, B_theo_rate, model: the 10 machines ranked lowest in TRAIN
(model: lowest U[m], i.e. machine effect after location+game — this is "truly weak"; also report model rank by
pred_rate). For each list report: ids, mean HOLD y_theo, mean HOLD machine index (HOLD actual theo / HOLD expected
from the model refit on HOLD rows with k=0 — i.e. U computed on HOLD only), and how many are in the HOLD bottom-10 by
that HOLD index ("hits"), and how many are in the HOLD bottom-10 by raw HOLD total hw.

Full-window fit (for the dashboard): refit on ALL rows Jan–Jun with the chosen k (keep closure level) → output
Z (incl. closed level), C, W, U for every machine with e_m and t_m, plus a per-machine 80% interval for U from the
gamma posterior: shape = t_m + k, rate = e_m + k (scipy.stats.gamma.ppf at 0.1 and 0.9 with scale = 1/rate).
Note theo depends only on coin-in, so this interval reflects demand noise, not slot luck.

## Model B — floor daily coin-in forecast (for staffing / promo decisions)
TRAIN = Jan 1..Apr 30, TEST = May 1..Jun 30, y = property_day.coin_in_usd.
- `B_const`: TRAIN daily mean.
- `M_weekday`: TRAIN mean by local_weekday.
- `M_weekday_event`: M_weekday × event multiplier for events whose `announced_date` <= 2025-04-30 (frozen-forecast
  rule). Multiplier per event_type learned in TRAIN = mean(y / weekday_mean) on that type's TRAIN event dates
  (type with no TRAIN example → citywide types use the pooled citywide TRAIN multiplier; property_promotion uses
  the TRAIN property_promotion multiplier). List which TEST events were usable and which were not (announced later).
Metrics on TEST: MAE ($), MAPE, bias. Also residual (actual - M_weekday) mean per TEST event → "measured lift".
Output daily arrays aligned with the 181 dates: actual, B_const, M_weekday, M_weekday_event (fitted on TRAIN for all dates).

## model.json layout
{"A": {"k_grid": [{k, inner_mae}], "k": chosen, "eligible_n", "metrics": [{method, target, mae, rmse, spearman}],
       "bootstrap": [...], "decision": [{method, ids, mean_hold_theo_rate, mean_hold_index, hits_index, hits_total}],
       "holdout": [{machine_id, zone, cfg, pred_model, b_hw_rate, b_theo_rate, y_theo, y_hw, train_total_hw}],
       "full": {"Z": {...}, "C": {...}, "W": {...}, "U": [{machine_id, U, lo80, hi80, e, t}]}},
 "B": {"metrics": [{method, mae, mape, bias}], "daily": {...}, "events": [...], "usable_events": [...]}}

## Acceptance
1. `ROOT/.venv/Scripts/python.exe ROOT/pipeline/model.py` < 3 min; prints k grid, metrics tables, decision table.
2. Asserts (print PASS): no TRAIN-fitted quantity reads rows after 2025-04-30 (check via max date of the fitting frame);
   eligible_n >= 290; the full-window U list has 310 machines; Model B daily arrays length 181.
3. Report the printed tables verbatim (they are short).
