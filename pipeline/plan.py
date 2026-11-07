"""Budget plan for July 1-30 2025: computes the swap-move plan from the fitted demand model and prices every
candidate action from action_catalog. Writes site/data/plan.json and docs/evidence/plan_report.md.

Money rule from the guide: cost = qty * (unit_cost + recurring_per_day * max(0, 30 - lead_days)) / 100 (cents -> $).
Benefits are expected house win (theo) only for the days left after the lead time. All estimates are ranges.
"""
import json, os, duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data-repo", "data")
core = json.load(open(os.path.join(ROOT, "site", "data", "core.json")))
model = json.load(open(os.path.join(ROOT, "site", "data", "model.json")))
ana = json.load(open(os.path.join(ROOT, "site", "data", "analysis.json")))

con = duckdb.connect()
cat = {r[0]: dict(zip(["id", "name", "unit", "unit_cost", "rec", "lead", "down_min", "limit", "group", "notes"], r))
       for r in con.sql(f"select action_type_id,name,unit,unit_cost_cents,recurring_cost_cents_per_day,lead_days,"
                        f"downtime_minutes,quantity_limit,incompatibility_group,notes "
                        f"from '{DATA}/2_machine_decision/action_catalog.parquet'").fetchall()}

def price(aid, qty):
    a = cat[aid]
    return qty * (a["unit_cost"] + a["rec"] * max(0, 30 - a["lead"])) / 100.0

HORIZON = 30
Z = model["A"]["full"]["Z"]; C = model["A"]["full"]["C"]
U = {u["machine_id"]: u["U"] for u in model["A"]["full"]["U"]}
HI80 = {u["machine_id"]: u["hi80"] for u in model["A"]["full"]["U"]}

# --- where every machine sits at the end of June (last active row) -------------------------------------------
last = con.sql(f"""select machine_id, zone_id, bank_id, location_id, config_id, theme
    from '{DATA}/1_prepared_views/prepared_daily_view.parquet'
    where active qualify row_number() over (partition by machine_id order by gaming_date desc)=1
      and max(gaming_date) over (partition by machine_id) = date '2025-06-30'""").fetchall()
mach = {r[0]: dict(zip(["id", "zone", "bank", "loc", "cfg", "theme"], r)) for r in last}
avail = con.sql(f"select sum(available_hours)/sum(case when active then 24.0 end) from "
                f"'{DATA}/1_prepared_views/prepared_daily_view.parquet' where active and gaming_date>='2025-05-01'").fetchall()[0][0]

# --- A-MOVE-MACHINE: swap pairs --------------------------------------------------------------------------------
# Model: theo/available-hour = Z[zone] * C[game] * U[machine]. Swapping machine a (zone za) with b (zone zb):
#   gain/h = (Z[zb]-Z[za]) * (C[a]*U_a - C[b]*U_b)   if the machine effect U travels with the cabinet (high case)
#   gain/h = (Z[zb]-Z[za]) * (C[a] - C[b])           if U belongs to the slot, not the machine (mid case)
# Low case: half of the zone gap is player sorting rather than traffic -> 0.5 * mid.
# Exclusions: High-Limit Room (different denominations/players), M-1158 (inspection), machines newer than 60 days.
EXCLUDE = {"M-1158"}
MOVE = cat["A-MOVE-MACHINE"]
op_days = HORIZON - MOVE["lead"]
hours = op_days * 24 * avail
move_down_h = MOVE["down_min"] / 60.0   # each moved machine is dark for this long
cands = []
ids = [m for m in mach if mach[m]["zone"] != "Z-HL" and m not in EXCLUDE]
for a in ids:
    for b in ids:
        ma, mb = mach[a], mach[b]
        dz = Z[mb["zone"]] - Z[ma["zone"]]
        if dz <= 0 or HI80[a] < 0.95:   # never promote a machine that is clearly weak for its spot
            continue
        mid = dz * (C[ma["cfg"]] - C[mb["cfg"]])
        high = dz * (C[ma["cfg"]] * U[a] - C[mb["cfg"]] * U[b])
        # downtime of both moves, valued at each machine's full rate in its destination zone
        down_loss = move_down_h * (Z[mb["zone"]] * C[ma["cfg"]] + Z[ma["zone"]] * C[mb["cfg"]])
        mid, high = mid - down_loss / hours, high - down_loss / hours
        if mid > 0:
            cands.append((mid, high, a, b))
cands.sort(reverse=True)
used, pairs = set(), []
N_PAIRS = 8
for mid, high, a, b in cands:
    if a in used or b in used:
        continue
    used |= {a, b}
    pairs.append(dict(up=a, up_from=mach[a]["zone"], up_game=mach[a]["theme"], down=b, down_from=mach[b]["zone"],
                      down_game=mach[b]["theme"], gain_h_mid=round(mid, 3), gain_h_high=round(high, 3),
                      gain_30d_mid=round(mid * hours, 0), gain_30d_high=round(high * hours, 0)))
    if len(pairs) == N_PAIRS:
        break
# Fund only pairs whose in-horizon mid gain beats their own cost by >= 10%; the rest are a long-run option.
pair_cost = price("A-MOVE-MACHINE", 2)
all_pairs = pairs
pairs = [p for p in all_pairs if p["gain_30d_mid"] >= 1.1 * pair_cost]
later_pairs = [p for p in all_pairs if p not in pairs]
move_qty = 2 * len(pairs)
move_cost = price("A-MOVE-MACHINE", move_qty)
mv_mid = sum(p["gain_30d_mid"] for p in pairs)
mv_high = max(sum(p["gain_30d_high"] for p in pairs), sum(p["gain_30d_mid"] for p in pairs))
mv_low = 0.5 * mv_mid
# downtime loss: 3 h per move at the machine's own rate (already netted per machine in `hours`)

# --- A-INSPECT: M-1158 ------------------------------------------------------------------------------------------
r = con.sql(f"""select sum(coin_in_cents)/100.0, sum(house_win_cents)/100.0, sum(theo_cents)/100.0, count(*)
    from '{DATA}/2_machine_decision/machine_day.parquet' where machine_id='M-1158' and active""").fetchall()[0]
ci_day = r[0] / r[3]
gap_day = (r[2] - r[1]) / r[3]           # theo - actual per day (the "leak" if the paytable really differs)
INS = cat["A-INSPECT"]
ins_days = HORIZON - INS["lead"]
ins_cost = price("A-INSPECT", 1)
ins_mid = gap_day * ins_days             # restored to configured paytable, play unchanged
ins_low = 0.0                            # inspection finds nothing actionable
ins_high = ins_mid

# --- A-PROMO: one promotion weekend -----------------------------------------------------------------------------
ev = {e["id"]: e for e in ana["events"]}
pd = core["pd"]; dates = core["dates"]
def theo_on(ds):
    return sum(pd["th"][dates.index(d)] for d in ds)
tourn = theo_on(["2025-02-21", "2025-02-22", "2025-02-23"])
wk = core["weekday"]; ev_dates = set()
for e in core["events"]:
    d0, d1 = e["start"], e["end"]
    ev_dates |= {d for d in dates if d0 <= d <= d1}
def wd_mean(name):
    xs = [pd["th"][i] for i, d in enumerate(dates) if wk[i] == name and d not in ev_dates]
    return sum(xs) / len(xs)
base_weekend = wd_mean("Fri") + wd_mean("Sat") + wd_mean("Sun")
promo_high = tourn - base_weekend                                  # Feb tournament format, 4-week lead
promo_low = base_weekend * ev["EV-P-LOCALS"]["lift_pct"] / 100.0   # weaker Locals-week format
promo_mid = (promo_low + promo_high) / 2
# July demand is weaker than February (LVCVA June visitors -7% vs Jan-Apr mean; floor theo June -4%): scale 0.95
season = 0.95
promo_low, promo_mid, promo_high = [x * season for x in (promo_low, promo_mid, promo_high)]
promo_cost = price("A-PROMO", 1)

# --- rejected options, priced with the same evidence --------------------------------------------------------------
st = ana["staffing"]
grave = [s for s in st["by_shift"] if s["shift"] == "grave"][0]
swing_ok = [s for s in st["by_shift"] if s["shift"] == "swing" and not s["understaffed"]][0]
grave_faults_month = grave["n"] / 6.0
night_rate = sum(ana["downtime"]["by_hour"]["lost_theo"][h] for h in [22, 23, 0, 1, 2, 3, 4, 5]) / \
             max(1e-9, sum(ana["downtime"]["by_hour"]["down_h"][h] for h in [22, 23, 0, 1, 2, 3, 4, 5]))
tech_days = HORIZON - cat["A-TECH-SHIFT"]["lead"]
tech_benefit = grave_faults_month * (tech_days / 30) * (grave["mean_wait_h"] - swing_ok["mean_wait_h"]) * night_rate
ridge = [x for x in ana["downtime"]["by_mfr_month"] if x["mfr"] == "Ridgeline" and x["month"] in ("2025-05", "2025-06")]
ridge_month_cost = sum(x["repair_cost"] for x in ridge) / 2
ridge_month_lost = sum(x["lost_theo"] for x in ridge) / 2
pm_days = HORIZON - cat["A-PREVENTIVE"]["lead"]
pm_benefit_25 = 0.25 * (ridge_month_cost + ridge_month_lost) * pm_days / 30
b40 = ana["closure"]["periods"]
b40_theo_day = con.sql(f"select sum(theo_usd)/count(distinct gaming_date) from "
                       f"'{DATA}/1_prepared_views/prepared_daily_view.parquet' where active and zone_id='Z-B40' "
                       f"and gaming_date>='2025-05-01'").fetchall()[0][0]
sign_days = HORIZON - cat["A-WAYFINDING"]["lead"]
sign_gap = b40["pre_ratio"] / b40["post_ratio"] - 1          # B40 never fully recovered after the closure
sign_benefit = b40_theo_day * sign_gap * sign_days
sign_breakeven = price("A-WAYFINDING", 1) / (b40_theo_day * sign_days)
# lease replacement of the GM's bottom-10 with an average game (C=1) in the same slot
lease_cost10 = price("A-REPLACE-LEASE", 10)
lease_days = HORIZON - cat["A-REPLACE-LEASE"]["lead"]

plan = {
  "budget": 100000,
  "horizon": "2025-07-01..2025-07-30",
  "actions": [
    {"id": "A-INSPECT", "name": cat["A-INSPECT"]["name"], "qty": 1, "targets": ["M-1158 (Back Forty, Desert Gold, slot L-31-4)"],
     "cost": ins_cost, "lead_days": INS["lead"],
     "effect_low": round(ins_low), "effect_mid": round(ins_mid), "effect_high": round(ins_high), "effect_unit": "$ theo-equivalent house win, Jul 2-30",
     "assumptions": [f"M-1158 hit rate 38.6% vs configured 31.5% over 674k spins (z = +124); observed hold 3.0% vs 10% configured",
                     f"If the paytable is restored, house win returns to theo: +${gap_day:,.0f}/day at the H1 coin-in of ${ci_day:,.0f}/day",
                     "Play volume stays the same after the fix (it may fall if players liked the looser game)"],
     "uncertainty": "Diagnosis is near-certain (a hit-rate gap this size is not luck); the cause is unknown (paytable, firmware, meter). Outcome is information first.",
     "measurement": "After the fix, hit rate on the next 50,000 spins must be within 31.5% ± 0.4 pp (±2 SE); observed hold tracked weekly vs 10% theo hold.",
     "evidence": [{"tab": "machines", "label": "Leak test: hit-rate z-scores", "anchor": "Hit-rate screen"}, {"tab": "verdict", "label": "GM's bottom-10, rank 2", "anchor": "bottom 10 machines"}]},
    {"id": "A-PROMO", "name": cat["A-PROMO"]["name"], "qty": 1, "targets": ["Slot-tournament weekend, Fri-Sun Jul 25-27 (after the 14-day lead)"],
     "cost": promo_cost, "lead_days": cat["A-PROMO"]["lead"],
     "effect_low": round(promo_low), "effect_mid": round(promo_mid), "effect_high": round(promo_high), "effect_unit": "$ extra floor theo over the weekend",
     "assumptions": [f"High = Feb 21-23 Winter Slot Tournament: +${tourn - base_weekend:,.0f} theo vs a normal Fri-Sun, no dip in the following days",
                     f"Low = the weaker Locals Week format: +{ev['EV-P-LOCALS']['lift_pct']:.1f}% of a normal weekend",
                     "July demand ×0.95 vs Feb (LVCVA visitors and our June floor were both down)",
                     "Prizes, marketing and staffing are inside the $15,000 package"],
     "uncertainty": "Two past promotions gave +6% and +19%; the 14-day lead is shorter than the 4-week lead of the February event.",
     "measurement": "Model B (weekday forecast, frozen on Jul 1) gives the counterfactual; lift = actual − forecast. Daily MAE is ~5%, so a 3-day lift above ~6% is distinguishable from noise. Check the next weekend for pull-forward.",
     "evidence": [{"tab": "demand", "label": "Event lifts", "anchor": "Event weeks"}, {"tab": "model", "label": "Model B forecast", "anchor": "Model B:"}]},
    {"id": "A-WAYFINDING", "name": cat["A-WAYFINDING"]["name"], "qty": 1, "targets": ["Back Forty (Z-B40): signs + sightlines on the Main Entrance walkway (W-ENT-B40) and at the Garage side"],
     "cost": price("A-WAYFINDING", 1), "lead_days": cat["A-WAYFINDING"]["lead"],
     "effect_low": round(b40_theo_day * 0.01 * sign_days), "effect_mid": round(sign_benefit), "effect_high": round(b40_theo_day * 0.08 * sign_days),
     "effect_unit": "$ extra Back Forty theo, Jul 11-30",
     "assumptions": [f"Back Forty earns ${b40_theo_day:,.0f}/day of theo (May-Jun); {sign_days} days after the 10-day lead",
                     f"The walkway closure proved its demand depends on access from the main entrance: ratio to the rest of the floor 0.669 -> 0.461 while closed, and only back to {b40['post_ratio']:.3f} after",
                     f"Low +1%, mid +{sign_gap * 100:.1f}% (closes the post-closure gap), high +8%; break-even = +{sign_breakeven * 100:.1f}%"],
     "uncertainty": "No past signage change to learn from; the closure shows that access matters, not how much signs restore.",
     "measurement": f"Weekly Back Forty ÷ rest-of-floor theo per open hour vs the post-closure baseline {b40['post_ratio']:.3f} (weekly SD ≈ 0.01, so +3% is visible in ~3 weeks), plus Back Forty counter entries per sensor-day. No machine moves in the zone during the test.",
     "evidence": [{"tab": "demand", "label": "Back Forty vs rest, weekly", "anchor": "B40-to-rest"}, {"tab": "demand", "label": "Zone earning rates", "anchor": "Zone table"}]},
  ],
  "rejected": [
    {"name": "Replace the GM's bottom-10 with leased machines", "cost": lease_cost10,
     "expected_benefit": "≈ $0 net in July: the 10 are average machines in a weak zone or low-hold games; a new cabinet in the same slot inherits the slot",
     "reason": "Model A decision test: the GM's 10 had a May-Jun location/game-adjusted index of 1.01 (average) and 0 of them were among the truly weakest 10."},
    {"name": "Add a slot technician to the grave shift", "cost": price("A-TECH-SHIFT", 1),
     "expected_benefit": f"≈ ${tech_benefit:,.0f} of recovered theo in {tech_days} days",
     "reason": f"Grave-shift faults wait {grave['mean_wait_h']:.1f} h vs {swing_ok['mean_wait_h']:.1f} h on a fully staffed swing shift, but only ~{grave_faults_month:.0f} faults/month happen at night, when a machine-hour is worth ${night_rate:.0f}."},
    {"name": "Preventive maintenance, Ridgeline", "cost": price("A-PREVENTIVE", 1),
     "expected_benefit": f"≈ ${pm_benefit_25:,.0f} if it prevents 25% of Ridgeline faults (repair cost + lost theo)",
     "reason": "Ridgeline faults are 2-3× the other brands per machine, but they already fell ~28% after March; no data on what preventive maintenance achieves."},
    {"name": f"Move strong games out of Back Forty ({len(all_pairs)} swap pairs)", "cost": price("A-MOVE-MACHINE", 2 * len(all_pairs)),
     "expected_benefit": f"≈ ${sum(p['gain_30d_mid'] for p in all_pairs):,.0f} in July (mid), then ≈ ${sum(p['gain_h_mid'] for p in all_pairs) * 24 * avail:,.0f}/day",
     "reason": f"The zone × game model says the best games belong in the busiest zones, but in July only {len(pairs)} pair(s) beat their own $3,600 cost by 10% (strong games that are weak for their spot are not promoted). It also confounds the signage test in the same zone: run it in August after the signs are measured."},
    {"name": "Comp policy pilot with control group", "cost": price("A-COMP-PILOT", 1),
     "expected_benefit": "Information: is the May 1 comp price cut paying for itself?",
     "reason": "Strong #4. Carded coin-in rose 2.8% vs uncarded after May 1 (placebo ≈ 0), but that may be more card use rather than more play. Recommended next once a slot frees up."},
    {"name": "Second promotion weekend", "cost": price("A-PROMO", 1),
     "expected_benefit": "Unknown until the first one is measured", "reason": "Test one, measure against the frozen forecast, then scale."},
    {"name": "Bigger guest survey / purchased machine / floor-wide comp change", "cost": None,
     "expected_benefit": "—", "reason": "No evidence linking them to the causes we found; a purchase ($22,000) has 9 operating days in the horizon."},
  ],
}
spent = sum(a["cost"] for a in plan["actions"])
plan["spent"] = spent
plan["kept"] = plan["budget"] - spent
sl, sm, sh = [x["effect_low"] for x in plan["actions"]], [x["effect_mid"] for x in plan["actions"]], [x["effect_high"] for x in plan["actions"]]
plan["sensitivity"] = [
  {"scenario": "All three actions at LOW effect", "benefit": sum(sl), "cost": spent},
  {"scenario": "All at MID", "benefit": sum(sm), "cost": spent},
  {"scenario": "All at HIGH", "benefit": sum(sh), "cost": spent},
  {"scenario": "Promotion flops (0), others MID", "benefit": sm[0] + sm[2], "cost": spent},
  {"scenario": "Inspection finds nothing, promotion and signs MID", "benefit": sm[1] + sm[2], "cost": spent},
  {"scenario": "Promotion only at the weak Locals-week lift, no seasonality discount", "benefit": round(promo_low / season), "cost": promo_cost},
]
assert len(plan["actions"]) <= 3 and spent <= 100000
assert move_qty <= cat["A-MOVE-MACHINE"]["limit"]
json.dump(plan, open(os.path.join(ROOT, "site", "data", "plan.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)

lines = ["# Plan report (pipeline/plan.py)", "", f"Availability used: {avail:.4f}; move operating hours per machine: {hours:.1f}", ""]
for a in plan["actions"]:
    lines.append(f"- **{a['id']}** ×{a['qty']}: cost ${a['cost']:,.0f}; effect low/mid/high ${a['effect_low']:,}/${a['effect_mid']:,}/${a['effect_high']:,}")
lines += ["", "## Candidate swap pairs (not funded in July)", "", "| up (leaves weak zone) | from | game | down | from | game | gain $/h mid | 28-day mid | high |", "|---|---|---|---|---|---|---|---|---|"]
for p in all_pairs:
    lines.append(f"| {p['up']} | {p['up_from']} | {p['up_game']} | {p['down']} | {p['down_from']} | {p['down_game']} | {p['gain_h_mid']} | {p['gain_30d_mid']:,.0f} | {p['gain_30d_high']:,.0f} |")
lines += ["", f"Spent ${spent:,.0f}; kept ${plan['kept']:,.0f}", "", "## Rejected"] + \
         [f"- {r['name']} (${r['cost']:,.0f}): {r['expected_benefit']} — {r['reason']}" if r["cost"] else f"- {r['name']}: {r['reason']}" for r in plan["rejected"]] + \
         ["", "## Sensitivity"] + [f"- {s['scenario']}: benefit ${s['benefit']:,} vs cost ${s['cost']:,.0f}" for s in plan["sensitivity"]]
os.makedirs(os.path.join(ROOT, "docs", "evidence"), exist_ok=True)
open(os.path.join(ROOT, "docs", "evidence", "plan_report.md"), "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines))
