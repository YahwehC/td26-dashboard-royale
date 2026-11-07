# Notes

## 2026-11-07
**Done:** read GUIDE.md/README; git init; cloned challenge repo (commit 5f9274b); installed duckdb/pandas/pyarrow/streamlit/plotly; data verified (62 checksums, 31 CSV/Parquet comparisons PASS via patched script).
**Decided:** Python + DuckDB + Streamlit; strategy = "GM's list vs our list", luck ranges around theo, hunt planted anomalies, experiments as recommendations.
**Next:** run `verify_semantics.py`; profile prepared_daily_view; recompute theo/hold and check vs raw meters; deadline unknown - check Devpost.

## Hypotheses to test (from Harrigan & Dixon 2009, PAR sheets paper; cite in write-up)
1. **Luck range:** payback +/- VI/sqrt(spins), VI = 1.65 x SD of one spin's net result (90% interval). Check `game_math` for volatility / win distribution columns; else estimate SD from data. Flag a machine as "unlucky" if actual win vs theo sits inside the range for its spin count.
2. **Hidden RTP versions:** same game can be configured at different RTPs (85-96.2% in the paper). Check whether low earners are on higher-RTP configs (`machines` + `game_math` + `placements`).
3. **Hand-pay downtime:** big wins freeze a machine ~5 min. Check `operations` and `machine_hour` for downtime tied to large payouts.
4. **Game type speed:** spins/hour differs by game type (about 600 mechanical vs 1,200 video, faster with stop buttons). Normalize by spins/exposure, not raw win, across game types.
5. **Ethics:** paper shows how structure hides losses; cite as reason to avoid actions that push heavy losers to play more.

## First luck test (analysis/luck_test.py; proxy for GM list = 10 lowest raw house win, real list not found yet)
- 310 machines, 55,092 on-floor machine-days. Used `game_math.payout_multiplier_variance`: z = residual / sqrt(sum spins*avgbet^2*variance). Overall z sd is 1.25 (not 1), so the variance estimate is a bit low; treat |z|>3 as flags, not proof.
- **M-1158 (Desert Gold, 90% RTP): z -5.16**, win $15.8k vs theo $52k on 674k spins at 99.9% availability. Not plausible as luck -> check raw meters / payout fault. Other |z|>3: M-1210 (-3.38), M-1054 (-3.17).
- 5 of the bottom 10 by raw win are **Royal Draw (95% RTP)**, 3 are Comet Cash: low win is mostly low-hold game math, not weak machines. Ranking by theo/exposure changes the list.
- M-5076 (178k spins) and M-1118 (50k spins) have little exposure; M-1118 avg bet ~$5 (Platinum Reels min bet $5).
- Next: find GM's actual list (docs/action_catalog?), check M-1158 in machine_day/operations/machine_hour, add time-trend check (did the residual start at a date?).

## GM's list found (GUIDE.md line ~100-120) + semantics check
- `verify_semantics.py` runs as-is on Windows: 11/11 PASS.
- **GM's bottom 10** = lowest SUM(house_win_usd) over `d.active` rows: M-5076, M-1158, M-1120, M-1118, M-1238, M-1181, M-1035, M-1179, M-1017, M-1265. Matches my proxy exactly.
- **Exposure trap:** M-5076 (49 days), M-1118 (55 days), M-1120 (132 days) were on the floor only part of the window, so the raw sum penalizes them. Fix: compare per-day or per-exposure-hour (theo/day, hold), not totals.
- Availability is ~99.5%+ for all 10, so downtime does NOT explain this list.
- Hold: Royal Draw 2.4-5.4% (configured 5%), Comet Cash 6.6-8.0% (configured 8%): near-design hold = low-margin game, not a fault. M-1158 hold 3.0% vs 10% configured = the outlier.
- Gotcha: `days` is a reserved word in DuckDB SQL.

## Per-day ranking (committed 1836a62 = setup; this section added after)
- Of GM's 10 (total win): 9 stay in bottom 10 by win/day, 8 by theo/day, only 1 by luck residual (M-1158). Only M-1118 drops out per day (rank 114; $365/day, on floor 55 days). My earlier "exposure flaw" claim applies to M-1118 mainly; M-5076/M-1120 are still bottom per day.
- So these are mostly NOT unlucky: they have low earning power (theo/day). Theme explains a lot: Royal Draw avg theo/day $236 (lowest theme, design hold 5%) vs Prairie Thunder $499, Aurora Link $676.
- Within-theme gap still open: Royal Draw machines M-1120 ($143), M-5076 ($153), M-1017 ($163) sit well below the Royal Draw avg ($236) -> location/traffic/bet size? Compare vs same-theme peers and by zone/bank next.
- Other low-win/day machines outside GM's list: M-1256 (Desert Gold, $200/day), M-1063 (Comet Cash), M-1192 (Royal Draw, z -2.67).
- Repo-local git identity set (email from account, name "user"); change with `git config user.name`.

## Peer comparison + verdicts (analysis/peer_verdicts.py) - uncommitted
- **Back Forty zone is the story.** 9 of GM's 10 are in Back Forty (49 machines, 8 banks; only M-1118 is not). Same game earns ~35-40% less theo/day inside it than outside (e.g. Prairie Thunder $338 vs $539, Desert Gold $266 vs $437, Royal Draw $166 vs $255); occupancy 22-30% vs 38-46%. Each of the 8 non-M-1158 machines is about average for its own game inside Back Forty; M-1158 theo/day ($287) is above the Back Forty Desert Gold avg ($266), so its problem is payout, not traffic. M-1118 is in High-Limit Room.
- **Natural experiment:** M-1120 (Royal Draw, slot L-38-5) retired 2025-05-13; M-5076 (same game G-VID95, same slot) installed that day for $2,500. Theo/day $143 (M-1120) vs $153 (M-5076): replacing the machine changed nothing. Caveat: only 49 days.
- **M-1118 was retired 2025-02-25**, already off the floor; theo/day $461 is above its game avg $402. GM's list includes a machine that is already gone.
- **M-1158 (Desert Gold, G-STD90 90% RTP all six months, no config change):** hold ~10% expected; weekly hold swings, Mar 10 - May 26 mostly <=1.5% / negative, Jan-Feb ~5%, late Jun 5-15%. 1 repair ticket (Mar 10, $84). 5 sigma (4 after the 1.25 overdispersion adjustment). Data can't say fault vs. extreme luck -> inspect (A-INSPECT $1,200, lead 1 day).
- Action costs to price against GM plan: replace lease $2,500 + $55/day (limit 20), buy $22,000 (limit 10), move machine $1,800 (limit 24), move bank $9,500 (limit 3), wayfinding $7,500/zone (limit 2), inspect $1,200 (limit 15).
- Open: traffic counters for Back Forty (zone_traffic_hourly), what makes it low (walkways/sightlines in floor_walkways, floor_locations).

## Why Back Forty is weak: access (analysis/closure_test.py) - uncommitted
- Layout: Back Forty (Z-B40) is a far corner (x=20,y=92). Walkways: to Main Entrance 42m, to Bar Row 80m, to Garage 100m; NO link to Center Pit. Sensor traffic 22.6 entries/hr vs Pit 173, Bar 118, Main Entrance 115, Garage 95, Hotel 84 (High-Limit 6.7 is a small room by design).
- **Natural experiment:** walkway W-ENT-B40 (Main Entrance <-> Back Forty) closed for renovation 2025-03-03 to 2025-04-07. Back Forty theo/day vs rest of floor (excl. High-Limit): 66.4% before -> **45.8% during** -> 63.3% after. Back Forty sensor entries/hr: 25.2 -> 17.6 (-30%) -> 22.7, while Pit/Bar/Entrance stayed flat or rose. So foot traffic/access causes much of the gap.
- Caveats: one event, one zone, ~5 weeks; rest-of-floor is the control (assumes it was unaffected); machine mix per period not adjusted.
- Implication for Q6: actions aimed at Back Forty access/visibility (A-WAYFINDING $7,500, lead 10 days -> only ~20 of the 30 July days exposed; maybe a test of 1 zone) beat replacing machines. A-MOVE-MACHINE only helps if there are empty slots in higher-traffic zones (check capacity vs occupied slots in floor_locations/placements).
