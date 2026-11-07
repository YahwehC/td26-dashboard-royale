# Devpost submission checklist — Dashboard Royale

Deadline: hacking ends **Sun Nov 8 2026, 12:00 PM** (check the Devpost event page for the exact submission time).

| # | Item | Where | Status | Who |
|---|------|-------|--------|-----|
| 1 | Public interactive dashboard link | GitHub Pages: `https://yahwehc.github.io/td26-dashboard-royale/` (built from `site/`) | ready to deploy | **You**: make repo public + enable Pages (steps below) |
| 2 | Video walkthrough ≤ 2 min | `docs/VIDEO_SCRIPT.md` | script drafted | **You**: record (screen + voice), upload (YouTube unlisted or Devpost upload) |
| 3 | Write-up ≤ 400 words | `docs/WRITEUP.md` | drafted | You: paste into Devpost |
| 4 | One model vs simple baseline, time holdout | dashboard tab "Model" + `pipeline/model.py` + `docs/evidence/model_report.md` | done | — |
| 5 | All code / transformation steps | the same public repo (`pipeline/`, `site/`, `specs/`) | done | You: push |
| 6 | ≤ 3 priced action types | dashboard tab "Plan" + `site/data/plan.json` + write-up | done | — |
| 7 | AI-use disclosure | `docs/APPENDIX.md` (section "AI use") + dashboard tab "Evidence" | done | — |
| 8 | Claims & Evidence appendix (file or public link) | `docs/APPENDIX.md` → link `https://github.com/YahwehC/td26-dashboard-royale/blob/main/docs/APPENDIX.md` | done | You: put link in Devpost |
| 9 | Test the dashboard link in a private/incognito window | — | — | **You** |

## Publish steps (GitHub Pages, ~5 min)
The repo already exists: `https://github.com/YahwehC/td26-dashboard-royale` (currently **private**).
1. Push the latest commit (Claude does this once you approve).
2. github.com → repo → Settings → General → Danger Zone → **Change visibility → Public** (Devpost needs public code; free Pages needs a public repo).
3. Settings → Pages → Build and deployment → Source: **GitHub Actions**. The workflow `.github/workflows/pages.yml` deploys `site/` on every push to `main` (1–2 min; re-run it from the Actions tab after switching the source).
4. Open `https://yahwehc.github.io/td26-dashboard-royale/` in a private window; check the period presets, a zone + bank drill-down, and the Model and Plan tabs.

## Reproduce the numbers
```
python -m venv .venv && .venv\Scripts\python -m pip install duckdb pandas numpy scipy statsmodels
git clone --depth 1 https://github.com/tamu-datathon-org/dashboard-royale.git data-repo
.venv\Scripts\python pipeline\build_data.py
.venv\Scripts\python pipeline\analysis.py
.venv\Scripts\python pipeline\model.py
.venv\Scripts\python pipeline\plan.py
```
