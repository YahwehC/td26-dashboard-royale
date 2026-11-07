# Model report - time-based holdout (003)

Data: `prepared_daily_view` (`active = true AND available_hours > 0`) for Model A, `property_day` for Model B.  TRAIN 2025-01-01..2025-04-30, HOLD/TEST 2025-05-01..2025-06-30.

## Model A - multiplicative machine demand

Model: `E[th] = ah * Z[zone] * C[config] * W[weekday] * U[machine]`, fitted by IPF with gamma-Poisson shrinkage `U=(t+k)/(e+k)`; closure level `Z-B40#closed` in fitting, plain `Z-B40` for HOLD prediction.

### Model A - k grid (inner: fit Jan-Feb, evaluate Mar-Apr)

```
k           inner_mae
----------  ---------
0              1.2332
250            1.2309
500            1.2288
1000           1.2249
2000           1.2183
5000           1.2024
10000          1.1883
20000          1.1879
50000          1.2482
1000000000     1.4103
```
### Model A - HOLD metrics (307 eligible machines)

```
method       target     mae    rmse  spearman
-----------  ------  ------  ------  --------
model        y_theo  1.2652  1.4579    0.9891
model        y_hw    2.7438  4.1274    0.8203
B_hw_rate    y_theo  2.2999  3.3327    0.8953
B_hw_rate    y_hw    3.1664  4.7328    0.7924
B_theo_rate  y_theo  1.0577  1.3240    0.9870
B_theo_rate  y_hw    2.6860  4.0915    0.8156
```
### Model A - paired bootstrap (2000 resamples, seed 7), target = y_theo

```
comparison                                    mean_mae_diff  ci95_low  ci95_high
--------------------------------------------  -------------  --------  ---------
MAE(model) - MAE(B_hw_rate), target=y_theo          -1.0368   -1.2949    -0.7823
MAE(model) - MAE(B_theo_rate), target=y_theo        +0.2078   +0.1625    +0.2534
```
### Model A - decision test (10 lowest in TRAIN)

```
method           mean_hold_theo_rate  mean_hold_index  hits_index  hits_total
---------------  -------------------  ---------------  ----------  ----------
B_total                      13.1808           1.0096           0           4
B_hw_rate                     9.8946           0.9901           1           4
B_theo_rate                   7.9756           1.0086           0           4
model                        15.9883           0.9001           4           0
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
model_pred_rate  M-1017, M-1035, M-1238, M-1265, M-1181, M-1179, M-1063, M-1162, M-1048, M-1252
```
### Model A - notes

- Inner-validation eligible machines: 299; chosen k = 20000 (MAE = 1.1879).
- Full-window fit: 50 IPF iterations, max relative change 6.34e-04.
- Inner-validation unseen target levels (fallback 1.0): zone=Z-B40#closed (1645 rows)
- HOLD unseen target levels: none.
- HOLD index = HOLD actual theo / HOLD expected theo from a k=0 refit on HOLD rows (location/game/weekday adjusted, i.e. U computed on HOLD only).

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
