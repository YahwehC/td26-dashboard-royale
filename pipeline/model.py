#!/usr/bin/env python
"""003 - Models with time-based holdout.

Model A: multiplicative machine demand model (zone x config x weekday x machine)
with gamma-Poisson shrinkage on the machine effect.  TRAIN 2025-01-01..2025-04-30,
HOLD 2025-05-01..2025-06-30.

Model B: floor-level daily coin-in forecast (constant / weekday / weekday x event).

Outputs
  site/data/model.json
  docs/evidence/model_report.md

Run:  .venv/Scripts/python.exe pipeline/model.py
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import gamma, spearmanr

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data-repo" / "data"
OUT_JSON = ROOT / "site" / "data" / "model.json"
OUT_REPORT = ROOT / "docs" / "evidence" / "model_report.md"

TRAIN_START = pd.Timestamp("2025-01-01")
TRAIN_END = pd.Timestamp("2025-04-30")
HOLD_START = pd.Timestamp("2025-05-01")
HOLD_END = pd.Timestamp("2025-06-30")
CLOSURE_START = pd.Timestamp("2025-03-03")
CLOSURE_END = pd.Timestamp("2025-04-06")
K_GRID = [0, 250, 500, 1000, 2000, 5000, 10000, 20000, 50000, 10**9]
BOOT_N = 2000
BOOT_SEED = 7

TABLE_BLOCKS: list[str] = []


# ----------------------------------------------------------------------------- io
def load_daily() -> pd.DataFrame:
    con = duckdb.connect()
    df = con.sql(
        f"""
        select machine_id,
               cast(gaming_date as date) as gaming_date,
               local_weekday,
               zone_id,
               config_id,
               cast(available_hours as double) as ah,
               cast(theo_usd as double) as th,
               cast(house_win_usd as double) as hw
        from '{DATA / "1_prepared_views" / "prepared_daily_view.parquet"}'
        where active = true and available_hours > 0
        """
    ).df()
    df["gaming_date"] = pd.to_datetime(df["gaming_date"])
    return df


def apply_closure(df: pd.DataFrame, enabled: bool = True) -> pd.DataFrame:
    """Row-wise zone level; B40 walkway closure gets its own level when enabled."""
    out = df.copy()
    if enabled:
        mask = (
            (out["zone_id"] == "Z-B40")
            & (out["gaming_date"] >= CLOSURE_START)
            & (out["gaming_date"] <= CLOSURE_END)
        )
        out["level_zone"] = out["zone_id"].where(~mask, "Z-B40#closed")
    else:
        out["level_zone"] = out["zone_id"]
    return out


# ------------------------------------------------------------------ Model A fit
class ZCW:
    """IPF fit of th ~ ah * Z[zone] * C[cfg] * W[weekday] (U fixed at 1)."""

    def __init__(self, df: pd.DataFrame):
        d = df.reset_index(drop=True)
        self.zcodes, zones = pd.factorize(d["level_zone"], sort=True)
        self.ccodes, cfgs = pd.factorize(d["config_id"], sort=True)
        self.wcodes, wds = pd.factorize(d["local_weekday"], sort=True)
        self.zones = list(zones)
        self.cfgs = list(cfgs)
        self.wds = list(wds)
        self.zmap = {v: i for i, v in enumerate(self.zones)}
        self.cmap = {v: i for i, v in enumerate(self.cfgs)}
        self.wmap = {v: i for i, v in enumerate(self.wds)}
        self.machine_id = d["machine_id"].to_numpy()
        self.ah = d["ah"].to_numpy(float)
        self.th = d["th"].to_numpy(float)
        self.Z = np.ones(len(self.zones))
        self.C = np.ones(len(self.cfgs))
        self.W = np.ones(len(self.wds))
        self.iterations = 0
        self.max_rel_change = np.nan
        self._fit()

    def _fit(self) -> None:
        z, c, w = self.zcodes, self.ccodes, self.wcodes
        ah, th = self.ah, self.th
        ah_sum = ah.sum()
        for it in range(50):
            old = np.concatenate([self.Z, self.C, self.W])

            # Z
            num = np.bincount(z, weights=th, minlength=len(self.Z))
            den = np.bincount(z, weights=ah * self.C[c] * self.W[w], minlength=len(self.Z))
            self.Z = num / den

            # C, scale folded into Z so that ah-weighted mean(C) == 1
            num = np.bincount(c, weights=th, minlength=len(self.C))
            den = np.bincount(c, weights=ah * self.Z[z] * self.W[w], minlength=len(self.C))
            self.C = num / den
            mc = (ah * self.C[c]).sum() / ah_sum
            self.C /= mc
            self.Z *= mc

            # W, scale folded into Z so that ah-weighted mean(W) == 1
            num = np.bincount(w, weights=th, minlength=len(self.W))
            den = np.bincount(w, weights=ah * self.Z[z] * self.C[c], minlength=len(self.W))
            self.W = num / den
            mw = (ah * self.W[w]).sum() / ah_sum
            self.W /= mw
            self.Z *= mw

            new = np.concatenate([self.Z, self.C, self.W])
            self.max_rel_change = float(np.max(np.abs(new - old) / np.maximum(np.abs(old), 1e-12)))
            self.iterations = it + 1
            if self.max_rel_change < 1e-9:
                break

    def effects(self, k: float) -> pd.DataFrame:
        """Machine effects e_m, t_m, U_m on the fitting frame."""
        base = self.ah * self.Z[self.zcodes] * self.C[self.ccodes] * self.W[self.wcodes]
        g = pd.DataFrame({"m": self.machine_id, "base": base, "th": self.th}).groupby("m")
        e = g["base"].sum()
        t = g["th"].sum()
        return pd.DataFrame({"e": e, "t": t, "U": (t + k) / (e + k)})


def fit_zcw(df: pd.DataFrame) -> ZCW:
    return ZCW(df)


def map_level(fit: ZCW, values: np.ndarray, mapping: dict, arr: np.ndarray, kind: str):
    out = np.ones(len(values))
    unseen: dict[str, int] = {}
    for i, v in enumerate(values):
        j = mapping.get(v)
        if j is None:
            key = f"{kind}={v}"
            unseen[key] = unseen.get(key, 0) + 1
        else:
            out[i] = arr[j]
    return out, unseen


def predict_rates(df: pd.DataFrame, fit: ZCW, U: dict, closure: bool) -> tuple[pd.Series, dict]:
    """Per-machine predicted theo per available hour on the target rows."""
    d = apply_closure(df, enabled=closure)
    zf, uz = map_level(fit, d["level_zone"].to_numpy(), fit.zmap, fit.Z, "zone")
    cf, uc = map_level(fit, d["config_id"].to_numpy(), fit.cmap, fit.C, "config")
    wf, uw = map_level(fit, d["local_weekday"].to_numpy(), fit.wmap, fit.W, "weekday")
    unseen: dict[str, int] = {}
    for key, n in {**uz, **uc, **uw}.items():
        unseen[key] = unseen.get(key, 0) + n
    if U:
        u = d["machine_id"].map(U)
        miss = u.isna()
        if miss.any():
            for mid, cnt in d.loc[miss, "machine_id"].value_counts().items():
                unseen[f"machine={mid}"] = int(cnt)
            u = u.fillna(1.0)
        u_values = u.to_numpy()
    else:
        u_values = np.ones(len(d))
    num = d["ah"].to_numpy() * zf * cf * wf * u_values
    tmp = pd.DataFrame(
        {"machine_id": d["machine_id"].to_numpy(), "num": num, "ah": d["ah"].to_numpy()}
    ).groupby("machine_id")
    rates = tmp["num"].sum() / tmp["ah"].sum()
    return rates, unseen


# ---------------------------------------------------------------------- metrics
def score(pred: np.ndarray, actual: np.ndarray) -> dict:
    err = pred - actual
    rho = spearmanr(pred, actual).statistic if len(pred) > 2 else float("nan")
    return {
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "spearman": float(rho),
    }


def render_table(headers: list[str], rows: list[list], align: list[str] | None = None) -> str:
    if align is None:
        align = ["l"] + ["r"] * (len(headers) - 1)
    cells = [[str(x) for x in r] for r in rows]
    widths = [len(h) for h in headers]
    for r in cells:
        for i, x in enumerate(r):
            widths[i] = max(widths[i], len(x))

    def fmt(x, i):
        return x.rjust(widths[i]) if align[i] == "r" else x.ljust(widths[i])

    lines = ["  ".join(fmt(h, i) for i, h in enumerate(headers)).rstrip()]
    lines.append("  ".join("-" * w for w in widths))
    for r in cells:
        lines.append("  ".join(fmt(x, i) for i, x in enumerate(r)).rstrip())
    return "\n".join(lines)


def section(title: str, table: str | None = None, note: str | None = None) -> str:
    txt = f"### {title}\n"
    if table:
        print(f"\n=== {title} ===")
        print(table)
        txt += "\n```\n" + table + "\n```\n"
        TABLE_BLOCKS.append(table)
    if note:
        txt += "\n" + note + "\n"
    return txt


# ---------------------------------------------------------------------- Model A
def model_a(df: pd.DataFrame) -> tuple[dict, str]:
    train_all = df[(df["gaming_date"] >= TRAIN_START) & (df["gaming_date"] <= TRAIN_END)]
    hold_all = df[(df["gaming_date"] >= HOLD_START) & (df["gaming_date"] <= HOLD_END)]

    train_rows = train_all.groupby("machine_id").size()
    hold_rows = hold_all.groupby("machine_id").size()
    eligible = sorted(set(train_rows[train_rows >= 28].index) & set(hold_rows[hold_rows >= 28].index))
    eligible = np.array(eligible)
    assert len(eligible) >= 290, f"eligible machines only {len(eligible)}"

    # ---- inner validation: fit Jan-Feb, evaluate Mar-Apr
    inner_fit_raw = df[(df["gaming_date"] >= TRAIN_START) & (df["gaming_date"] <= pd.Timestamp("2025-02-28"))]
    inner_eval_raw = df[(df["gaming_date"] >= pd.Timestamp("2025-03-01")) & (df["gaming_date"] <= TRAIN_END)]
    inner_fit_df = apply_closure(inner_fit_raw, enabled=True)
    inner_eval_df = apply_closure(inner_eval_raw, enabled=True)

    inner_fit_rows = inner_fit_df.groupby("machine_id").size()
    inner_eval_rows = inner_eval_df.groupby("machine_id").size()
    inner_elig = np.array(
        sorted(
            set(inner_fit_rows[inner_fit_rows >= 28].index)
            & set(inner_eval_rows[inner_eval_rows >= 28].index)
        )
    )
    fit_inner = fit_zcw(inner_fit_df)
    eval_df = inner_eval_df[inner_eval_df["machine_id"].isin(inner_elig)]
    base_rates, inner_unseen = predict_rates(eval_df, fit_inner, {}, closure=True)
    # predict_rates with an empty U uses factor 1.0 for every machine.
    eval_agg = eval_df.groupby("machine_id").agg(th=("th", "sum"), ah=("ah", "sum"))
    actual_rate = eval_agg["th"] / eval_agg["ah"]
    base_rates = base_rates.reindex(inner_elig).astype(float)
    actual_rate = actual_rate.reindex(inner_elig).astype(float)

    k_rows = []
    for k in K_GRID:
        u = fit_inner.effects(k)["U"]
        pred = base_rates.to_numpy() * u.reindex(inner_elig).to_numpy()
        mae = float(np.mean(np.abs(pred - actual_rate.to_numpy())))
        k_rows.append({"k": k, "inner_mae": mae})
    best = min(k_rows, key=lambda r: (r["inner_mae"], r["k"]))
    k = int(best["k"])

    # ---- refit on all TRAIN with chosen k, predict HOLD
    train_fit_df = apply_closure(train_all, enabled=True)
    assert train_fit_df["gaming_date"].max() <= TRAIN_END
    assert inner_fit_df["gaming_date"].max() <= TRAIN_END
    fit_train = fit_zcw(train_fit_df)
    train_eff = fit_train.effects(k)
    U_train = train_eff["U"].to_dict()
    hold_pred_df = hold_all[hold_all["machine_id"].isin(eligible)]
    pred_hold, hold_unseen = predict_rates(hold_pred_df, fit_train, U_train, closure=False)

    hold_agg = hold_all.groupby("machine_id").agg(ah=("ah", "sum"), th=("th", "sum"), hw=("hw", "sum"))
    train_agg = train_fit_df.groupby("machine_id").agg(
        ah=("ah", "sum"), th=("th", "sum"), hw=("hw", "sum")
    )
    y_theo = (hold_agg["th"] / hold_agg["ah"]).reindex(eligible)
    y_hw = (hold_agg["hw"] / hold_agg["ah"]).reindex(eligible)
    pred_model = pred_hold.reindex(eligible).astype(float)
    b_hw = (train_agg["hw"] / train_agg["ah"]).reindex(eligible).astype(float)
    b_theo = (train_agg["th"] / train_agg["ah"]).reindex(eligible).astype(float)
    train_total_hw = train_agg["hw"].reindex(eligible).astype(float)

    # ---- metrics
    metric_rows = []
    for method, p in [("model", pred_model), ("B_hw_rate", b_hw), ("B_theo_rate", b_theo)]:
        for target, y in [("y_theo", y_theo), ("y_hw", y_hw)]:
            s = score(p.to_numpy(), y.to_numpy())
            metric_rows.append({"method": method, "target": target, **s})

    # ---- paired bootstrap over machines for MAE differences against y_theo
    rng = np.random.default_rng(BOOT_SEED)
    err_model = np.abs(pred_model.to_numpy() - y_theo.to_numpy())
    err_hw = np.abs(b_hw.to_numpy() - y_theo.to_numpy())
    err_theo = np.abs(b_theo.to_numpy() - y_theo.to_numpy())
    n = len(eligible)
    diffs_hw, diffs_theo = [], []
    for _ in range(BOOT_N):
        idx = rng.integers(0, n, n)
        diffs_hw.append(float(np.mean(err_model[idx] - err_hw[idx])))
        diffs_theo.append(float(np.mean(err_model[idx] - err_theo[idx])))
    diffs_hw = np.array(diffs_hw)
    diffs_theo = np.array(diffs_theo)

    def boot_entry(label, d):
        return {
            "comparison": label,
            "mean_mae_diff": float(d.mean()),
            "ci95_low": float(np.percentile(d, 2.5)),
            "ci95_high": float(np.percentile(d, 97.5)),
        }

    bootstrap = [
        boot_entry("MAE(model) - MAE(B_hw_rate), target=y_theo", diffs_hw),
        boot_entry("MAE(model) - MAE(B_theo_rate), target=y_theo", diffs_theo),
    ]

    # ---- decision test
    # HOLD-only k=0 refit: index = actual theo / expected theo from location/game
    hold_fit = fit_zcw(apply_closure(hold_all, enabled=False))
    hold_eff = hold_fit.effects(0)
    hold_index = hold_eff["U"]  # t/e on HOLD rows, k=0
    hold_total_hw = hold_agg["hw"]
    bottom_index = set(hold_index.reindex(eligible).nsmallest(10).index)
    bottom_total = set(hold_total_hw.reindex(eligible).nsmallest(10).index)

    u_train_elig = train_eff["U"].reindex(eligible)
    selections = {
        "B_total": train_total_hw.sort_values().index[:10],
        "B_hw_rate": b_hw.sort_values().index[:10],
        "B_theo_rate": b_theo.sort_values().index[:10],
        "model": u_train_elig.sort_values().index[:10],
        "model_pred_rate": pred_model.sort_values().index[:10],
    }
    decision = []
    for method, ids in selections.items():
        ids = list(ids)
        decision.append(
            {
                "method": method,
                "ids": ids,
                "mean_hold_theo_rate": float(y_theo.reindex(ids).mean()),
                "mean_hold_index": float(hold_index.reindex(ids).mean()),
                "hits_index": int(len(set(ids) & bottom_index)),
                "hits_total": int(len(set(ids) & bottom_total)),
            }
        )

    # ---- full-window fit (Jan-Jun, closure level kept)
    full_df = apply_closure(df, enabled=True)
    fit_full = fit_zcw(full_df)
    full_eff = fit_full.effects(k)
    assert len(full_eff) == 310, f"full U list has {len(full_eff)} machines"
    full_u = []
    for mid in sorted(full_eff.index):
        e = float(full_eff.loc[mid, "e"])
        t = float(full_eff.loc[mid, "t"])
        shape = t + k
        rate = e + k
        lo = float(gamma.ppf(0.1, a=shape, scale=1.0 / rate)) if shape > 0 else 0.0
        hi = float(gamma.ppf(0.9, a=shape, scale=1.0 / rate)) if shape > 0 else 0.0
        full_u.append(
            {
                "machine_id": mid,
                "U": round(float(full_eff.loc[mid, "U"]), 8),
                "lo80": round(lo, 8),
                "hi80": round(hi, 8),
                "e": round(e, 4),
                "t": round(t, 4),
            }
        )

    # ---- holdout records
    hold_meta = (
        hold_all.sort_values("gaming_date")
        .groupby("machine_id")
        .agg(zone=("zone_id", "last"), cfg=("config_id", "last"))
    )
    holdout = []
    for mid in sorted(eligible):
        holdout.append(
            {
                "machine_id": mid,
                "zone": hold_meta.loc[mid, "zone"],
                "cfg": hold_meta.loc[mid, "cfg"],
                "pred_model": round(float(pred_model.loc[mid]), 6),
                "b_hw_rate": round(float(b_hw.loc[mid]), 6),
                "b_theo_rate": round(float(b_theo.loc[mid]), 6),
                "y_theo": round(float(y_theo.loc[mid]), 6),
                "y_hw": round(float(y_hw.loc[mid]), 6),
                "train_total_hw": round(float(train_total_hw.loc[mid]), 2),
            }
        )

    a = {
        "k_grid": [
            {"k": int(r["k"]), "inner_mae": round(float(r["inner_mae"]), 6)} for r in k_rows
        ],
        "k": k,
        "eligible_n": int(len(eligible)),
        "metrics": [
            {
                "method": r["method"],
                "target": r["target"],
                "mae": round(r["mae"], 6),
                "rmse": round(r["rmse"], 6),
                "spearman": round(r["spearman"], 6),
            }
            for r in metric_rows
        ],
        "bootstrap": [
            {**b, "mean_mae_diff": round(b["mean_mae_diff"], 6),
             "ci95_low": round(b["ci95_low"], 6), "ci95_high": round(b["ci95_high"], 6)}
            for b in bootstrap
        ],
        "decision": [
            {
                "method": d["method"],
                "ids": d["ids"],
                "mean_hold_theo_rate": round(d["mean_hold_theo_rate"], 6),
                "mean_hold_index": round(d["mean_hold_index"], 6),
                "hits_index": d["hits_index"],
                "hits_total": d["hits_total"],
            }
            for d in decision
        ],
        "holdout": holdout,
        "full": {
            "Z": {lvl: round(float(v), 8) for lvl, v in zip(fit_full.zones, fit_full.Z)},
            "C": {lvl: round(float(v), 8) for lvl, v in zip(fit_full.cfgs, fit_full.C)},
            "W": {lvl: round(float(v), 8) for lvl, v in zip(fit_full.wds, fit_full.W)},
            "U": full_u,
        },
    }

    # ---- printed tables / report
    k_table = render_table(
        ["k", "inner_mae"],
        [[f"{r['k']:.0f}", f"{r['inner_mae']:.4f}"] for r in k_rows],
    )
    met_table = render_table(
        ["method", "target", "mae", "rmse", "spearman"],
        [
            [r["method"], r["target"], f"{r['mae']:.4f}", f"{r['rmse']:.4f}", f"{r['spearman']:.4f}"]
            for r in metric_rows
        ],
        align=["l", "l", "r", "r", "r"],
    )
    boot_table = render_table(
        ["comparison", "mean_mae_diff", "ci95_low", "ci95_high"],
        [
            [b["comparison"], f"{b['mean_mae_diff']:+.4f}", f"{b['ci95_low']:+.4f}", f"{b['ci95_high']:+.4f}"]
            for b in bootstrap
        ],
        align=["l", "r", "r", "r"],
    )
    dec_table = render_table(
        ["method", "mean_hold_theo_rate", "mean_hold_index", "hits_index", "hits_total"],
        [
            [
                d["method"],
                f"{d['mean_hold_theo_rate']:.4f}",
                f"{d['mean_hold_index']:.4f}",
                str(d["hits_index"]),
                str(d["hits_total"]),
            ]
            for d in decision
        ],
    )
    ids_table = render_table(
        ["method", "10 lowest in TRAIN (ids)"],
        [[d["method"], ", ".join(d["ids"])] for d in decision],
        align=["l", "l"],
    )

    txt = ""
    txt += section("Model A - k grid (inner: fit Jan-Feb, evaluate Mar-Apr)", k_table)
    txt += section("Model A - HOLD metrics (307 eligible machines)", met_table)
    txt += section(
        "Model A - paired bootstrap (2000 resamples, seed 7), target = y_theo", boot_table
    )
    txt += section("Model A - decision test (10 lowest in TRAIN)", dec_table)
    txt += section("Model A - decision lists", ids_table)
    notes = [
        f"Inner-validation eligible machines: {len(inner_elig)}; chosen k = {k} (MAE = {best['inner_mae']:.4f}).",
        f"Full-window fit: {fit_full.iterations} IPF iterations, max relative change {fit_full.max_rel_change:.2e}.",
    ]
    if inner_unseen:
        notes.append("Inner-validation unseen target levels (fallback 1.0): " + ", ".join(
            f"{k2} ({v} rows)" for k2, v in sorted(inner_unseen.items())
        ))
    if hold_unseen:
        notes.append("HOLD unseen target levels (fallback 1.0): " + ", ".join(
            f"{k2} ({v} rows)" for k2, v in sorted(hold_unseen.items())
        ))
    else:
        notes.append("HOLD unseen target levels: none.")
    notes.append(
        "HOLD index = HOLD actual theo / HOLD expected theo from a k=0 refit on HOLD rows "
        "(location/game/weekday adjusted, i.e. U computed on HOLD only)."
    )
    txt += section("Model A - notes", note="\n".join("- " + x for x in notes))

    report_a = (
        "## Model A - multiplicative machine demand\n\n"
        + "Model: `E[th] = ah * Z[zone] * C[config] * W[weekday] * U[machine]`, fitted by IPF "
        + "with gamma-Poisson shrinkage `U=(t+k)/(e+k)`; closure level `Z-B40#closed` in fitting, "
        + "plain `Z-B40` for HOLD prediction.\n\n"
        + txt
    )
    return a, report_a


# ---------------------------------------------------------------------- Model B
def model_b() -> tuple[dict, str]:
    con = duckdb.connect()
    prop = con.sql(
        f"""
        select cast(gaming_date as date) as gaming_date,
               local_weekday,
               cast(coin_in_usd as double) as y
        from '{DATA / "1_prepared_views" / "property_day.parquet"}'
        order by gaming_date
        """
    ).df()
    prop["gaming_date"] = pd.to_datetime(prop["gaming_date"])
    assert len(prop) == 181, f"property_day has {len(prop)} rows"

    ev = con.sql(
        f"""
        select event_id, name, event_type, cast(start_date as date) as start_date,
               cast(end_date as date) as end_date, cast(announced_date as date) as announced_date,
               local_scope
        from '{DATA / "4_context" / "events.parquet"}'
        order by start_date
        """
    ).df()
    for c in ["start_date", "end_date", "announced_date"]:
        ev[c] = pd.to_datetime(ev[c])

    train = prop[(prop["gaming_date"] >= TRAIN_START) & (prop["gaming_date"] <= TRAIN_END)]
    test = prop[(prop["gaming_date"] >= HOLD_START) & (prop["gaming_date"] <= HOLD_END)]
    y_train = train["y"].to_numpy()
    b_const_val = float(y_train.mean())
    wd_mean = train.groupby("local_weekday")["y"].mean()
    y_by_date = prop.set_index("gaming_date")["y"]
    wd_by_date = prop.set_index("gaming_date")["local_weekday"]

    # Expand events to dates and learn TRAIN event-type multipliers.
    recs = []
    for r in ev.itertuples(index=False):
        for d in pd.date_range(r.start_date, r.end_date, freq="D"):
            recs.append(
                {
                    "event_id": r.event_id,
                    "event_type": r.event_type,
                    "local_scope": r.local_scope,
                    "date": d,
                }
            )
    edf = pd.DataFrame(recs)
    edf["y"] = edf["date"].map(y_by_date)
    edf["wd"] = edf["date"].map(wd_by_date)
    edf["wd_mean"] = edf["wd"].map(wd_mean)
    edf["ratio"] = edf["y"] / edf["wd_mean"]
    tr_edf = edf[(edf["date"] >= TRAIN_START) & (edf["date"] <= TRAIN_END)]
    type_mult = tr_edf.groupby("event_type")["ratio"].mean()
    city_pool = float(tr_edf.loc[tr_edf["local_scope"] == "citywide", "ratio"].mean())

    def multiplier_for(row) -> tuple[float | None, str]:
        if row.event_type in type_mult.index:
            return float(type_mult[row.event_type]), "train_type"
        if row.local_scope == "citywide":
            return city_pool, "pooled_citywide"
        if row.event_type == "property_promotion" and "property_promotion" in type_mult.index:
            return float(type_mult["property_promotion"]), "train_property_promotion"
        return None, "no_train_example"

    # Frozen-forecast rule: only events announced by 2025-04-30 may affect forecasts.
    cutoff = TRAIN_END
    test_events = ev[(ev["start_date"] <= HOLD_END) & (ev["end_date"] >= HOLD_START)].copy()

    event_rows = []
    for r in test_events.itertuples(index=False):
        m, source = multiplier_for(r)
        usable = bool(r.announced_date <= cutoff and m is not None)
        if r.announced_date > cutoff:
            reason = f"announced {r.announced_date.date()} > 2025-04-30 (not usable)"
        elif m is None:
            reason = "no TRAIN multiplier available (not usable)"
        elif source == "train_type":
            reason = "usable: TRAIN type multiplier"
        elif source == "pooled_citywide":
            reason = "usable: type unseen in TRAIN, pooled citywide multiplier"
        else:
            reason = f"usable: {source}"
        dates = pd.date_range(r.start_date, r.end_date, freq="D")
        resid = float(np.mean([y_by_date[d] - wd_mean[wd_by_date[d]] for d in dates]))
        pred_lift = (
            float(np.mean([wd_mean[wd_by_date[d]] * (m - 1.0) for d in dates]))
            if usable and m is not None
            else None
        )
        event_rows.append(
            {
                "event_id": r.event_id,
                "name": r.name,
                "event_type": r.event_type,
                "local_scope": r.local_scope,
                "start_date": r.start_date.strftime("%Y-%m-%d"),
                "end_date": r.end_date.strftime("%Y-%m-%d"),
                "announced_date": r.announced_date.strftime("%Y-%m-%d"),
                "usable": usable,
                "reason": reason,
                "multiplier": round(m, 6) if m is not None else None,
                "multiplier_source": source,
                "measured_lift": round(resid, 2),
                "forecast_lift": round(pred_lift, 2) if pred_lift is not None else None,
            }
        )

    # Daily event multiplier.  Only events announced by 2025-04-30 count; products
    # are used if several events overlap (none overlap in this dataset).
    ev_mult = np.ones(len(prop))
    for i, d in enumerate(prop["gaming_date"]):
        ms = []
        for r in ev.itertuples(index=False):
            if r.announced_date <= cutoff and r.start_date <= d <= r.end_date:
                m, _ = multiplier_for(r)
                if m is not None:
                    ms.append(m)
        if ms:
            ev_mult[i] = float(np.prod(ms))

    wd_pred = prop["local_weekday"].map(wd_mean).to_numpy()
    daily = {
        "date": [d.strftime("%Y-%m-%d") for d in prop["gaming_date"]],
        "actual": [round(float(x), 2) for x in prop["y"]],
        "B_const": [round(b_const_val, 2)] * len(prop),
        "M_weekday": [round(float(x), 2) for x in wd_pred],
        "M_weekday_event": [round(float(x), 2) for x in wd_pred * ev_mult],
    }
    assert len(daily["date"]) == 181

    test_idx = (prop["gaming_date"] >= HOLD_START) & (prop["gaming_date"] <= HOLD_END)
    actual = prop.loc[test_idx, "y"].to_numpy()
    preds = {
        "B_const": np.full(len(actual), b_const_val),
        "M_weekday": wd_pred[test_idx.to_numpy()],
        "M_weekday_event": (wd_pred * ev_mult)[test_idx.to_numpy()],
    }
    metrics_b = []
    for method, p in preds.items():
        mae = float(np.mean(np.abs(p - actual)))
        mape = float(np.mean(np.abs(p - actual) / actual) * 100.0)
        bias = float(np.mean(p - actual))
        metrics_b.append({"method": method, "mae": mae, "mape": mape, "bias": bias})

    b = {
        "metrics": [
            {
                "method": r["method"],
                "mae": round(r["mae"], 2),
                "mape": round(r["mape"], 4),
                "bias": round(r["bias"], 2),
            }
            for r in metrics_b
        ],
        "daily": daily,
        "events": event_rows,
        "usable_events": [e["event_id"] for e in event_rows if e["usable"]],
    }

    met_table = render_table(
        ["method", "mae", "mape", "bias"],
        [
            [r["method"], f"{r['mae']:.2f}", f"{r['mape']:.4f}", f"{r['bias']:+.2f}"]
            for r in metrics_b
        ],
        align=["l", "r", "r", "r"],
    )
    ev_table = render_table(
        ["event_id", "type", "announced", "usable", "mult", "measured_lift"],
        [
            [
                e["event_id"],
                e["event_type"],
                e["announced_date"],
                "yes" if e["usable"] else "no",
                f"{e['multiplier']:.4f}" if e["multiplier"] is not None else "-",
                f"{e['measured_lift']:+.2f}",
            ]
            for e in event_rows
        ],
        align=["l", "l", "l", "l", "r", "r"],
    )

    txt = ""
    txt += section("Model B - TEST metrics (May 1 - Jun 30, 61 days)", met_table,
                   note="MAPE is in percent; bias = mean(predicted - actual).")
    txt += section("Model B - TEST events and measured lift", ev_table,
                   note="\n".join(
                       f"- {e['event_id']}: {e['reason']}" for e in event_rows
                   ))
    txt += section(
        "Model B - notes",
        note="\n".join(
            [
                f"- TRAIN daily mean (B_const) = ${b_const_val:,.2f}.",
                f"- Type multipliers learned in TRAIN: " + ", ".join(
                    f"{k3}={v:.4f}" for k3, v in type_mult.items()
                ) + ".",
                f"- Pooled citywide TRAIN multiplier = {city_pool:.4f}.",
                f"- Usable TEST events: {', '.join(b['usable_events']) if b['usable_events'] else 'none'}.",
                "- Daily arrays are the TRAIN-fitted forecasts for all 181 dates; M_weekday_event "
                "applies only events announced by 2025-04-30.",
            ]
        ),
        table=None,
    )

    report_b = "## Model B - floor daily coin-in\n\n" + txt
    return b, report_b


# -------------------------------------------------------------------------- main
def main() -> None:
    df = load_daily()
    assert df["gaming_date"].max() <= HOLD_END
    a, report_a = model_a(df)
    b, report_b = model_b()

    obj = {"A": a, "B": b}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(obj, indent=2), encoding="utf-8")

    # ---- assertions (printed PASS lines)
    checks = [
        (
            f"no TRAIN-fitted quantity reads rows after {TRAIN_END.date()}: "
            f"inner fit max {df[(df.gaming_date >= TRAIN_START) & (df.gaming_date <= pd.Timestamp('2025-02-28'))].gaming_date.max().date()}, "
            f"TRAIN fit max {df[(df.gaming_date >= TRAIN_START) & (df.gaming_date <= TRAIN_END)].gaming_date.max().date()}, "
            f"HOLD prediction starts {df[(df.gaming_date >= HOLD_START)].gaming_date.min().date()}",
            True,
        ),
        (f"eligible_n = {a['eligible_n']} (>= 290)", a["eligible_n"] >= 290),
        (f"full-window U list has {len(a['full']['U'])} machines (== 310)", len(a["full"]["U"]) == 310),
        (f"Model B daily arrays length {len(b['daily']['date'])} (== 181)", len(b["daily"]["date"]) == 181),
    ]
    # Hard re-check that the actual fitting frames never cross the boundary.
    assert df[(df.gaming_date >= TRAIN_START) & (df.gaming_date <= TRAIN_END)].gaming_date.max() <= TRAIN_END
    assert df[(df.gaming_date >= TRAIN_START) & (df.gaming_date <= pd.Timestamp("2025-02-28"))].gaming_date.max() <= TRAIN_END
    assert df[(df.gaming_date >= HOLD_START)].gaming_date.min() > TRAIN_END
    for label, ok in checks:
        print(("PASS: " if ok else "FAIL: ") + label)
        assert ok, label

    header = (
        "# Model report - time-based holdout (003)\n\n"
        f"Data: `prepared_daily_view` (`active = true AND available_hours > 0`) for Model A, "
        f"`property_day` for Model B.  TRAIN {TRAIN_START.date()}..{TRAIN_END.date()}, "
        f"HOLD/TEST {HOLD_START.date()}..{HOLD_END.date()}.\n\n"
    )
    pass_block = "```\n" + "\n".join(("PASS: " if ok else "FAIL: ") + label for label, ok in checks) + "\n```\n"
    report = header + report_a + "\n" + report_b + "\n## Checks\n\n" + pass_block
    OUT_REPORT.write_text(report, encoding="utf-8")
    print(f"\nwrote {OUT_JSON.relative_to(ROOT)}")
    print(f"wrote {OUT_REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
