#!/usr/bin/env python3
"""Validate the JSON files produced by pipeline/build_data.py."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "site" / "data"


def load(name):
    with open(DATA_DIR / name, "r", encoding="utf-8") as handle:
        return json.load(handle)


def check_close(label, actual, expected, tolerance):
    delta = abs(actual - expected)
    print(
        f"{label}: sum={actual:,.2f} expected={expected:,.2f} "
        f"delta={delta:,.2f} (tol {tolerance:g})"
    )
    assert delta <= tolerance, f"{label}: delta {delta} > {tolerance}"


def main() -> int:
    core = load("core.json")
    players = load("players.json")
    ops = load("ops.json")

    md = core["md"]
    pd = core["pd"]

    n = len(md["d"])
    print(f"md rows: {n}")
    assert n == 55092, f"md.d has {n} rows, expected 55092"
    for key, values in md.items():
        assert len(values) == n, f"md.{key} has {len(values)} rows, expected {n}"
    print(f"md arrays: {len(md)} keys, all length {n}")

    assert len(core["dates"]) == 181, f"dates: {len(core['dates'])}"
    try:
        dst_idx = core["dates"].index("2025-03-08")
    except ValueError:
        raise AssertionError("2025-03-08 missing from dates") from None
    sched = core["sched_h"][dst_idx]
    print(f"dates: {len(core['dates'])}; sched_h[2025-03-08]={sched}")
    assert sched == 23.0, f"sched_h[2025-03-08]={sched}, expected 23.0"

    check_close("md.ci vs pd.ci", sum(md["ci"]), sum(pd["ci"]), 1.0)
    check_close("md.hw vs pd.hw", sum(md["hw"]), sum(pd["hw"]), 1.0)
    check_close("md.th vs pd.th", sum(md["th"]), sum(pd["th"]), 5.0)

    n_players = len(players["rows"]["p"])
    print(f"player rows: {n_players}")
    assert n_players == 148893, f"players.rows.p has {n_players}, expected 148893"
    net_sum = sum(players["rows"]["net"])
    check_close("players net", net_sum, -15585460.6, 200.0)

    faults = ops["faults"]
    n_faults = len(faults["m"])
    print(f"faults: {n_faults}")
    assert n_faults == 1207, f"faults.m has {n_faults}, expected 1207"
    assert len(faults["shift"]) == n_faults, "faults.shift length mismatch"
    assert len(faults["understaffed"]) == n_faults, (
        "faults.understaffed length mismatch"
    )

    with_shift = sum(1 for shift in faults["shift"] if shift is not None)
    share = with_shift / n_faults
    print(f"faults with shift != null: {with_shift}/{n_faults} = {share:.4%}")
    assert share > 0.95, f"shift coverage {share:.4%} is not > 95%"

    counts = Counter(
        (shift, bool(understaffed))
        for shift, understaffed in zip(faults["shift"], faults["understaffed"])
    )
    print("faults by shift / understaffed:")
    for (shift, understaffed), count in sorted(
        counts.items(), key=lambda item: (str(item[0][0]), item[0][1])
    ):
        label = "(none)" if shift is None else shift
        print(f"  shift={label:<7} understaffed={str(understaffed):<5} count={count}")

    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
