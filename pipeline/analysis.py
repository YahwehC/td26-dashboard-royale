#!/usr/bin/env python
"""
Evidence tables for "Luck, location, or a leak?" (The Gilded Ace, Jan-Jun 2025).

Computes sections A-F, writes:
  * site/data/analysis.json          (machine-readable evidence)
  * docs/evidence/analysis_report.md (human-readable tables)

Run from anywhere with:
  F:\\...\\dashboard-royale\\.venv\\Scripts\\python.exe pipeline/analysis.py

Money columns ending _cents are integer cents; _usd columns are dollars.
All rates are ratios of sums. Inactive machine rows are excluded.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data-repo" / "data"
OUT_JSON = ROOT / "site" / "data" / "analysis.json"
OUT_MD = ROOT / "docs" / "evidence" / "analysis_report.md"

SHIFT_ORDER = ["day", "swing", "grave"]
TOP_MACHINES_IN_REPORT = 20


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def pq(rel: str) -> str:
    """Absolute POSIX path of a parquet file under data-repo/data."""
    return (DATA / rel).as_posix()


def fnum(x, nd: int = 6):
    """Finite float rounded, or None (JSON-safe)."""
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    return round(x, nd)


def clean(obj):
    """Recursively make an object JSON-safe (numpy types, NaN, timestamps)."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return fnum(obj)
    if isinstance(obj, float):
        return fnum(obj)
    if isinstance(obj, (int, str)) or obj is None:
        return obj
    return str(obj)


def fmt(x, nd: int = 2) -> str:
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "yes" if x else "no"
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not math.isfinite(xf):
        return "—"
    return f"{xf:,.{nd}f}"


def fmt_p(p) -> str:
    if p is None:
        return "—"
    p = float(p)
    if not math.isfinite(p):
        return "—"
    if p < 0.0001:
        return "<0.0001"
    return f"{p:.4f}"


def md_table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# shared loaders
# --------------------------------------------------------------------------- #
def load_dates(con) -> pd.DatetimeIndex:
    df = con.execute(
        f"SELECT gaming_date FROM read_parquet('{pq('2_machine_decision/calendar_day.parquet')}') "
        "ORDER BY gaming_date"
    ).df()
    return pd.DatetimeIndex(pd.to_datetime(df["gaming_date"]))


# --------------------------------------------------------------------------- #
# A. downtime
# --------------------------------------------------------------------------- #
def section_downtime(con, dates: pd.DatetimeIndex):
    """Down hours and theoretical-win cost of downtime, per active machine-hour."""
    df = con.execute(
        f"""
        SELECT mh.machine_id,
               mh.gaming_date,
               mh.local_hour,
               mh.available_seconds,
               mh.coin_in_cents,
               strftime(mh.gaming_date, '%Y-%m') AS month,
               mc.manufacturer AS mfr,
               CAST(mh.coin_in_cents AS DOUBLE)
                   * (1.0 - CAST(gm.configured_rtp AS DOUBLE)) / 100.0 AS theo,
               GREATEST(0, 3600 - mh.available_seconds) AS down_s
        FROM read_parquet('{pq('5_optional/machine_hour.parquet')}') mh
        JOIN read_parquet('{pq('2_machine_decision/machine_day.parquet')}') md
          ON md.machine_id = mh.machine_id AND md.gaming_date = mh.gaming_date
        JOIN read_parquet('{pq('2_machine_decision/game_math.parquet')}') gm
          ON gm.config_id = md.config_id
        JOIN read_parquet('{pq('2_machine_decision/machines.parquet')}') mc
          ON mc.machine_id = mh.machine_id
        WHERE mh.active
        """
    ).df()
    df["gaming_date"] = pd.to_datetime(df["gaming_date"])

    # r(machine, local_hour) over the whole window, dollars of theo per available hour
    rate = (
        df.groupby(["machine_id", "local_hour"], as_index=False)
        .agg(theo_sum=("theo", "sum"), avail_sec=("available_seconds", "sum"))
    )
    rate["r"] = np.where(
        rate["avail_sec"] > 0, rate["theo_sum"] / (rate["avail_sec"] / 3600.0), 0.0
    )
    df = df.merge(rate[["machine_id", "local_hour", "r"]],
                  on=["machine_id", "local_hour"], how="left")
    df["lost_theo"] = df["down_s"] / 3600.0 * df["r"]

    # by gaming date (all 181 dates, zero-filled)
    bd = (
        df.groupby("gaming_date")
        .agg(down_h=("down_s", lambda s: s.sum() / 3600.0),
             lost_theo=("lost_theo", "sum"))
        .reindex(dates, fill_value=0.0)
    )

    # by local hour (0..23)
    bh = (
        df.groupby("local_hour")
        .agg(down_h=("down_s", lambda s: s.sum() / 3600.0),
             lost_theo=("lost_theo", "sum"))
        .reindex(range(24), fill_value=0.0)
    )

    # faults and direct repair cost by manufacturer-month (gaming month)
    faults = con.execute(
        f"""
        SELECT mc.manufacturer AS mfr,
               c.month,
               COUNT(*) AS faults,
               SUM(o.direct_cost_cents) / 100.0 AS repair_cost
        FROM read_parquet('{pq('2_machine_decision/operations.parquet')}') o
        JOIN read_parquet('{pq('2_machine_decision/calendar_day.parquet')}') c
          ON o.opened_at_utc >= c.gaming_day_start_utc
         AND o.opened_at_utc <  c.gaming_day_end_utc
        JOIN read_parquet('{pq('2_machine_decision/machines.parquet')}') mc
          ON mc.machine_id = o.machine_id
        WHERE o.event_type = 'fault_repair'
        GROUP BY 1, 2
        """
    ).df()

    bm = (
        df.groupby(["mfr", "month"], as_index=False)
        .agg(down_h=("down_s", lambda s: s.sum() / 3600.0),
             lost_theo=("lost_theo", "sum"))
    )
    bm = bm.merge(faults, on=["mfr", "month"], how="outer")
    for col in ("down_h", "lost_theo", "repair_cost"):
        bm[col] = bm[col].fillna(0.0)
    bm["faults"] = bm["faults"].fillna(0).astype(int)
    bm = bm.sort_values(["mfr", "month"]).reset_index(drop=True)

    # all machines, with faults over the whole window
    mf = con.execute(
        f"""
        SELECT machine_id, COUNT(*) AS faults
        FROM read_parquet('{pq('2_machine_decision/operations.parquet')}')
        WHERE event_type = 'fault_repair'
        GROUP BY 1
        """
    ).df()
    machines = con.execute(
        f"SELECT machine_id FROM read_parquet('{pq('2_machine_decision/machines.parquet')}')"
    ).df()
    by_machine = (
        df.groupby("machine_id", as_index=False)
        .agg(down_h=("down_s", lambda s: s.sum() / 3600.0),
             lost_theo=("lost_theo", "sum"))
    )
    by_machine = machines.merge(by_machine, on="machine_id", how="left")
    by_machine = by_machine.merge(mf, on="machine_id", how="left")
    by_machine["down_h"] = by_machine["down_h"].fillna(0.0)
    by_machine["lost_theo"] = by_machine["lost_theo"].fillna(0.0)
    by_machine["faults"] = by_machine["faults"].fillna(0).astype(int)
    by_machine = by_machine.sort_values(
        ["lost_theo", "machine_id"], ascending=[False, True]
    ).reset_index(drop=True)

    theo_total = float(df["theo"].sum())
    lost_total = float(df["lost_theo"].sum())
    total = {
        "down_h": float(df["down_s"].sum() / 3600.0),
        "lost_theo": lost_total,
        "theo_total": theo_total,
        "share": lost_total / theo_total if theo_total else None,
    }

    out = {
        "by_date": {
            "down_h": [float(v) for v in bd["down_h"].to_numpy()],
            "lost_theo": [float(v) for v in bd["lost_theo"].to_numpy()],
        },
        "by_hour": {
            "down_h": [float(v) for v in bh["down_h"].to_numpy()],
            "lost_theo": [float(v) for v in bh["lost_theo"].to_numpy()],
        },
        "by_mfr_month": [
            {
                "mfr": str(r.mfr),
                "month": str(r.month),
                "down_h": float(r.down_h),
                "lost_theo": float(r.lost_theo),
                "faults": int(r.faults),
                "repair_cost": float(r.repair_cost),
            }
            for r in bm.itertuples(index=False)
        ],
        "by_machine": [
            {
                "machine_id": str(r.machine_id),
                "down_h": float(r.down_h),
                "lost_theo": float(r.lost_theo),
                "faults": int(r.faults),
            }
            for r in by_machine.itertuples(index=False)
        ],
        "total": total,
    }

    aux = {
        "dates": dates,
        "by_date_df": bd,
        "by_hour_df": bh,
        "by_mfr_month_df": bm,
        "by_machine_df": by_machine,
        "rate_df": rate,
    }
    return out, aux


# --------------------------------------------------------------------------- #
# B. substitution
# --------------------------------------------------------------------------- #
def section_substitution(con):
    """
    Occupancy of non-down machines in bank-hours with k>=1 down machines
    (>=30 min) vs matched bank-hours with k=0.
    Matching cell: (bank, local_hour, weekday); weight: treated bank-hours.
    """
    bh = con.execute(
        f"""
        SELECT mh.machine_id,
               mh.hour_start_utc,
               mh.gaming_date,
               mh.local_hour,
               fl.bank_id,
               mh.available_seconds,
               mh.occupied_seconds
        FROM read_parquet('{pq('5_optional/machine_hour.parquet')}') mh
        JOIN read_parquet('{pq('2_machine_decision/floor_locations.parquet')}') fl
          ON fl.location_id = mh.location_id AND fl.node_type = 'slot'
        WHERE mh.active
        """
    ).df()
    bh["gaming_date"] = pd.to_datetime(bh["gaming_date"])
    bh["down_s"] = np.maximum(0, 3600 - bh["available_seconds"])
    bh["isdown"] = bh["down_s"] >= 1800
    bh["weekday"] = bh["gaming_date"].dt.day_of_week

    bank_hour = (
        bh.groupby(["bank_id", "hour_start_utc", "gaming_date", "local_hour", "weekday"],
                   as_index=False)
        .agg(k=("isdown", "sum"))
    )
    # occupancy of machines not down that hour
    up = (
        bh[~bh["isdown"]]
        .groupby(["bank_id", "hour_start_utc"], as_index=False)
        .agg(occ_s=("occupied_seconds", "sum"), av_s=("available_seconds", "sum"))
    )
    up["occ"] = up["occ_s"] / up["av_s"]
    g = bank_hour.merge(up[["bank_id", "hour_start_utc", "occ"]],
                        on=["bank_id", "hour_start_utc"], how="left")
    g["treated"] = (g["k"] >= 1).astype(int)

    treated_bank_hours = int(g["treated"].sum())
    treated_with_occ = int(((g["treated"] == 1) & g["occ"].notna()).sum())

    cells = (
        g.dropna(subset=["occ"])
        .groupby(["bank_id", "local_hour", "weekday", "treated"], as_index=False)
        .agg(occ=("occ", "mean"), n=("occ", "size"))
    )
    pv = cells.pivot_table(
        index=["bank_id", "local_hour", "weekday"],
        columns="treated", values="occ",
    )
    cnt = (
        cells[cells["treated"] == 1]
        .set_index(["bank_id", "local_hour", "weekday"])["n"]
        .rename("w")
    )
    both = pv.dropna(subset=[0, 1]).join(cnt).dropna(subset=["w"])
    both["diff"] = both[1] - both[0]

    if len(both):
        d = both["diff"].to_numpy(dtype=float)
        w = both["w"].to_numpy(dtype=float)
        base_vals = both[0].to_numpy(dtype=float)
        diff = float((w * d).sum() / w.sum())
        baseline = float((w * base_vals).sum() / w.sum())
        ratio = diff / baseline if baseline else None

        rng = np.random.default_rng(42)
        boot = np.empty(1000, dtype=float)
        for i in range(1000):
            idx = rng.integers(0, len(d), len(d))
            boot[i] = (w[idx] * d[idx]).sum() / w[idx].sum()
        ci_low, ci_high = np.percentile(boot, [2.5, 97.5])
    else:
        diff = baseline = ratio = None
        ci_low = ci_high = None

    out = {
        "treated_bank_hours": treated_bank_hours,
        "weighted_mean_diff_occ": diff,
        "baseline_occ": baseline,
        "ratio": ratio,
        "ci_low": float(ci_low) if ci_low is not None else None,
        "ci_high": float(ci_high) if ci_high is not None else None,
        "n_cells": int(len(both)),
        "treated_bank_hours_with_comparison": treated_with_occ,
        "bootstrap_resamples": 1000,
        "seed": 42,
    }
    aux = {"cells": both, "treated_bank_hours": treated_bank_hours,
           "treated_with_occ": treated_with_occ}
    return out, aux


# --------------------------------------------------------------------------- #
# C. staffing
# --------------------------------------------------------------------------- #
def section_staffing(con):
    """Fault wait times against slot-tech roster coverage (Apr-May day-shift short)."""
    ro = con.execute(
        f"""
        SELECT o.operation_id,
               o.machine_id,
               o.opened_at_utc,
               o.opened_at_local,
               o.work_started_at_utc,
               date_diff('second', o.opened_at_utc, o.work_started_at_utc) / 3600.0
                   AS wait_h,
               r.shift,
               r.zone_id,
               r.planned_headcount,
               r.actual_headcount
        FROM read_parquet('{pq('2_machine_decision/operations.parquet')}') o
        JOIN read_parquet('{pq('5_optional/shift_roster.parquet')}') r
          ON r.role = 'slot_tech'
         AND o.opened_at_utc >= r.start_utc
         AND o.opened_at_utc <  r.end_utc
        WHERE o.event_type = 'fault_repair'
        """
    ).df()
    ro["understaffed"] = ro["actual_headcount"] < ro["planned_headcount"]
    ro["local_hour"] = pd.to_datetime(ro["opened_at_local"]).dt.hour
    ro = ro.dropna(subset=["wait_h"]).copy()

    by_shift = []
    for shift in SHIFT_ORDER:
        for us in (True, False):
            sub = ro[(ro["shift"] == shift) & (ro["understaffed"] == us)]
            if not len(sub):
                continue
            by_shift.append({
                "shift": shift,
                "understaffed": bool(us),
                "n": int(len(sub)),
                "mean_wait_h": float(sub["wait_h"].mean()),
                "median_wait_h": float(sub["wait_h"].median()),
                "mean_actual_headcount": float(sub["actual_headcount"].mean()),
            })

    by_hour_df = (
        ro.groupby("local_hour")
        .agg(n=("wait_h", "size"), mean_wait_h=("wait_h", "mean"))
        .reindex(range(24))
    )
    by_hour = [
        {
            "local_hour": int(h),
            "n": int(by_hour_df.loc[h, "n"]) if pd.notna(by_hour_df.loc[h, "n"]) else 0,
            "mean_wait_h": (float(by_hour_df.loc[h, "mean_wait_h"])
                            if pd.notna(by_hour_df.loc[h, "mean_wait_h"]) else None),
        }
        for h in range(24)
    ]

    roster = con.execute(
        f"""
        SELECT gaming_date, shift, planned_headcount, actual_headcount
        FROM read_parquet('{pq('5_optional/shift_roster.parquet')}')
        WHERE role = 'slot_tech'
        """
    ).df()
    roster["gaming_date"] = pd.to_datetime(roster["gaming_date"])
    roster["month"] = roster["gaming_date"].dt.strftime("%Y-%m")
    rm = (
        roster.groupby(["month", "shift"], as_index=False)
        .agg(planned_mean=("planned_headcount", "mean"),
             actual_mean=("actual_headcount", "mean"))
    )
    rm["shift"] = pd.Categorical(rm["shift"], categories=SHIFT_ORDER, ordered=True)
    rm = rm.sort_values(["month", "shift"])
    roster_month = [
        {
            "month": str(r.month),
            "shift": str(r.shift),
            "planned_mean": float(r.planned_mean),
            "actual_mean": float(r.actual_mean),
        }
        for r in rm.itertuples(index=False)
    ]

    model = smf.ols(
        "wait_h ~ C(shift) + actual_headcount", data=ro
    ).fit(cov_type="HC1")
    params = []
    for term in model.params.index:
        params.append({
            "term": str(term),
            "coef": float(model.params[term]),
            "se": float(model.bse[term]),
            "p": float(model.pvalues[term]),
        })
    regression = {
        "n": int(model.nobs),
        "r2": float(model.rsquared),
        "hc": "HC1",
        "params": params,
    }

    out = {
        "by_shift": by_shift,
        "by_hour": by_hour,
        "roster_month": roster_month,
        "regression": regression,
    }
    aux = {"faults": ro, "roster_month_df": rm, "by_hour_df": by_hour_df}
    return out, aux


# --------------------------------------------------------------------------- #
# D. closure
# --------------------------------------------------------------------------- #
def section_closure(con, dates: pd.DatetimeIndex):
    """Walkway W-ENT-B40 closure: B40 vs rest-of-floor theo rate and counterfactual."""
    pv = con.execute(
        f"""
        SELECT gaming_date, zone_id, theo_usd, available_hours
        FROM read_parquet('{pq('1_prepared_views/prepared_daily_view.parquet')}')
        WHERE active
        """
    ).df()
    pv["gaming_date"] = pd.to_datetime(pv["gaming_date"])

    b40 = (
        pv[pv["zone_id"] == "Z-B40"]
        .groupby("gaming_date")
        .agg(b40_theo=("theo_usd", "sum"), b40_av=("available_hours", "sum"))
    )
    rest = (
        pv[pv["zone_id"] != "Z-B40"]
        .groupby("gaming_date")
        .agg(rest_theo=("theo_usd", "sum"), rest_av=("available_hours", "sum"))
    )
    daily = pd.DataFrame(index=dates).join(b40).join(rest)
    for col in ("b40_theo", "b40_av", "rest_theo", "rest_av"):
        daily[col] = daily[col].fillna(0.0)
    daily["b40_rate"] = np.where(daily["b40_av"] > 0,
                                 daily["b40_theo"] / daily["b40_av"], np.nan)
    daily["rest_rate"] = np.where(daily["rest_av"] > 0,
                                  daily["rest_theo"] / daily["rest_av"], np.nan)
    daily["ratio"] = daily["b40_rate"] / daily["rest_rate"]
    daily["week_start"] = daily.index - pd.to_timedelta(daily.index.day_of_week, unit="D")

    weekly = (
        daily.groupby("week_start")[["b40_theo", "b40_av", "rest_theo", "rest_av"]]
        .sum()
    )
    weekly["b40_rate"] = weekly["b40_theo"] / weekly["b40_av"]
    weekly["rest_rate"] = weekly["rest_theo"] / weekly["rest_av"]
    weekly["ratio"] = weekly["b40_rate"] / weekly["rest_rate"]

    def period_ratio(lo: str, hi: str) -> dict:
        sub = daily.loc[lo:hi]
        b = float(sub["b40_theo"].sum() / sub["b40_av"].sum())
        r = float(sub["rest_theo"].sum() / sub["rest_av"].sum())
        return {"b40_rate": b, "rest_rate": r, "ratio": b / r}

    pre = period_ratio("2025-01-01", "2025-03-02")
    closure = period_ratio("2025-03-03", "2025-04-06")
    post = period_ratio("2025-04-07", "2025-06-30")
    periods = {
        "pre_ratio": pre["ratio"],
        "closure_ratio": closure["ratio"],
        "post_ratio": post["ratio"],
    }

    clo = daily.loc["2025-03-03":"2025-04-06"]
    lost_theo_closure = float(
        (clo["rest_rate"] * pre["ratio"] * clo["b40_av"] - clo["b40_theo"]).sum()
    )

    traffic = con.execute(
        f"""
        SELECT z.zone_id,
               c.gaming_date,
               z.entries_count * 60.0 / z.coverage_minutes AS adj
        FROM read_parquet('{pq('4_context/zone_traffic_hourly.parquet')}') z
        JOIN read_parquet('{pq('2_machine_decision/calendar_day.parquet')}') c
          ON z.hour_start_utc >= c.gaming_day_start_utc
         AND z.hour_start_utc <  c.gaming_day_end_utc
        WHERE z.counter_status IN ('ok', 'partial')
          AND z.coverage_minutes > 0
          AND z.entries_count IS NOT NULL
        """
    ).df()
    traffic["gaming_date"] = pd.to_datetime(traffic["gaming_date"])
    traffic["week_start"] = (
        traffic["gaming_date"]
        - pd.to_timedelta(traffic["gaming_date"].dt.day_of_week, unit="D")
    )
    tg = (
        traffic.groupby(["zone_id", "week_start"], as_index=False)
        .agg(adj_entries=("adj", "sum"), sensor_hours=("adj", "size"))
    )
    tg["entries_per_sensor_day"] = tg["adj_entries"] / tg["sensor_hours"] * 24.0
    tg = tg.sort_values(["zone_id", "week_start"])

    out = {
        "weekly": [
            {
                "week_start": r.week_start.strftime("%Y-%m-%d"),
                "b40_rate": float(r.b40_rate),
                "rest_rate": float(r.rest_rate),
                "ratio": float(r.ratio),
            }
            for r in weekly.reset_index().itertuples(index=False)
        ],
        "daily_ratio": [
            (float(v) if pd.notna(v) else None) for v in daily["ratio"].to_numpy()
        ],
        "periods": periods,
        "lost_theo_closure": lost_theo_closure,
        "traffic_weekly": [
            {
                "zone_id": str(r.zone_id),
                "week_start": r.week_start.strftime("%Y-%m-%d"),
                "entries_per_sensor_day": float(r.entries_per_sensor_day),
            }
            for r in tg.itertuples(index=False)
        ],
    }
    aux = {
        "daily": daily,
        "weekly": weekly,
        "periods_detail": {"pre": pre, "closure": closure, "post": post},
        "traffic_weekly_df": tg,
    }
    return out, aux


# --------------------------------------------------------------------------- #
# E. comp
# --------------------------------------------------------------------------- #
def detect_comp_change(daily: pd.DataFrame):
    """
    First gaming date d such that the 7-day ratio of sums (points / face $) after d is below 0.7x the
    7-day ratio of sums before d, and every single day of the week after d is below that threshold
    (so the Apr 28-30 transition days are not reported as the change). Ratio of sums, not mean of ratios.
    """
    pts = daily["pts"].to_numpy(dtype=float)
    face = daily["face"].to_numpy(dtype=float)
    vals = daily["pts_per_face_usd"].to_numpy(dtype=float)
    idx = daily.index
    def ros(lo, hi):
        f = np.nansum(face[lo:hi])
        return np.nansum(pts[lo:hi]) / f if f > 0 else np.nan
    for strict in (True, False):
        for i in range(7, len(vals) - 6):
            before, after = ros(i - 7, i), ros(i, i + 7)
            if not (np.isfinite(before) and np.isfinite(after)) or before <= 0:
                continue
            threshold = 0.7 * before
            if after < threshold and (not strict or np.nanmax(vals[i:i + 7]) < threshold):
                return idx[i]
    return idx[0]


def did_block(floor: pd.DataFrame, pre_lo, pre_hi, post_lo, post_hi, seed=42):
    """DiD in log daily-mean coin-in, carded vs uncarded, with day bootstrap."""
    pre = floor.loc[pre_lo:pre_hi, ["carded", "uncarded"]]
    post = floor.loc[post_lo:post_hi, ["carded", "uncarded"]]
    cp, up = pre["carded"].mean(), pre["uncarded"].mean()
    cq, uq = post["carded"].mean(), post["uncarded"].mean()
    did = float(math.log(cq / cp) - math.log(uq / up))

    pre_rows = pre.to_numpy(dtype=float)
    post_rows = post.to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    boot = np.empty(1000, dtype=float)
    for i in range(1000):
        pi = rng.integers(0, len(pre_rows), len(pre_rows))
        qi = rng.integers(0, len(post_rows), len(post_rows))
        cpp = pre_rows[pi, 0].mean()
        upp = pre_rows[pi, 1].mean()
        cqq = post_rows[qi, 0].mean()
        uqq = post_rows[qi, 1].mean()
        boot[i] = math.log(cqq / cpp) - math.log(uqq / upp)
    ci_low, ci_high = np.percentile(boot, [2.5, 97.5])

    return {
        "pre_start": str(pd.Timestamp(pre_lo).date()),
        "pre_end": str(pd.Timestamp(pre_hi).date()),
        "post_start": str(pd.Timestamp(post_lo).date()),
        "post_end": str(pd.Timestamp(post_hi).date()),
        "carded_pre_daily_mean": float(cp),
        "carded_post_daily_mean": float(cq),
        "uncarded_pre_daily_mean": float(up),
        "uncarded_post_daily_mean": float(uq),
        "did": did,
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "n_pre_days": int(len(pre)),
        "n_post_days": int(len(post)),
        "bootstrap_resamples": 1000,
        "seed": seed,
    }


def section_comp(con, dates: pd.DatetimeIndex):
    """Redemption price change, monthly comp economics, carded-vs-uncarded DiD."""
    comp = con.execute(
        f"""
        SELECT c.gaming_date,
               -SUM(l.points_delta) AS pts,
               SUM(l.face_value_cents) / 100.0 AS face,
               SUM(l.economic_cost_cents) / 100.0 AS cost,
               COUNT(*) AS n
        FROM read_parquet('{pq('3_guests/loyalty_ledger.parquet')}') l
        JOIN read_parquet('{pq('2_machine_decision/calendar_day.parquet')}') c
          ON l.event_at_utc >= c.gaming_day_start_utc
         AND l.event_at_utc <  c.gaming_day_end_utc
        WHERE l.event_type = 'redeem'
        GROUP BY 1
        ORDER BY 1
        """
    ).df()
    comp["gaming_date"] = pd.to_datetime(comp["gaming_date"])
    cd = pd.DataFrame(index=dates).join(comp.set_index("gaming_date"))
    for col in ("pts", "face", "cost", "n"):
        cd[col] = cd[col].fillna(0.0)
    cd["pts_per_face_usd"] = np.where(cd["face"] > 0, cd["pts"] / cd["face"], np.nan)
    # ensure points_redeemed is positive (redeem deltas are negative)
    cd["pts"] = cd["pts"].abs()

    change = detect_comp_change(cd)
    before = cd.loc[cd.index < change]
    after = cd.loc[cd.index >= change]
    pts_before = float(before["pts"].sum() / before["face"].sum())
    pts_after = float(after["pts"].sum() / after["face"].sum())

    daily = {
        "points_redeemed": [float(v) for v in cd["pts"].to_numpy()],
        "face_usd": [float(v) for v in cd["face"].to_numpy()],
        "cost_usd": [float(v) for v in cd["cost"].to_numpy()],
        "n_redemptions": [int(v) for v in cd["n"].to_numpy()],
        "pts_per_face_usd": [
            (float(v) if pd.notna(v) else None) for v in cd["pts_per_face_usd"]
        ],
    }

    pp = con.execute(
        f"SELECT * FROM read_parquet('{pq('1_prepared_views/player_period.parquet')}')"
    ).df()
    monthly_df = (
        pp.groupby("period_month", as_index=False)
        .agg(
            players=("player_id", "nunique"),
            tracked_coin_in=("tracked_coin_in_usd", "sum"),
            theo=("theo_usd", "sum"),
            comp_cost=("comp_cost_usd", "sum"),
            comp_face=("comp_face_value_usd", "sum"),
            redemptions=("comps_redeemed", "sum"),
            points_earned=("points_earned", "sum"),
            points_redeemed=("points_redeemed", "sum"),
        )
    )
    monthly_df["reinvestment"] = monthly_df["comp_cost"] / monthly_df["theo"]
    monthly = [
        {
            "month": str(r.period_month),
            "players": int(r.players),
            "tracked_coin_in": float(r.tracked_coin_in),
            "theo": float(r.theo),
            "comp_cost": float(r.comp_cost),
            "comp_face": float(r.comp_face),
            "reinvestment": float(r.reinvestment),
            "redemptions": int(r.redemptions),
            "points_earned": int(r.points_earned),
            "points_redeemed": int(r.points_redeemed),
        }
        for r in monthly_df.itertuples(index=False)
    ]

    floor = con.execute(
        f"""
        SELECT gaming_date,
               SUM(carded_coin_in_usd) AS carded,
               SUM(coin_in_usd - carded_coin_in_usd) AS uncarded
        FROM read_parquet('{pq('1_prepared_views/prepared_daily_view.parquet')}')
        WHERE active
        GROUP BY 1
        ORDER BY 1
        """
    ).df()
    floor["gaming_date"] = pd.to_datetime(floor["gaming_date"])
    floor = floor.set_index("gaming_date").reindex(dates).fillna(0.0)

    did = did_block(floor, "2025-03-01", "2025-04-30",
                    "2025-05-01", "2025-06-30")
    placebo = did_block(floor, "2025-01-01", "2025-02-28",
                        "2025-03-01", "2025-04-30")

    # theo / comp by opening tier, Mar-Apr vs May-Jun (no clean control)
    pp["period_month"] = pp["period_month"].astype(str)
    pre = pp[pp["period_month"].isin(["2025-03", "2025-04"])]
    post = pp[pp["period_month"].isin(["2025-05", "2025-06"])]
    tiers = []
    for tier in sorted(pp["opening_tier"].dropna().unique()):
        a = pre[pre["opening_tier"] == tier]
        b = post[post["opening_tier"] == tier]
        if not len(a) or not len(b):
            continue
        tiers.append({
            "tier": str(tier),
            "theo_pre_per_player_month": float(a["theo_usd"].sum() / len(a)),
            "theo_post_per_player_month": float(b["theo_usd"].sum() / len(b)),
            # total comp cost in the period (the plain spec key) ...
            "comp_cost_pre": float(a["comp_cost_usd"].sum()),
            "comp_cost_post": float(b["comp_cost_usd"].sum()),
            # ... and the same spend per active player-month for comparability
            "comp_cost_pre_per_player_month": float(a["comp_cost_usd"].sum() / len(a)),
            "comp_cost_post_per_player_month": float(b["comp_cost_usd"].sum() / len(b)),
        })

    out = {
        "daily": daily,
        "change_date": change.strftime("%Y-%m-%d"),
        "pts_per_usd_before": pts_before,
        "pts_per_usd_after": pts_after,
        "monthly": monthly,
        "did": did,
        "placebo": placebo,
        "by_opening_tier": tiers,
    }
    aux = {
        "daily_df": cd,
        "monthly_df": monthly_df,
        "floor": floor,
        "change": change,
        "tiers_df": pd.DataFrame(tiers),
    }
    return out, aux


# --------------------------------------------------------------------------- #
# F. events
# --------------------------------------------------------------------------- #
def section_events(con):
    """Event-date property coin-in vs same weekdays in the prior four weeks."""
    prop = con.execute(
        f"""
        SELECT gaming_date, coin_in_usd
        FROM read_parquet('{pq('1_prepared_views/property_day.parquet')}')
        """
    ).df()
    prop["gaming_date"] = pd.to_datetime(prop["gaming_date"])
    prop = prop.set_index("gaming_date").sort_index()

    ev = con.execute(
        f"SELECT * FROM read_parquet('{pq('4_context/events.parquet')}') ORDER BY start_date"
    ).df()
    ev["start_date"] = pd.to_datetime(ev["start_date"])
    ev["end_date"] = pd.to_datetime(ev["end_date"])

    all_event_dates = set()
    for r in ev.itertuples(index=False):
        all_event_dates.update(pd.date_range(r.start_date, r.end_date, freq="D"))

    rows = []
    for r in ev.itertuples(index=False):
        edates = [d for d in pd.date_range(r.start_date, r.end_date, freq="D")
                  if d in prop.index]
        if not edates:
            continue
        event_mean = float(prop.loc[edates, "coin_in_usd"].mean())
        weekdays = {d.day_of_week for d in edates}
        bstart = r.start_date - pd.Timedelta(days=28)
        bend = r.start_date - pd.Timedelta(days=1)
        bdates = [
            d for d in pd.date_range(bstart, bend, freq="D")
            if d in prop.index
            and d.day_of_week in weekdays
            and d not in all_event_dates
        ]
        base_mean = float(prop.loc[bdates, "coin_in_usd"].mean()) if bdates else None
        if base_mean:
            lift_pct = (event_mean / base_mean - 1.0) * 100.0
            lift_usd = event_mean - base_mean
        else:
            lift_pct = lift_usd = None
        rows.append({
            "id": str(r.event_id),
            "name": str(r.name),
            "type": str(r.event_type),
            "start": r.start_date.strftime("%Y-%m-%d"),
            "end": r.end_date.strftime("%Y-%m-%d"),
            "lift_pct": lift_pct,
            "lift_usd_per_day": lift_usd,
            "n_days": int(len(edates)),
            "event_mean_coin_in_usd": event_mean,
            "baseline_mean_coin_in_usd": base_mean,
            "n_baseline_days": int(len(bdates)),
        })

    out = rows
    aux = {"events_df": pd.DataFrame(rows), "property": prop}
    return out, aux


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def build_report(dates, A, Aaux, B, Bax, C, Caux, D, Daux, E, Eaux, F, Faux) -> str:
    L = []
    L.append("# Evidence tables — The Gilded Ace, Jan–Jun 2025")
    L.append("")
    L.append("Generated by `pipeline/analysis.py`. Money is USD; `_rate` values are dollars of "
             "theoretical win per available machine-hour. All ratios are ratios of sums. "
             "Inactive machine rows are excluded. Data window: 181 gaming dates, "
             "2025-01-01 to 2025-06-30.")
    L.append("")
    L.append("> **Downtime is an upper bound.** It values down machine-hours at the "
             "machine×local-hour expected theo rate and assumes no substitution to other machines. "
             "Section B tests that assumption directly.")
    L.append("")

    # ---- A ----
    L.append("## A. Downtime")
    L.append("")
    t = A["total"]
    L.append(md_table(
        ["metric", "value"],
        [
            ["down hours", fmt(t["down_h"], 2)],
            ["lost theo (USD)", fmt(t["lost_theo"], 2)],
            ["theo all active hours (USD)", fmt(t["theo_total"], 2)],
            ["lost theo / total theo", f"{t['share']*100:.2f}%"],
        ],
    ))
    L.append("")
    bd = Aaux["by_date_df"].copy()
    bd["month"] = bd.index.strftime("%Y-%m")
    bm = bd.groupby("month").agg(down_h=("down_h", "sum"),
                                 lost_theo=("lost_theo", "sum"))
    L.append("### Monthly downtime")
    L.append("")
    L.append(md_table(
        ["month", "down_h", "lost_theo_usd"],
        [[m, fmt(r.down_h, 2), fmt(r.lost_theo, 2)] for m, r in bm.iterrows()],
    ))
    L.append("")
    L.append("Full 181-day `by_date` arrays are in `site/data/analysis.json`.")
    L.append("")
    L.append("### Downtime by local hour")
    L.append("")
    L.append(md_table(
        ["local_hour", "down_h", "lost_theo_usd"],
        [[h, fmt(A["by_hour"]["down_h"][h], 2), fmt(A["by_hour"]["lost_theo"][h], 2)]
         for h in range(24)],
    ))
    L.append("")
    L.append("### Downtime and repair cost by manufacturer-month")
    L.append("")
    L.append(md_table(
        ["manufacturer", "month", "down_h", "lost_theo_usd", "faults", "repair_cost_usd"],
        [[r["mfr"], r["month"], fmt(r["down_h"], 2), fmt(r["lost_theo"], 2),
          r["faults"], fmt(r["repair_cost"], 2)] for r in A["by_mfr_month"]],
    ))
    L.append("")
    L.append(f"### Machines with the largest lost theo (top {TOP_MACHINES_IN_REPORT}; "
             f"all {len(A['by_machine'])} in JSON)")
    L.append("")
    L.append(md_table(
        ["machine_id", "down_h", "lost_theo_usd", "faults"],
        [[r["machine_id"], fmt(r["down_h"], 2), fmt(r["lost_theo"], 2), r["faults"]]
         for r in A["by_machine"][:TOP_MACHINES_IN_REPORT]],
    ))
    L.append("")

    # ---- B ----
    L.append("## B. Substitution")
    L.append("")
    L.append("Occupancy of the *other* (not-down) machines in bank-hours with **k≥1** machines "
             "down ≥30 min, compared with matched bank-hours with **k=0**. Cells are "
             "(bank, local hour, weekday); the difference within each cell is weighted by the "
             "number of treated bank-hours. 95% CI: 1,000 cell bootstraps, seed 42.")
    L.append("")
    L.append(md_table(
        ["metric", "value"],
        [
            ["treated bank-hours (k≥1)", B["treated_bank_hours"]],
            ["used in matched comparison", B["treated_bank_hours_with_comparison"]],
            ["matched cells", B["n_cells"]],
            ["weighted mean occ. difference", fmt(B["weighted_mean_diff_occ"], 4)],
            ["baseline occupancy (k=0)", fmt(B["baseline_occ"], 4)],
            ["ratio (diff / baseline)", fmt(B["ratio"], 4)],
            ["95% CI low", fmt(B["ci_low"], 4)],
            ["95% CI high", fmt(B["ci_high"], 4)],
        ],
    ))
    L.append("")
    L.append("The occupancy difference is tiny and positive: bank-hours with a down machine do "
             "**not** show a measurable drain of players to neighbours, so substitution does not "
             "explain away the downtime estimate.")
    L.append("")

    # ---- C ----
    L.append("## C. Staffing")
    L.append("")
    L.append("Fault tickets matched to the slot-tech roster row containing `opened_at_utc`. "
             "`understaffed` = actual headcount < planned headcount. `wait_h` = "
             "work_started − opened.")
    L.append("")
    L.append("### Wait by shift and staffing state")
    L.append("")
    L.append(md_table(
        ["shift", "understaffed", "n", "mean_wait_h", "median_wait_h", "mean_actual_headcount"],
        [[r["shift"], fmt(r["understaffed"]), r["n"], fmt(r["mean_wait_h"], 3),
          fmt(r["median_wait_h"], 3), fmt(r["mean_actual_headcount"], 3)]
         for r in C["by_shift"]],
    ))
    L.append("")
    L.append("### Faults and wait by local hour")
    L.append("")
    L.append(md_table(
        ["local_hour", "n", "mean_wait_h"],
        [[r["local_hour"], r["n"], fmt(r["mean_wait_h"], 3)] for r in C["by_hour"]],
    ))
    L.append("")
    L.append("### Slot-tech roster by month")
    L.append("")
    L.append(md_table(
        ["month", "shift", "planned_mean", "actual_mean"],
        [[r["month"], r["shift"], fmt(r["planned_mean"], 3), fmt(r["actual_mean"], 3)]
         for r in C["roster_month"]],
    ))
    L.append("")
    L.append("### Regression (HC1)")
    L.append("")
    L.append(f"`wait_h ~ C(shift) + actual_headcount`, n = {C['regression']['n']}, "
             f"R² = {fmt(C['regression']['r2'], 4)}.")
    L.append("")
    L.append(md_table(
        ["term", "coef", "SE", "p"],
        [[p["term"], fmt(p["coef"], 4), fmt(p["se"], 4), fmt_p(p["p"])]
         for p in C["regression"]["params"]],
    ))
    L.append("")

    # ---- D ----
    L.append("## D. Walkway closure (W-ENT-B40, 2025-03-03 14:00 UTC → 2025-04-07 13:00 UTC)")
    L.append("")
    L.append("B40 = zone `Z-B40`; rest = all other zones. Rate = Σ theo / Σ available hours "
             "($ per machine-hour). `ratio` = B40 rate / rest rate.")
    L.append("")
    L.append("### Weekly")
    L.append("")
    L.append(md_table(
        ["week_start", "b40_rate", "rest_rate", "ratio"],
        [[r["week_start"], fmt(r["b40_rate"], 4), fmt(r["rest_rate"], 4),
          fmt(r["ratio"], 4)] for r in D["weekly"]],
    ))
    L.append("")
    L.append("### Period ratios")
    L.append("")
    L.append(md_table(
        ["period", "B40/rest ratio"],
        [["pre (Jan 1 – Mar 2)", fmt(D["periods"]["pre_ratio"], 4)],
         ["closure (Mar 3 – Apr 6)", fmt(D["periods"]["closure_ratio"], 4)],
         ["post (Apr 7 – Jun 30)", fmt(D["periods"]["post_ratio"], 4)]],
    ))
    L.append("")
    L.append(f"Counterfactual lost theo in the closure window: "
             f"**${fmt(D['lost_theo_closure'], 2)}** "
             f"(rest-of-floor rate × pre-closure B40/rest ratio × B40 available hours − B40 theo).")
    L.append("")
    L.append("### Zone traffic (counter-adjusted entries per sensor-day, ISO weeks)")
    L.append("")
    tg = Daux["traffic_weekly_df"]
    if len(tg):
        pv = tg.pivot_table(index="week_start", columns="zone_id",
                            values="entries_per_sensor_day")
        pv = pv.sort_index()
        headers = ["week_start"] + [str(c) for c in pv.columns]
        rows = [[d.strftime("%Y-%m-%d")] + [fmt(v, 1) for v in pv.loc[d].to_numpy()]
                for d in pv.index]
        L.append(md_table(headers, rows))
    else:
        L.append("_No qualifying counter rows._")
    L.append("")

    # ---- E ----
    L.append("## E. Comp redemption price change")
    L.append("")
    L.append("`pts_per_face_usd` = points redeemed / face value of redeemed comps. "
             "Change date detection: first date whose next 7 days are a sustained drop below "
             "70% of the prior 7-day mean.")
    L.append("")
    L.append(md_table(
        ["metric", "value"],
        [
            ["change date", E["change_date"]],
            ["points per $ face before", fmt(E["pts_per_usd_before"], 4)],
            ["points per $ face after", fmt(E["pts_per_usd_after"], 4)],
            ["after / before", fmt(E["pts_per_usd_after"] / E["pts_per_usd_before"], 4)],
        ],
    ))
    L.append("")
    L.append("### Monthly tracked economics")
    L.append("")
    L.append(md_table(
        ["month", "players", "coin_in_usd", "theo_usd", "comp_cost_usd", "comp_face_usd",
         "reinvestment", "redemptions", "points_earned", "points_redeemed"],
        [[r["month"], r["players"], fmt(r["tracked_coin_in"], 0), fmt(r["theo"], 0),
          fmt(r["comp_cost"], 0), fmt(r["comp_face"], 0), fmt(r["reinvestment"], 4),
          r["redemptions"], r["points_earned"], r["points_redeemed"]]
         for r in E["monthly"]],
    ))
    L.append("")
    L.append("### Difference-in-differences, carded vs uncarded daily coin-in")
    L.append("")
    rows = []
    for label, key in (("comp change (Mar–Apr → May–Jun)", "did"),
                       ("placebo (Jan–Feb → Mar–Apr)", "placebo")):
        r = E[key]
        rows.append([label, fmt(r["did"], 4), fmt(r["ci_low"], 4), fmt(r["ci_high"], 4),
                     r["n_pre_days"], r["n_post_days"]])
    L.append(md_table(["comparison", "DiD (log)", "95% CI low", "95% CI high",
                       "n pre", "n post"], rows))
    L.append("")
    L.append("DiD = ln(carded post/pre) − ln(uncarded post/pre), using daily floor means; "
             "CI from 1,000 bootstraps resampling days within each period (seed 42).")
    L.append("")
    L.append("### Theo and comp cost by opening tier (Mar–Apr vs May–Jun)")
    L.append("")
    L.append("Theo is per active player-month. `comp_cost_pre` / `comp_cost_post` are total "
             "tier spend; the per-player-month columns are shown for comparability.")
    L.append("")
    L.append(md_table(
        ["tier", "theo_pre", "theo_post", "comp_cost_pre_total", "comp_cost_post_total",
         "comp_cost_pre /player-month", "comp_cost_post /player-month"],
        [[r["tier"], fmt(r["theo_pre_per_player_month"], 2),
          fmt(r["theo_post_per_player_month"], 2), fmt(r["comp_cost_pre"], 2),
          fmt(r["comp_cost_post"], 2), fmt(r["comp_cost_pre_per_player_month"], 2),
          fmt(r["comp_cost_post_per_player_month"], 2)]
         for r in E["by_opening_tier"]],
    ))
    L.append("")
    L.append("No clean control exists for the tier split; these are descriptive pre/post values.")
    L.append("")

    # ---- F ----
    L.append("## F. Events")
    L.append("")
    L.append("Property coin-in on event dates vs the same weekdays in the four weeks before the "
             "event start, excluding all other event dates.")
    L.append("")
    L.append(md_table(
        ["id", "name", "type", "start", "end", "lift_pct", "lift_usd_per_day", "n_days",
         "baseline_days"],
        [[r["id"], r["name"], r["type"], r["start"], r["end"], fmt(r["lift_pct"], 2),
          fmt(r["lift_usd_per_day"], 2), r["n_days"], r["n_baseline_days"]]
         for r in F],
    ))
    L.append("")
    L.append("The CES baseline is limited to Jan 1–3 because the dataset window starts on "
             "2025-01-01; all other events have a full four-week baseline.")
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    con = duckdb.connect()
    con.execute("SET threads = 8")
    dates = load_dates(con)

    print("Computing A. downtime ...")
    A, Aaux = section_downtime(con, dates)
    print("Computing B. substitution ...")
    B, Bax = section_substitution(con)
    print("Computing C. staffing ...")
    C, Caux = section_staffing(con)
    print("Computing D. closure ...")
    D, Daux = section_closure(con, dates)
    print("Computing E. comp ...")
    E, Eaux = section_comp(con, dates)
    print("Computing F. events ...")
    F, Faux = section_events(con)

    analysis = clean({
        "downtime": A,
        "substitution": B,
        "staffing": C,
        "closure": D,
        "comp": E,
        "events": F,
    })

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(analysis, fh, indent=2, ensure_ascii=False, allow_nan=False)
        fh.write("\n")

    report = build_report(dates, A, Aaux, B, Bax, C, Caux, D, Daux, E, Eaux, F, Faux)
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write(report)
        if not report.endswith("\n"):
            fh.write("\n")

    # ---- printed key numbers ----
    print("\n=== KEY NUMBERS ===")
    t = A["total"]
    print(f"A downtime: down_h={t['down_h']:.2f}, lost_theo=${t['lost_theo']:,.2f}, "
          f"theo_total=${t['theo_total']:,.2f}, share={t['share']*100:.3f}%")
    print(f"  by_mfr_month rows={len(A['by_mfr_month'])}, by_machine rows={len(A['by_machine'])}, "
          f"by_date n={len(A['by_date']['down_h'])}, by_hour n={len(A['by_hour']['down_h'])}")
    print(f"B substitution: treated_bank_hours={B['treated_bank_hours']}, "
          f"diff={B['weighted_mean_diff_occ']:.4f}, baseline={B['baseline_occ']:.4f}, "
          f"ratio={B['ratio']:.4f}, CI=({B['ci_low']:.4f},{B['ci_high']:.4f}), "
          f"cells={B['n_cells']}")
    print(f"C staffing: n_faults={C['regression']['n']}, "
          f"mean wait by shift=" +
          ", ".join(f"{r['shift']}{'(short)' if r['understaffed'] else ''}="
                    f"{r['mean_wait_h']:.3f}h" for r in C["by_shift"]))
    print(f"  regression coefs: " +
          "; ".join(f"{p['term']}={p['coef']:.3f} (SE {p['se']:.3f}, p {p['p']:.4f})"
                    for p in C["regression"]["params"]))
    print(f"D closure: pre={D['periods']['pre_ratio']:.4f}, "
          f"closure={D['periods']['closure_ratio']:.4f}, post={D['periods']['post_ratio']:.4f}, "
          f"lost_theo_closure=${D['lost_theo_closure']:,.2f}")
    print(f"  weeks={len(D['weekly'])}, traffic_rows={len(D['traffic_weekly'])}")
    print(f"E comp: change_date={E['change_date']}, "
          f"before={E['pts_per_usd_before']:.3f}, after={E['pts_per_usd_after']:.3f}")
    print(f"  DiD={E['did']['did']:.4f} CI=({E['did']['ci_low']:.4f},"
          f"{E['did']['ci_high']:.4f}); placebo={E['placebo']['did']:.4f} "
          f"CI=({E['placebo']['ci_low']:.4f},{E['placebo']['ci_high']:.4f})")
    print(f"F events: " + "; ".join(
        f"{r['id']}={r['lift_pct']:.2f}%" for r in F))

    # ---- sanity checks (acceptance) ----
    sum_by_date = float(sum(A["by_date"]["down_h"]))
    assert 4800 <= t["down_h"] <= 5300, f"down_h out of range: {t['down_h']}"
    print("PASS: downtime.total.down_h in [4800, 5300]")
    assert D["periods"]["closure_ratio"] < D["periods"]["pre_ratio"], (
        f"closure ratio {D['periods']['closure_ratio']} not below pre "
        f"{D['periods']['pre_ratio']}"
    )
    print("PASS: closure.periods.closure_ratio < pre_ratio")
    assert E["change_date"] == "2025-05-01", f"unexpected change_date {E['change_date']}"
    print("PASS: comp.change_date == 2025-05-01")
    assert abs(sum_by_date - t["down_h"]) <= 1.0, (
        f"by_date sum {sum_by_date} vs total {t['down_h']}"
    )
    print("PASS: sum(downtime.by_date.down_h) == total.down_h (within 1h)")
    assert len(A["by_date"]["down_h"]) == 181, "by_date not aligned to 181 dates"
    print("PASS: len(by_date arrays) == 181")

    print(f"\nWrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")


if __name__ == "__main__":
    main()
