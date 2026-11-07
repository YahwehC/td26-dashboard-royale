"""Builds docs/APPENDIX.md (Claims & Evidence + AI disclosure + methods) from content/*.json and the evidence reports."""
import json, os, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
claims = json.load(open(os.path.join(ROOT, "content", "claims.json"), encoding="utf-8"))
story = json.load(open(os.path.join(ROOT, "content", "story.json"), encoding="utf-8"))
plan = json.load(open(os.path.join(ROOT, "site", "data", "plan.json"), encoding="utf-8"))

L = ["# Claims & Evidence appendix — Dashboard Royale (The Gilded Ace)", "",
     "The casino and its guests are fictional (synthetic data, release 0.9.0-draft); only `4_context/real_sources` is real public data.",
     "Every number below is produced by the scripts in `pipeline/` (see the README for the run order). Evidence reports with full tables:",
     "`docs/evidence/analysis_report.md`, `docs/evidence/model_report.md`, `docs/evidence/plan_report.md`.", "",
     "## Claims", ""]
for c in claims:
    L += [f"### {c['id']} — {c['claim']}", "",
          f"- **Table / query:** {c['source']}",
          f"- **Result:** {c['result']}",
          f"- **Alternative explanation tested:** {c['alternative']}",
          f"- **Limitation:** {c['limitation']}",
          f"- **Dashboard tab:** `{c['tab']}`", ""]
L += ["## Budget plan (July 1–30, 2025)", "",
      "| Action | Qty | Cost | Effect low / mid / high | Measurement |", "|---|---|---|---|---|"]
for a in plan["actions"]:
    L.append(f"| {a['name']} ({a['id']}) — {'; '.join(a['targets'])} | {a['qty']} | ${a['cost']:,.0f} | "
             f"${a['effect_low']:,} / ${a['effect_mid']:,} / ${a['effect_high']:,} ({a['effect_unit']}) | {a['measurement']} |")
L += ["", f"Spent **${plan['spent']:,.0f}**, kept **${plan['kept']:,.0f}**. Cost formula: qty × (unit cost + daily cost × max(0, 30 − lead days)).", "",
      "Rejected options:", ""]
for r in plan["rejected"]:
    cost = f"${r['cost']:,.0f}" if r["cost"] else "—"
    L.append(f"- **{r['name']}** ({cost}): {r['expected_benefit']}. {r['reason']}")
L += ["", "Sensitivity:", ""] + [f"- {s['scenario']}: benefit ${s['benefit']:,} vs cost ${s['cost']:,.0f}" for s in plan["sensitivity"]]
L += ["", "## Methods in one paragraph each", "",
      "**Luck.** Machine-day house win vs theo (Σ bet × (1 − configured RTP)). The variance of a day's house win is Σ bet² × the game's "
      "payout-multiplier variance (`machine_day.sum_bet_squared` × `game_math.payout_multiplier_variance`), so luck z = (house win − theo) / √Σvariance is exact, not assumed.", "",
      "**Leak test.** Payout-positive spins ~ Binomial(paid spins, published hit probability); |z| ≥ 5 is flagged for inspection (safe after 310 tests).", "",
      "**Location × game.** Iterative proportional fitting of theo per available hour on zone and game (and weekday in the model), with a separate level for the "
      "Back Forty during the walkway closure. Machine index U = (theo + k)/(expected + k); k chosen by an inner Jan–Feb → Mar–Apr validation; quasi-Poisson interval "
      "with estimated dispersion φ.", "",
      "**Validation.** Train Jan–Apr, test May–Jun, no rows after Apr 30 used for any holdout prediction; baselines = own house win per hour (GM's logic) and own theo per hour; "
      "metrics = MAE, RMSE, bias, Spearman, relative error, paired bootstrap; decision test = do the 10 lowest-ranked machines stay weak in May–Jun?", "",
      "**Downtime.** Down seconds from `machine_hour` × the machine's own theo per available hour at that local hour; substitution tested with matched bank × hour-of-day × weekday cells.", "",
      "**Comps.** Points per comp dollar from `loyalty_ledger` redemptions (ratio of sums); difference-in-differences of carded vs uncarded coin-in with a placebo period; comp cost counted once (it is inside POS cost of goods).", "",
      "## AI use disclosure", "", story["ai"]["answer"], "",
      "## Data notes", "",
      "- Gaming day 06:00–06:00 local; 2025-03-08 has 23 h (scheduled_seconds used). Ratios are ratios of sums. Off-floor rows (1,018) excluded.",
      "- Player tables are carded play only (~66% of coin-in). Traffic counters count crossings, offline hours excluded.",
      "- LVCVA/Missouri/NOAA real data are used as context only (published after 2025; not model inputs).", ""]
open(os.path.join(ROOT, "docs", "APPENDIX.md"), "w", encoding="utf-8").write("\n".join(L))
for n in ("story.json", "claims.json"):  # analyst-written dashboard text -> site/data
    shutil.copyfile(os.path.join(ROOT, "content", n), os.path.join(ROOT, "site", "data", n))
print("wrote docs/APPENDIX.md", sum(len(x.split()) for x in L), "words")
