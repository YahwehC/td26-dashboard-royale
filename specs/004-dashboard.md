# 004 — Static interactive dashboard (site/)

Goal: a single-page, static (no server, no build step) dashboard in `ROOT/site/` that judges open from GitHub Pages.
ROOT = `F:\CYH\projects\datathon\challenges\dashboard-royale`. Files to create: `site/index.html`, `site/app.js`,
`site/style.css`. Do not modify anything in `site/data/` (inputs, produced by the pipeline) or elsewhere.

Inputs (fetch with relative URLs `data/<name>.json`; formats documented in `specs/001-build-core.md`,
`specs/002-analysis.md`, `specs/003-model.md` — READ THEM, and inspect the real files' keys before coding):
- `data/core.json`, `data/players.json`, `data/ops.json`, `data/analysis.json`, `data/model.json`
- `data/story.json` — text written by the analyst: `{ "<tab id>": {"title": str, "question": str, "answer": str (may contain simple <b>,<i>,<br> only), "notes": [str]} }`
- `data/plan.json` — budget plan: `{ "budget": 100000, "actions": [{ "id","name","qty","targets":[str],"cost","lead_days",
  "effect_low","effect_mid","effect_high","effect_unit","assumptions":[str],"uncertainty": str,"measurement": str,
  "evidence":[{"tab","label"}] }], "kept": number, "rejected": [{"name","cost","expected_benefit","reason"}], "sensitivity": [...] }`
- `data/claims.json` — `[{ "id","claim","source","result","alternative","limitation","tab" }]`
If story/plan/claims files are missing, show a small "content pending" note instead of crashing.

Libraries: Plotly from `https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.2/plotly.min.js` only. Vanilla JS (ES2020),
no frameworks, no other CDNs. Fonts: system-ui. Must work opened via `python -m http.server` from `site/`.

## Look & accessibility
- CSS tokens on `:root` (light) + dark under `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {...} }`
  and `:root[data-theme="dark"]`; a theme toggle button sets `data-theme`. Plotly layouts read the current token
  values (paper/plot bg transparent, font color = ink, grid = hairline) and re-render on theme change.
- Colors (light/dark): surface `#fcfcfb`/`#1a1a19`, page `#f9f9f7`/`#0d0d0d`, ink `#0b0b0b`/`#f0efec`,
  ink-2 `#52514e`/`#c3c2b7`, muted `#898781`, grid `#e1e0d9`/`#2c2c2a`, axis `#c3c2b7`/`#383835`.
  Categorical in fixed order: `#2a78d6, #eb6834, #1baf7a, #eda100, #e87ba4, #008300, #6250d6, #e34948`
  (dark: `#3987e5, #d95926, #199e70, #c98500, #d55181, #008300, #9085e9, #e66767`). Status: good `#0ca30c`,
  warning `#fab219`, serious `#ec835a`, critical `#d03b3b` — always with a text label, never color alone.
  Highlight = categorical slot 2 (orange); default marks = slot 1 (blue); context/other = muted gray.
- Lines 2px, bar gaps, no dual y-axes ever, legends for >=2 series, hover tooltips on every chart
  (`hovermode: 'x unified'` for time series). `displayModeBar: false`, `responsive: true`.
- Layout: max-width 1240px, 16px gutters, cards with 12px radius and hairline border; works at 375px width
  (charts stack, tables scroll horizontally inside their card, no page-level horizontal scroll).
- Every chart card has: title (a finding, not a label), a one-line "how to read", and a "Source:" footnote naming
  the table(s). Every chart has a "Table" toggle that shows the plotted numbers as an HTML table (accessibility).
- Insert any data-derived text with `textContent` (story.json `answer` may use innerHTML: it's our own content).

## Global filter bar (sticky, one row, above all content; scopes every tab)
- Period: two `<input type=date>` (min 2025-01-01, max 2025-06-30) + preset buttons: "Full H1", "Q1", "Q2",
  "Train (Jan–Apr)", "Holdout (May–Jun)". Default Full H1.
- Zone select (All + 7 zones by name), Bank select (All + banks of the selected zone). "Reset" button.
- URL hash keeps state (`#tab=machines&from=2025-01-01&to=2025-06-30&zone=Z-B40&bank=B-33`), so links are shareable.
- Text under the bar: "Showing N gaming days · M machines · period X–Y".

## Shared computations (app.js, pure functions, on filter change; must take < 300 ms for the full period)
Let P = selected date idx range. Rows = core.md rows with d in P.
1. **Per machine in P** (all machines, independent of zone filter): days, ah, sh, oh, ci, hw, th, v, sp, hs, f, rc, cost,
   zone = zone of the bank where it had most ah, bank likewise, config.
2. **Floor fit in P (zone × game)**, on all rows in P: IPF exactly as in spec 003 step 1 but with only Z (zone, with
   the extra level "Z-B40#closed" for B40 rows dated 2025-03-03..2025-04-06) and C (config), 30 iterations, C normalised
   to ah-weighted mean 1. Expected theo e_m = sum ah*Z*C over the machine's rows; t_m = th sum;
   machine index U_m = (t_m + k)/(e_m + k), k = model.json A.k; 80% interval via the gamma posterior
   (shape t+k, rate e+k) — implement a gamma quantile in JS (Wilson–Hilferty approximation is fine for shape > 30;
   for smaller shape, use a normal approx on U with sd = sqrt(shape)/rate).
3. **Luck**: luck_m = hw − th; z_luck = luck / sqrt(v) (null if v=0).
   **Leak test**: hit-rate z = (hs − sp*p)/sqrt(sp*p*(1−p)), p = configs[c].hit_p.
4. **Attribution** (why does a machine earn less than a typical machine?), for machines with hw > 0:
   reference ah_ref = (sum over P of sched_h) × floor availability (sum ah / sum sh over P);
   factors: exposure = ah_m/ah_ref; location = Z_zone / Zbar (Zbar = ah-weighted mean of Z over P, closed level
   included as its own zone level for the B40 rows); game = C_c; machine = U_m; luck = hw/th.
   product × (ah_ref × Zbar) = hw. Show log-shares as a horizontal diverging bar per machine (negative = drag).
5. **Verdict** per machine (first rule that matches):
   - `Leak? Inspect` if |hit z| >= 5 (status critical)
   - `Short exposure` if days < 0.6 × number of days in P (status warning)
   - `Truly weak` if U hi80 < 0.92 (status serious)
   - else main drag = most negative of log(location), log(game), log(luck), log(exposure): `Location`, `Game math`,
     `Bad luck`, `Downtime/exposure` (status good = "not the machine's fault"); if none < −0.05: `Fine`.
6. **GM's list** = 10 machines with the lowest total hw in P (machines with days>0 in P).

## Tabs (top nav; keyboard accessible buttons; `#tab=` in hash)
1. **verdict** (default): story.verdict text. KPI tiles: floor coin-in, house win, theo, observed hold vs theo hold
   (ratio of sums), availability, in P. The GM's bottom-10 table: rank, machine, zone/bank, game (theme + RTP),
   days, house win, theo, luck $ and z, availability %, location factor, game factor, machine index U [80% interval],
   hit z, verdict chip. Beside/below: one attribution diverging bar chart for those 10 (stacked log factors, 5
   categorical colors in fixed order: exposure, location, game, machine, luck). Count line: "Of the GM's 10:
   x location, y game math, z short exposure, ... ".
2. **machines** (Q1): scatter of all machines (zone filter dims non-selected machines to muted): x = expected theo/h
   (e/ah), y = actual theo/h (t/ah), with y=x line, GM's 10 in orange, Leak in critical red with label.
   "Luck funnel": x = theo $, y = luck $, band ±1.96·sqrt(v) drawn as a funnel (compute v-to-theo relation per point;
   simply plot each point and draw the band per point as error bars OR plot z vs theo with ±1.96 lines — use z vs theo).
   Hit-rate z bar chart (sorted, top 15 |z|). Full machine table (sortable columns, text search, filtered by zone/bank)
   with all columns of tab 1 + manufacturer, faults, downtime h, supplied costs, contribution (hw − cost).
3. **demand** (Q2): daily floor coin-in in P (line, 7-day mean line), shaded rectangles for events (from core.events)
   and the walkway closure, annotated; B40 vs rest weekly theo/h ratio (analysis.closure.weekly) with closure shading
   and the three period ratios; zone traffic per sensor-day weekly (analysis.closure.traffic_weekly) for selected zone
   (default B40 and Main Entrance); event lifts table (analysis.events); weekday mean coin-in bar chart in P;
   zone table in P: theo/available-hour, occupancy, availability, machines.
4. **downtime** (Q3): KPIs in P: downtime hours, lost theo (upper bound), share of theo; lost theo by date (bars, P);
   by local hour (bars) and mean repair wait by hour (separate chart, from ops.faults filtered to P); faults per
   machine-month by manufacturer (bars from analysis.downtime.by_mfr_month restricted to months in P); staffing
   table (analysis.staffing.by_shift) + roster by month chart; substitution test card (analysis.substitution);
   top-15 machines by lost theo in P (compute from ops.faults in P × machine's theo per available hour in P).
5. **players** (Q4): group filters (tier, age band, region multi-select or single select + All) — players months
   overlapping P (month idx whose month intersects P). KPIs: tracked players, tracked coin-in, players' net
   (payout − coin-in, shown as negative = players lost), theo, luck residual (net + theo), % of players ahead
   (net > 0, per player over the selected months). Lorenz curve (share of players vs share of theo, and vs share of
   net loss among losers) with top 1%/10% shares labelled. Histogram of per-player net (bins, clipped at ±$2,000 with
   overflow bins). Table by tier and by age band: players, coin-in, net, theo, comp cost, comp/theo.
   Responsible-gaming note from story.players.notes.
6. **comps** (Q5): daily points-per-comp-dollar line (analysis.comp.daily) with change-date marker; monthly
   reinvestment (comp cost / theo) bars; monthly comp cost bars; DiD card (estimate + CI, placebo) from
   analysis.comp; by-tier table.
7. **plan** (Q6): budget bar (spent per action vs kept, total $100,000); one card per action: qty, targets, cost,
   lead days, expected effect low/mid/high, assumptions, uncertainty, measurement, evidence links (clicking switches
   tab + sets filters). Rejected options table. Sensitivity table from plan.sensitivity.
8. **model**: k grid line (inner MAE vs k, log x); metrics table (model vs baselines; MAE, RMSE, Spearman, both
   targets); bootstrap CI card; holdout scatter predicted vs actual (model in blue, B_hw_rate in muted gray, y=x);
   decision table; Model B: actual vs forecasts line chart (train dimmed, test highlighted, vertical line at May 1),
   metrics table, events usable/unusable list.
9. **evidence**: claims.json as a table (claim → source → result → alternative tested → limitation, link to tab);
   method notes from story.evidence; AI-use disclosure from story.ai.

## Acceptance (do these and report)
1. Create a temporary `site/data/story.json`, `plan.json`, `claims.json` ONLY IF they do not exist (minimal dummy
   content, mark each with `"_dummy": true` at top level, since the analyst will overwrite them).
2. Add `site/check_site.py` (Python stdlib) that: starts `http.server` on port 8765 serving `site/`, fetches
   index.html, app.js, style.css and every data/*.json (status 200, valid JSON), and checks that index.html references
   only cdnjs.cloudflare.com as external script host. Run it, report output.
3. Add a node-free JS self-test: `site/app.js` exposes `window.__selftest()` that runs the shared computations for
   the full period and returns {nMachines, gmList: [ids], sumHW, sumTheo, leakIds}. Document in the report what it
   should return; the analyst will run it in a browser. Do not claim it passed unless you ran it.
4. Keep app.js readable (sections with comments). No minification.
