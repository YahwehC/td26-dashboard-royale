# 005 — Audit every number in the narrative against the data

Goal: find every numeric claim in the human-written text that does not match the data. Judges grade "correct money math"
(30%), and we already found one wrong number ("top 10% of losers ≈ 80% of net losses"; the true value is 52.8%).
REPORT ONLY. Do not edit content/, docs/ or site/.

ROOT = `F:\CYH\projects\datathon\challenges\dashboard-royale`. Python: `ROOT\.venv\Scripts\python.exe` (duckdb, pandas, numpy available).
Raw data (read-only): `ROOT/data-repo/data/**.parquet`. The view names and paths are listed in `pipeline/q.py`
(e.g. `pp` = 3_guests/player_period, `md` = 2_machine_decision/machine_day). Generated outputs: `site/data/*.json`
(analysis.json, model.json, plan.json, core.json, players.json, ops.json) and `docs/evidence/*.md`.

## Files to audit (text only)
1. `content/story.json`: each tab's "answer", "notes" and any text fields (HTML tags inside strings are fine).
2. `content/claims.json`: fields claim, result, alternative, limitation.
3. `docs/WRITEUP.md`
4. `docs/VIDEO_SCRIPT.md`

## What to do
- Write `ROOT/pipeline/audit_claims.py`. It must:
  - extract every sentence that contains a number,
  - recompute that number from the parquet (DuckDB SQL) or read it from site/data/*.json / docs/evidence/*.md,
  - write `ROOT/docs/evidence/claim_audit.md` with a table: file | quoted text (≤ 20 words) | claimed | recomputed | source (SQL or json path) | status (OK / MISMATCH / NOT CHECKABLE).
- Tolerance: OK if it matches after the rounding used in the text (e.g. "$15.6M" vs 15,594,xxx → OK; "~6%" vs 6.4% → OK).
- Money rules: ratios are ratios of sums. Columns ending `_cents` are cents, `_usd` are dollars. Theo = coin-in × (1 − RTP).
  The gaming day runs 06:00–06:00.
- Player-level numbers come from `pp` aggregated over all months per player_id (sum tracked_net_usd, theo_usd, tracked_coin_in_usd).
- Do not "fix" a mismatch by changing the definition. Report it and give both definitions if the wording is ambiguous.
- Several numbers already exist in analysis.json / model.json / plan.json; reading them is fine, but at least spot-check
  10 of the money figures directly with SQL from the parquet.

## Acceptance
```
ROOT\.venv\Scripts\python.exe ROOT\pipeline\audit_claims.py
```
- runs in < 5 minutes, exit code 0
- `docs/evidence/claim_audit.md` exists, has ≥ 60 rows, and lists the MISMATCH rows first
- Your final report: the number of OK / MISMATCH / NOT CHECKABLE rows and the full list of MISMATCH rows (claimed vs recomputed).
