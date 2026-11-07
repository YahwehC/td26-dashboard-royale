# Model report - time-based holdout (003)

Data: `prepared_daily_view` (`active = true AND available_hours > 0`) for Model A, `property_day` for Model B.  TRAIN 2025-01-01..2025-04-30, HOLD/TEST 2025-05-01..2025-06-30.

## Model A - multiplicative machine demand

Model: `E[th] = ah * Z[zone] * C[config] * W[weekday] * U[machine]`, fitted by IPF with gamma-Poisson shrinkage `U=(t+k)/(e+k)`; closure level `Z-B40#closed` in fitting, plain `Z-B40` for HOLD prediction.

### Model A - k grid (inner: fit Jan-Feb, evaluate Mar-Apr)

```
k           inner_mae
----------  ---------
0              0.6355
250            0.6327
500            0.6301
1000           0.6253
2000           0.6172
5000           0.5978
10000          0.5805
20000          0.5795
50000          0.6506
1000000000     0.8429
```

### Model A - HOLD metrics (307 eligible machines)

```
method          target     mae    rmse  spearman     bias
--------------  ------  ------  ------  --------  -------
model           y_theo  1.2647  1.4572    0.9892  +1.2457
model           y_hw    2.7432  4.1271    0.8205  +1.1781
model_noshrink  y_theo  1.2703  1.4855    0.9885  +1.2471
model_noshrink  y_hw    2.7718  4.1823    0.8163  +1.1795
B_hw_rate       y_theo  2.2999  3.3327    0.8953  +1.0298
B_hw_rate       y_hw    3.1664  4.7328    0.7924  +0.9622
B_theo_rate     y_theo  1.0577  1.3240    0.9870  +0.9331
B_theo_rate     y_hw    2.6860  4.0915    0.8156  +0.8655
```

### Model A - HOLD relative metrics (mean |pred/mean(pred) - y/mean(y)|, %)

```
method          target  rel_error_%
--------------  ------  -----------
model           y_theo       3.0760
model           y_hw        14.5672
model_noshrink  y_theo       3.2251
model_noshrink  y_hw        14.7816
B_hw_rate       y_theo      11.6934
B_hw_rate       y_hw        16.9799
B_theo_rate     y_theo       3.7762
B_theo_rate     y_hw        14.7369
```

The May-Jun floor-wide theo level fell, which no TRAIN-only method can know, so the absolute bias column shows a level error for every method. Relative error divides each method's predictions and the actuals by their own mean across machines, removing that common floor level. It isolates how well each method ranks and sizes machines against each other, which is what the replacement decision needs.

### Model A - paired bootstrap (2000 resamples, seed 7), target = y_theo

```
comparison                                             mean_mae_diff  ci95_low  ci95_high
-----------------------------------------------------  -------------  --------  ---------
MAE(model) - MAE(B_hw_rate), target=y_theo                   -1.0373   -1.2952    -0.7835
MAE(model) - MAE(B_theo_rate), target=y_theo                 +0.2073   +0.1619    +0.2529
MAE(model_noshrink) - MAE(B_theo_rate), target=y_theo        +0.2126   +0.1754    +0.2475
```

### Model A - paired bootstrap of relative error (2000 resamples, seed 7), target = y_theo

```
comparison                                                          mean_rel_diff  ci95_low  ci95_high
------------------------------------------------------------------  -------------  --------  ---------
relative_error(model) - relative_error(B_hw_rate), target=y_theo          -8.6212   -9.9879    -7.3219
relative_error(model) - relative_error(B_theo_rate), target=y_theo        -0.7034   -0.9507    -0.4695
```

### Model A - decision test (10 lowest in TRAIN)

```
method           mean_hold_theo_rate  mean_hold_index  hits_index  hits_total
---------------  -------------------  ---------------  ----------  ----------
B_total                      13.1808           1.0096           0           4
B_hw_rate                     9.8946           0.9901           1           4
B_theo_rate                   7.9756           1.0086           0           4
model                        15.9883           0.9001           4           0
model_noshrink               13.6797           0.8884           5           0
model_pred_rate               7.9756           1.0086           0           4
```

### Model A - decision lists

```
method           10 lowest in TRAIN (ids)
---------------  ------------------------------------------------------------------------------
B_total          M-1158, M-1181, M-1238, M-1179, M-3101, M-1265, M-1157, M-1035, M-7487, M-1168
B_hw_rate        M-1158, M-1181, M-1238, M-1179, M-1265, M-1157, M-1035, M-1168, M-1184, M-1041
B_theo_rate      M-1017, M-1035, M-1265, M-1181, M-1238, M-1179, M-1048, M-1063, M-1162, M-1252
model            M-1184, M-1244, M-1286, M-1068, M-1154, M-1145, M-1019, M-1078, M-1126, M-1061
model_noshrink   M-1184, M-1286, M-1154, M-1068, M-1008, M-1145, M-1244, M-1126, M-1162, M-1019
model_pred_rate  M-1017, M-1035, M-1238, M-1265, M-1181, M-1179, M-1063, M-1162, M-1048, M-1252
```

### Model A - full-window U: 10 lowest hi80 (quasi-Poisson, phi = 31.8945)

```
machine_id         U      lo80      hi80
----------  --------  --------  --------
M-1184      0.849209  0.826485  0.872093
M-1244      0.898378  0.878768  0.918100
M-1154      0.905112  0.881674  0.928708
M-1145      0.907380  0.885017  0.929887
M-1008      0.906467  0.880138  0.932997
M-1286      0.911027  0.888083  0.934124
M-1068      0.914534  0.892084  0.937128
M-1019      0.924185  0.902976  0.945523
M-1211      0.925064  0.904385  0.945864
M-1078      0.925600  0.904837  0.946484
```

Quasi-Poisson dispersion phi = 31.894486 estimated from all 55092 full-window machine-day rows with 335 parameters (Z+C+W levels plus machines); shape = (t+k)/phi, rate = (e+k)/phi, 80% interval from gamma ppf(0.1/0.9). This replaces the Poisson interval, which treated $1 of theo as one count and was far too narrow.

### Model A - notes

- Inner-validation eligible machines: 252; chosen k = 20000 (MAE = 0.5795).
- Inner-validation target excludes 1645 rows in the B40 closure window; unseen target levels raise an error (no 1.0 fallback).
- IPF iterations / final max relative change: inner 5000 / 4.15e-09, TRAIN 648 / 9.83e-10, HOLD k=0 341 / 9.63e-10, full 515 / 9.78e-10.
- HOLD unseen target levels: none.
- HOLD index = HOLD actual theo / HOLD expected theo from a k=0 refit on HOLD rows (location/game/weekday adjusted, i.e. U computed on HOLD only).
- `model` uses the chosen k, `model_noshrink` uses the same fit with k=0; both HOLD forecasts use the TRAIN-fitted location/game/weekday effects.
- `model_pred_rate` ranks the same fitted model by predicted HOLD rate; the `model` row ranks by U at the chosen k and `model_noshrink` by U at k=0 (location/game adjusted).
- The HOLD k=0 refit is evaluation-only (used for the decision index); no HOLD forecast uses HOLD outcomes.


## Model B - floor daily coin-in

### Model B - TEST metrics (May 1 - Jun 30, 61 days)

```
method                 mae     mape       bias
---------------  ---------  -------  ---------
B_const          218258.10  16.4251  +28936.54
M_weekday         68698.55   5.0207  +39285.62
M_weekday_event   63990.26   4.7644  +44727.33
```

MAPE is in percent; bias = mean(predicted - actual).

### Model B - TEST events and measured lift

```
event_id     type                announced   usable    mult  measured_lift
-----------  ------------------  ----------  ------  ------  -------------
EV-EDC25     festival            2024-05-20  yes     1.0672     +179083.76
EV-P-LOCALS  property_promotion  2025-05-26  no      1.1308      +16001.55
```

- EV-EDC25: usable: type unseen in TRAIN, pooled citywide multiplier
- EV-P-LOCALS: announced 2025-05-26 > 2025-04-30 (not usable)

### Model B - notes

- TRAIN daily mean (B_const) = $1,384,919.05.
- Type multipliers learned in TRAIN: convention=1.0163, property_promotion=1.1308, sports_viewing=1.1617.
- Pooled citywide TRAIN multiplier = 1.0672.
- Usable TEST events: EV-EDC25.
- Daily arrays are the TRAIN-fitted forecasts for all 181 dates; M_weekday_event applies only events announced by 2025-04-30.


## Checks

```
PASS: no TRAIN-fitted quantity reads rows after 2025-04-30: inner fit max 2025-02-28, TRAIN fit max 2025-04-30, HOLD prediction starts 2025-05-01
PASS: eligible_n = 307 (>= 290)
PASS: full-window U list has 310 machines (== 310)
PASS: Model B daily arrays length 181 (== 181)
```
