# Luck, Location, or a Leak? — Dashboard Royale (TAMU Datathon 2026)

Interactive dashboard for The Gilded Ace (a fictional 300-machine casino, Jan–Jun 2025): should the GM replace the
10 lowest-earning slot machines? Short answer: **no** — they are victims of location, low-hold game math, short
exposure and luck; one machine (M-1158) shows a payout anomaly to inspect. Full reasoning in the dashboard.

- **Dashboard:** `site/` (static HTML + JS + Plotly, no server). Live: GitHub Pages link in the Devpost entry.
- **Write-up:** [`docs/WRITEUP.md`](docs/WRITEUP.md) · **Claims & Evidence appendix + AI disclosure:** [`docs/APPENDIX.md`](docs/APPENDIX.md)
- **Evidence reports:** [`docs/evidence/`](docs/evidence/) (analysis, model validation, budget plan)

## Reproduce
Requires Python 3.11+.
```
git clone --depth 1 https://github.com/tamu-datathon-org/dashboard-royale.git data-repo
python -m venv .venv
.venv\Scripts\python -m pip install duckdb pandas numpy scipy statsmodels      # (macOS/Linux: .venv/bin/python)
.venv\Scripts\python pipeline\build_data.py      # parquet -> site/data/core.json, players.json, ops.json
.venv\Scripts\python pipeline\check_build.py     # reconciles totals with property_day
.venv\Scripts\python pipeline\analysis.py        # downtime, substitution, staffing, closure, comps, events
.venv\Scripts\python pipeline\model.py           # Model A (machine demand) + Model B (floor forecast), time holdout
.venv\Scripts\python pipeline\plan.py            # $100k plan priced from action_catalog
.venv\Scripts\python pipeline\make_appendix.py   # docs/APPENDIX.md + dashboard text
cd site && python -m http.server 8000            # open http://localhost:8000
```

## Layout
| Path | What |
|---|---|
| `pipeline/` | all transformations (DuckDB + pandas); `q.py` is an ad-hoc SQL helper used while exploring |
| `site/` | the dashboard; `site/data/*.json` are generated |
| `content/` | analyst-written text shown in the dashboard (`story.json`, `claims.json`) |
| `specs/` | the task specifications given to the AI coding assistant |
| `docs/` | write-up, appendix, video script, submission checklist |

Data: TAMU Datathon "Dashboard Royale" release 0.9.0-draft (synthetic casino data; `4_context/real_sources` is real public data from LVCVA, NOAA and the Missouri Gaming Commission).
