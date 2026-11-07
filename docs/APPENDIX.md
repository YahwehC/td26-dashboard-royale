# Claims & Evidence appendix — Dashboard Royale (The Gilded Ace)

The casino and its guests are fictional (synthetic data, release 0.9.0-draft); only `4_context/real_sources` is real public data.
Every number below is produced by the scripts in `pipeline/` (see the README for the run order). Evidence reports with full tables:
`docs/evidence/analysis_report.md`, `docs/evidence/model_report.md`, `docs/evidence/plan_report.md`.

## Claims

### C1 — None of the GM's bottom-10 (lowest total house win) is a weak machine.

- **Table / query:** prepared_daily_view + machine_day + game_math; zone × game IPF fit (pipeline/model.py full fit; recomputed in app.js for any period)
- **Result:** 9/10 in Back Forty (zone rate $12.4 vs $15.2–21.5 per open hour elsewhere); 8/10 low-hold games (game factor 0.56–0.68); 3/10 on the floor 49–132 days; machine index 0.95–1.10 for all ten.
- **Alternative explanation tested:** Bad luck: luck z of the ten ranges −2.4 to +0.6 except M-1158 (−4.6), so luck adds to the shortfall but does not create it. Downtime: availability 99.5–99.9% for all ten.
- **Limitation:** Zone × game is a fitted structure; a machine's own appeal and its slot within a bank cannot be fully separated without moving it.
- **Dashboard tab:** `verdict`

### C2 — M-1158 pays out far more often than its configured game; it should be inspected.

- **Table / query:** machine_day.payout_positive_spins / paid_spins vs game_math.hit_probability (G-STD90 = 0.31544)
- **Result:** Hit rate 38.6% over 674,454 spins, z = +124 (next-largest |z| among 310 machines = 2.8); observed hold 3.0% vs 10% configured; luck residual −$36,165 (z = −4.6). Stable every month Jan–Jun.
- **Alternative explanation tested:** Luck: ruled out (binomial z = 124). A meter/reporting fault rather than a paytable change is possible — that is what inspection decides.
- **Limitation:** A pattern is a lead, not proof of wrongdoing; the cause is unknown.
- **Dashboard tab:** `machines`

### C3 — Game factors are multiplicative and the same in every zone.

- **Table / query:** prepared_daily_view: sum(theo_usd)/sum(available_hours) by config × zone, divided by the zone rate
- **Result:** e.g. Royal Draw 0.59 (Back Forty), 0.55 (Bar), 0.57 (Entrance), 0.54 (Garage), 0.58 (Hotel), 0.55 (Pit); machine index after zone × game has SD ≈ 6%.
- **Alternative explanation tested:** Players sort themselves (fans of a game seek it out): would show up as zone × game interactions; none are visible, but it is the reason our 'low' case halves the swap gain.
- **Limitation:** Observational; the swap plan is designed as a measured test.
- **Dashboard tab:** `machines`

### C4 — The Mar 3–Apr 6 walkway closure cut Back Forty play by about a third and cost ~$163,000 of expected win.

- **Table / query:** floor_walkways (W-ENT-B40 closure) + prepared_daily_view; ratio of Back Forty to rest-of-floor theo per open hour (pipeline/analysis.py §D)
- **Result:** Ratio 0.669 before, 0.461 during, 0.643 after; lost theo = Σ closure days (rest rate × pre ratio × B40 hours − B40 theo) = $163,371.
- **Alternative explanation tested:** A floor-wide dip in March: ruled out — the rest of the floor was flat or up in the same weeks (ratio, not level).
- **Limitation:** Counterfactual assumes the pre-closure ratio would have held; the post-closure ratio (0.643) suggests part of the gap is a lasting habit change.
- **Dashboard tab:** `demand`

### C5 — June demand fell with the city, not because of the floor.

- **Table / query:** property_day coin-in by month vs real_sources/city_visitation_monthly (LVCVA)
- **Result:** Floor coin-in/day June −4% vs Jan–Apr; LVCVA June visitors −5% vs Jan–Apr mean (−11% year on year), convention attendance 375k vs ~590k.
- **Alternative explanation tested:** Heat (NOAA June mean max 38.6 °C) — moves with the same months; we cannot separate heat from tourism with 6 monthly points.
- **Limitation:** LVCVA describes all Las Vegas visitors and was published later; context only.
- **Dashboard tab:** `demand`

### C6 — Downtime cost ~$99,000 of expected win (0.42% of theo), mostly from Ridgeline cabinets.

- **Table / query:** machine_hour (available_seconds) × each machine's theo per open hour at that local hour (pipeline/analysis.py §A)
- **Result:** 5,021 down hours; $98,886 lost theo; Ridgeline $54,222 (55%) with 94 of 310 machines.
- **Alternative explanation tested:** Players move to a neighbour (then nothing is lost): matched bank-hour test shows other machines' occupancy rises only +0.5 pp (+1.1%, 95% CI 0.15–0.79 pp).
- **Limitation:** Upper bound; uses average rates by hour of day, not the exact demand at the minute of the fault.
- **Dashboard tab:** `downtime`

### C7 — Short-staffed shifts roughly triple repair wait.

- **Table / query:** operations (opened → work_started) joined to shift_roster slot_tech headcounts (pipeline/analysis.py §C)
- **Result:** Day shift: 2.0 h when short (n=72) vs 0.58 h (n=255); swing 2.6 h vs 0.70 h; grave (always 1 tech) 2.0 h. OLS: −1.82 h per extra tech (SE 0.17).
- **Alternative explanation tested:** Harder faults on short days: repair duration (work_started → available) is ~3 h at every hour, so the difference is waiting, not difficulty.
- **Limitation:** Absences were concentrated in April–May; seasonality and staffing overlap.
- **Dashboard tab:** `downtime`

### C8 — Tracked players lost $15.6M, in line with theo; results are highly concentrated.

- **Table / query:** player_period (tracked_net_usd, theo_usd), per player over Jan–Jun
- **Result:** Net −$15,585,461 vs theo $15,485,021; 13.6% of 113,890 players ahead; top 1% = 22.7% of theo, top 10% = 66.4%.
- **Alternative explanation tested:** House luck on carded play: luck residual is only −0.6% of theo.
- **Limitation:** Carded play only (~66% of coin-in); a player may also play uncarded.
- **Dashboard tab:** `players`

### C9 — On May 1 comps became 2.3× cheaper in points; comp cost stepped up ~10% in May and carded play rose 2.8% vs uncarded.

- **Table / query:** loyalty_ledger redemptions (points ÷ face value per gaming day); player_period comp_cost; machine_day carded vs uncarded coin-in (DiD, pipeline/analysis.py §E)
- **Result:** 13.1 → 5.8 points per comp $; reinvestment 1.1% → 1.3% of theo; DiD +2.8% (95% CI 0.5–5.2%); placebo (Jan–Feb vs Mar–Apr) −0.8% (CI −3.0–1.5%).
- **Alternative explanation tested:** More card use rather than more play: theo per active player-month is flat by tier (Base 94→96, Gold 222→220) and total floor coin-in did not rise — consistent with re-carding.
- **Limitation:** No randomized control; that is what the comp pilot would add.
- **Dashboard tab:** `comps`

### C10 — Adjusting for location and game ranks machines' future earnings better than raw house win.

- **Table / query:** pipeline/model.py: TRAIN Jan–Apr, HOLD May–Jun, 307 machines; inner validation for shrinkage k
- **Result:** Relative error 3.1% (model) vs 3.8% (own theo history) vs 11.7% (own house win); GM's list May–Jun index 1.01 with 0/10 in the true bottom-10; model's list 0.90 with 4/10.
- **Alternative explanation tested:** Simple luck removal (theo history) already captures most of the gain and wins on absolute $ MAE (1.06 vs 1.26 $/h) because all methods miss the May–Jun floor slowdown.
- **Limitation:** One 2-month holdout; the walkway closure inside TRAIN makes Back Forty harder to forecast.
- **Dashboard tab:** `model`

### C11 — A promotion weekend should return 2–5× its $15,000 cost.

- **Table / query:** property_day theo on event days vs same weekdays without events; events table
- **Result:** Winter Slot Tournament (Feb 21–23): +$82,500 theo vs a normal Fri–Sun, with no dip in the following week; Locals Week +6.5%/day.
- **Alternative explanation tested:** The February lift came from something else that weekend: no other event in the calendar; Super Bowl was two weeks earlier.
- **Limitation:** Two past promotions only; July is a weaker month (×0.95 applied) and the lead is 14 days instead of 4 weeks.
- **Dashboard tab:** `plan`

### C12 — New Back Forty signs need only a 2.8% lift to pay back in July; the closure showed the zone's demand depends on access.

- **Table / query:** pipeline/plan.py; Back Forty theo/day May–Jun from prepared_daily_view; closure ratios from pipeline/analysis.py §D
- **Result:** Back Forty ≈ $13,200 theo/day; 20 days after the 10-day lead; mid case closes the post-closure gap (0.643 → 0.669, +4.0%) = $10,584 vs $7,500.
- **Alternative explanation tested:** Back Forty is weak because of its games, not access: game mix is already removed by the zone × game model, and the zone fell 31% when only the walkway changed.
- **Limitation:** No past signage change to calibrate the effect; measured against the post-closure ratio with no other changes in the zone.
- **Dashboard tab:** `plan`

### C13 — Moving the strongest games out of the Back Forty is a good long-run move but not a July one.

- **Table / query:** pipeline/plan.py using zone (Z) and game (C) factors and machine intervals from the full model fit
- **Result:** Gain/h = (Z_to − Z_from) × (C_strong − C_weak) ≈ $5–7 per pair; 8 candidate pairs ≈ $28,000 in July vs $28,800 cost, then ≈ $1,000/day.
- **Alternative explanation tested:** Regulars follow their game (sorting) — would halve the gain.
- **Limitation:** Deferred to August so it does not confound the signage test.
- **Dashboard tab:** `plan`

## Budget plan (July 1–30, 2025)

| Action | Qty | Cost | Effect low / mid / high | Measurement |
|---|---|---|---|---|
| Machine inspection and paytable verification (A-INSPECT) — M-1158 (Back Forty, Desert Gold, slot L-31-4) | 1 | $1,200 | $0 / $5,794 / $5,794 ($ theo-equivalent house win, Jul 2-30) | After the fix, hit rate on the next 50,000 spins must be within 31.5% ± 0.4 pp (±2 SE); observed hold tracked weekly vs 10% theo hold. |
| Property promotion weekend (A-PROMO) — Slot-tournament weekend, Fri-Sun Jul 25-27 (after the 14-day lead) | 1 | $15,000 | $27,515 / $52,956 / $78,397 ($ extra floor theo over the weekend) | Model B (weekday forecast, frozen on Jul 1) gives the counterfactual; lift = actual − forecast. Daily MAE is ~5%, so a 3-day lift above ~6% is distinguishable from noise. Check the next weekend for pull-forward. |
| Wayfinding and signage refresh for a zone (A-WAYFINDING) — Back Forty (Z-B40): signs + sightlines on the Main Entrance walkway (W-ENT-B40) and at the Garage side | 1 | $7,500 | $2,657 / $10,584 / $21,253 ($ extra Back Forty theo, Jul 11-30) | Weekly Back Forty ÷ rest-of-floor theo per open hour vs the post-closure baseline 0.643 (weekly SD ≈ 0.01, so +3% is visible in ~3 weeks), plus Back Forty counter entries per sensor-day. No machine moves in the zone during the test. |

Spent **$23,700**, kept **$76,300**. Cost formula: qty × (unit cost + daily cost × max(0, 30 − lead days)).

Rejected options:

- **Replace the GM's bottom-10 with leased machines** ($33,800): ≈ $0 net in July: the 10 are average machines in a weak zone or low-hold games; a new cabinet in the same slot inherits the slot. Model A decision test: the GM's 10 had a May-Jun location/game-adjusted index of 1.01 (average) and 0 of them were among the truly weakest 10.
- **Add a slot technician to the grave shift** ($11,520): ≈ $739 of recovered theo in 23 days. Grave-shift faults wait 2.0 h vs 0.7 h on a fully staffed swing shift, but only ~50 faults/month happen at night, when a machine-hour is worth $15.
- **Preventive maintenance, Ridgeline** ($9,000): ≈ $4,551 if it prevents 25% of Ridgeline faults (repair cost + lost theo). Ridgeline faults are 2-3× the other brands per machine, but they already fell ~28% after March; no data on what preventive maintenance achieves.
- **Move strong games out of Back Forty (8 swap pairs)** ($28,800): ≈ $28,007 in July (mid), then ≈ $1,000/day. The zone × game model says the best games belong in the busiest zones, but in July only 1 pair(s) beat their own $3,600 cost by 10% (strong games that are weak for their spot are not promoted). It also confounds the signage test in the same zone: run it in August after the signs are measured.
- **Comp policy pilot with control group** ($4,000): Information: is the May 1 comp price cut paying for itself?. Strong #4. Carded coin-in rose 2.8% vs uncarded after May 1 (placebo ≈ 0), but that may be more card use rather than more play. Recommended next once a slot frees up.
- **Second promotion weekend** ($15,000): Unknown until the first one is measured. Test one, measure against the frozen forecast, then scale.
- **Bigger guest survey / purchased machine / floor-wide comp change** (—): —. No evidence linking them to the causes we found; a purchase ($22,000) has 9 operating days in the horizon.

Sensitivity:

- All three actions at LOW effect: benefit $30,172 vs cost $23,700
- All at MID: benefit $69,334 vs cost $23,700
- All at HIGH: benefit $105,444 vs cost $23,700
- Promotion flops (0), others MID: benefit $16,378 vs cost $23,700
- Inspection finds nothing, promotion and signs MID: benefit $63,540 vs cost $23,700
- Promotion only at the weak Locals-week lift, no seasonality discount: benefit $28,963 vs cost $15,000

## Prior work and industry practice (checked before finalising)

We found no earlier public Dashboard Royale entry or open slot-floor dashboard to reuse. Our methods follow standard practice:

- **Actual-to-theoretical index and control bands** instead of a fixed hold-% threshold; check machine → game → zone → property. Five causes of a hold gap are checked in order: luck, wrong game-mix theo, jackpot accounting, meter fault, integrity (casinomanagers.net, *Theoretical hold vs actual hold*). For M-1158 the hit-rate test rules out luck (z = +124) and its theo uses its own game's RTP; the inspection checks the remaining three (jackpot accounting, meters, configuration/integrity).
- **Lost theo from downtime** = down hours × comparable theo per hour, and some play moves to neighbouring machines (casinomanagers.net, *Slot machine performance metrics*). We measured that shift: about +1% neighbour occupancy, so our downtime loss is an upper bound.
- **Win per unit per day (WPUPD) against the house average** is the usual floor KPI (calbizjournal.com, *Slot machine management*). Our machine index U is a location- and game-adjusted version of that index.
- **Location + game features explain most unit volume.** Lucas & Dunn (2005, *J. Hospitality & Tourism Research*, doi:10.1177/1096348004273427) explain 64%. Lucas & Kim (*UNLV Gaming Research & Review Journal* 29(1)) find that layout order changes daily theo win by about 21%, so which machine goes where must be tested, not assumed. That is one reason the machine swaps are deferred.
- **Funnel plot** with exact-variance limits, as in FunnelPlotR (NHS-R community), on the Machines tab.
- Operators rank machines on net contribution, so the Machines tab also shows house win minus lease, service, power and repair cost; replacement is priced from `action_catalog`.

## Methods in one paragraph each

**Luck.** Machine-day house win vs theo (Σ bet × (1 − configured RTP)). The variance of a day's house win is Σ bet² × the game's payout-multiplier variance (`machine_day.sum_bet_squared` × `game_math.payout_multiplier_variance`), so luck z = (house win − theo) / √Σvariance is exact, not assumed.

**Leak test.** Payout-positive spins ~ Binomial(paid spins, published hit probability); |z| ≥ 5 is flagged for inspection (safe after 310 tests).

**Location × game.** Iterative proportional fitting of theo per available hour on zone and game (and weekday in the model), with a separate level for the Back Forty during the walkway closure. Machine index U = (theo + k)/(expected + k); k chosen by an inner Jan–Feb → Mar–Apr validation; quasi-Poisson interval with estimated dispersion φ.

**Validation.** Train Jan–Apr, test May–Jun, no rows after Apr 30 used for any holdout prediction; baselines = own house win per hour (GM's logic) and own theo per hour; metrics = MAE, RMSE, bias, Spearman, relative error, paired bootstrap; decision test = do the 10 lowest-ranked machines stay weak in May–Jun?

**Downtime.** Down seconds from `machine_hour` × the machine's own theo per available hour at that local hour; substitution tested with matched bank × hour-of-day × weekday cells.

**Comps.** Points per comp dollar from `loyalty_ledger` redemptions (ratio of sums); difference-in-differences of carded vs uncarded coin-in with a placebo period; comp cost counted once (it is inside POS cost of goods).

## AI use disclosure

We used AI assistants: Claude (Anthropic) planned the analysis, chose methods, wrote specifications, reviewed results and drafted the text; DeepSeek wrote and ran the data-extraction, analysis, model and dashboard code from those specifications; Codex (OpenAI) reviewed the money math. Every number shown is produced by the scripts in the repository and was checked against the raw tables. Team members reviewed the findings and recorded the video.

## Data notes

- Gaming day 06:00–06:00 local; 2025-03-08 has 23 h (scheduled_seconds used). Ratios are ratios of sums. Off-floor rows (1,018) excluded.
- Player tables are carded play only (~66% of coin-in). Traffic counters count crossings, offline hours excluded.
- LVCVA/Missouri/NOAA real data are used as context only (published after 2025; not model inputs).
