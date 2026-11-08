# Dashboard Royale (TAMU Datathon 2026) — session notes

Challenge: "Luck, location, or a leak?" — fictional 300-machine casino (The Gilded Ace), Jan–Jun 2025.
GM wants to replace the 10 lowest-earning machines. We decide which are truly bad. Guide: `GUIDE.md`.
User speaks Chinese → answer in Chinese. Code/specs in English.

## Layout
- `data-repo/` — clone of https://github.com/tamu-datathon-org/dashboard-royale (data lives HERE; the
  `dashboard-casino` repo named in the guide does not exist). Read-only, gitignored.
- `.venv/` — own venv (Py 3.12; duckdb 2.x → use `.fetchall()`, no fetchone/fetchmany). Never use root `.venv`.
- `pipeline/` — build_data → check_build → analysis → model → plan → make_appendix (run order, see README).
- `content/` — analyst-written dashboard text (story.json, claims.json); make_appendix copies them to site/data.
  DeepSeek once overwrote site/data/story.json with a dummy — always edit `content/`, never site/data/story.json.
- `site/` — static dashboard (index.html, app.js, style.css; Plotly 2.27.0 from cdnjs — 2.35.2 is NOT on cdnjs).
- `docs/` — WRITEUP.md (≤400 words, now 393), APPENDIX.md (generated), VIDEO_SCRIPT.md, SUBMISSION_CHECKLIST.md, evidence/.
- Git: repo `YahwehC/td26-dashboard-royale` (created by the parent session; private as of 12:55 Nov 7). Pages workflow in `.github/workflows/pages.yml`.

## Environment gotchas
- DeepSeek sandbox failed with `SetNamedSecurityInfoW ... Win32 5` until the folder got an explicit user ACE:
  `icacls <folder> /grant "<DOMAIN>\<user>:(F)"` (same ACE the project root has).
- pip in a fresh venv hung; `pip install --no-cache-dir --only-binary :all: ...` worked.
- Local preview: `.venv/Scripts/python -m http.server 8790 --directory site`.

## Key findings (all reproducible from pipeline/)
- GM's bottom-10 (lowest total house win): 9 in Back Forty (zone rate $12.4 vs 15.5–21.5/open h), 8 low-hold games
  (Royal Draw 95%, Comet Cash 92%), 3 partial exposure (M-1118, M-1120 retired; M-5076 installed May 13);
  machine index U 0.95–1.10 → none truly weak.
- Leak: M-1158 hit rate 38.6% vs 31.5% (z=+124), hold 3% vs 10%, luck −$36k.
- Exact luck variance: Σ bet² × payout_multiplier_variance; z SD ≈ 1.09 across machines (luck is ordinary).
- Walkway W-ENT-B40 closed Mar 3–Apr 6 (gaming days): B40/rest ratio 0.669 → 0.461 → 0.643; lost $163k theo.
- Downtime 5,021 h, $98.9k theo (0.42%); substitution ≈ +1% neighbour occupancy; Ridgeline 55% of loss;
  short-staffed shifts wait 2.0–2.6 h vs 0.6–0.7 h; −1.8 h per extra tech.
- Comps: May 1 points per comp $ 13.1 → 5.8; reinvestment 1.1% → 1.3%; DiD carded vs uncarded +2.8% [0.5, 5.2], placebo −0.8%.
- Players: 113,890 carded, net −$15.59M ≈ theo $15.49M; 13.6% ahead; top 10% = 66% of theo.
- Events: Super Bowl +24%, March Madness +20%, Winter Slot Tournament +19% (+$82.5k theo, no pull-forward), EDC +13%, Locals week +6.5%.

## Model (pipeline/model.py)
- A: theo/open h = Z[zone] × C[game] × W[weekday] × U[machine], IPF, U shrunk (k=20,000 by inner Jan–Feb→Mar–Apr),
  closure level for B40; quasi-Poisson interval (φ≈32). Holdout May–Jun: relative error 3.1% (model) vs 3.8% (own theo
  rate) vs 11.7% (own house win). Dollar MAE: model 1.26 vs theo-rate 1.06 (all over-forecast May–Jun slowdown) — report honestly.
  Decision test: GM list hold index 1.01, 0/10 true bottom; model list 0.90, 4/10.
- B: floor coin-in weekday model MAE $69k vs constant $218k; used as frozen counterfactual for the promo.

## Plan (pipeline/plan.py) — spend $23,700, keep $76,300
1. Inspect M-1158 $1,200 (+$5.8k). 2. Promo weekend $15,000 (+$27.5k/53k/78k). 3. Back Forty signs $7,500 (+$2.7k/10.6k/21.3k, break-even 2.8%).
Rejected (priced): lease-replace bottom-10, grave tech ($739 benefit), Ridgeline PM, machine swaps (only 1 pair pays in July; deferred to Aug), comp pilot (#4), 2nd promo.
Codex reviewed money math: 2 minor bugs fixed (move downtime valuation; comp change detection ratio of sums).

## Research / prior work (rule: research before building) — done Nov 7 after the build
No prior Dashboard Royale entry or open slot-floor dashboard to reuse; the 2024 TAMU 1st place
(github.com/Pranav379/Roni-s-Analytics, Streamlit) has nothing technical to copy. Sources confirm our method:
- casinomanagers.net/theoretical-hold-vs-actual-hold/ — actual-to-theoretical index (GGR/theo, volume-weighted),
  5 causes of a hold gap (luck, game-mix theo, jackpot accounting, meter fault, integrity), control bands not fixed %.
- casinomanagers.net/slot-machine-performance-metrics/ — availability %, lost theo = down h × comparable rate, peer-group median.
- calbizjournal.com/slot-machine-management — WPUPD and "house average" index.
- surveillanceasia.com glossary "actual hold" — z / chi-square vs theo (= our luck z + binomial hit test).
- slotmath.org volatility index — ±z·σ/√n band (= our exact Σbet²×var).
- Lucas & Kim, "Slot Floor Layout Strategy", UNLV GRRJ 29(1) — weak titles in good spots + popular in bad spots +21% t-win
  ⇒ swap ordering is empirical (consistent with deferring swaps).
- Lucas & Dunn 2005 (doi 10.1177/1096348004273427) — location + game "performance potential" explains 64% of unit volume
  (academic basis for zone × game × U).
- FunnelPlotR (nhs-r-community) — funnel plot with overdispersion limits → idea for a luck-vs-leak funnel chart.
Ideas to adopt: funnel/control-band chart, industry terms (actual-to-theo index, WPUPD, house-average index), availability %.

## Status (Nov 7, ~13:00)
- [x] Data, analysis, model, plan, dashboard (all 9 tabs checked in browser; period/zone/bank filters; mobile no overflow)
- [x] Write-up, appendix, video script, checklist
- [x] Pushed to private repo (push only, per parent). Funnel chart + chart-width fix + prior-work appendix section added after research.
- [ ] Make public + enable Pages: user said NOT yet (Nov 7, "still working") — keep private, no Devpost submit until told
- [x] Demo film (Nov 8, ~1:41, AI voice): `video/` adapted from build-a-dataset's pipeline. `script.json` (lines + shot + headline) → `voice.py`
  (edge-tts en-US-AndrewNeural → out/cues.json, voice.wav) → `capture.py` (dashboard screenshots from :8790, headless **Edge** via
  `channel="msedge"`; set TEMP/TMP to `video/out/tmp` or the sandbox blocks mkdtemp) → `render.py --stills ...` (writes beats.json) →
  `music.py` → `render.py` → `video/out/dashboard-royale-demo.mp4` (gitignored). Film = `video/index.html`, `renderAt(t)`.
- [ ] User: upload the video (YouTube unlisted / Devpost), fill Devpost
