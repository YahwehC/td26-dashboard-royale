#!/usr/bin/env python3
"""Build the compact JSON files consumed by the static dashboard.

Reads the parquet release under data-repo/data (read-only) with DuckDB and writes
core.json, players.json and ops.json to site/data.  Only duckdb + stdlib are used.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data-repo" / "data"
OUT = ROOT / "site" / "data"

SOURCE = "tamu-datathon-org/dashboard-royale data/ (release 0.9.0-draft)"
MD_ROWS_EXPECTED = 55092
PD_ROWS_EXPECTED = 181


def pq(rel: str) -> str:
    """DuckDB read_parquet() expression for a path relative to DATA."""
    path = (DATA / (rel + ".parquet")).as_posix()
    return "read_parquet('" + path + "')"


def q(con: duckdb.DuckDBPyConnection, sql: str):
    return con.sql(sql).fetchall()


def dstr(value) -> str | None:
    return value.isoformat() if value is not None else None


def tstr(value, utc: bool = False) -> str | None:
    """ISO-8601 timestamp; UTC columns get a trailing Z, local columns do not."""
    if value is None:
        return None
    text = value.isoformat(timespec="seconds")
    return text + "Z" if utc else text


def rnd(value, ndigits: int):
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return round(number, ndigits)


def rnd_int(value):
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return int(round(number, 0))


def as_int(value):
    return None if value is None else int(value)


def write_json(name: str, payload) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    return path


def build_calendar(con):
    rows = q(
        con,
        f"""
        SELECT gaming_date, gaming_day_start_utc, gaming_day_end_utc,
               scheduled_seconds, local_weekday, federal_holiday
        FROM {pq('2_machine_decision/calendar_day')}
        ORDER BY gaming_date
        """,
    )
    dates = [dstr(r[0]) for r in rows]
    weekday = [r[4] for r in rows]
    sched_h = [round(r[3] / 3600.0, 3) for r in rows]
    holiday = [r[5] for r in rows]
    date_idx = {r[0]: i for i, r in enumerate(rows)}
    spans = [(r[1], r[2], i) for i, r in enumerate(rows)]
    assert len(rows) == PD_ROWS_EXPECTED, f"calendar rows: {len(rows)}"
    return dates, weekday, sched_h, holiday, date_idx, spans


def build_floor(con):
    rows = q(
        con,
        f"""
        SELECT location_id, node_type, zone_id, name, x_m, y_m
        FROM {pq('2_machine_decision/floor_locations')}
        WHERE node_type IN ('zone', 'bank', 'entrance', 'outlet')
        ORDER BY location_id
        """,
    )
    by_type = {"zone": [], "bank": [], "entrance": [], "outlet": []}
    for location_id, node_type, zone_id, name, x_m, y_m in rows:
        by_type[node_type].append((location_id, zone_id, name, x_m, y_m))

    zones = [
        {"id": r[0], "name": r[2], "x": r[3], "y": r[4]}
        for r in by_type["zone"]
    ]
    zone_idx = {z["id"]: i for i, z in enumerate(zones)}

    def zone_index(zone_id):
        if zone_id is None:
            return None
        if zone_id not in zone_idx:
            raise KeyError(f"unknown zone_id {zone_id!r}")
        return zone_idx[zone_id]

    banks = [
        {"id": r[0], "zone": zone_index(r[1]), "x": r[3], "y": r[4]}
        for r in by_type["bank"]
    ]
    entrances = [
        {
            "id": r[0],
            "zone": zone_index(r[1]),
            "name": r[2],
            "x": r[3],
            "y": r[4],
        }
        for r in by_type["entrance"]
    ]
    outlets = [
        {
            "id": r[0],
            "zone": zone_index(r[1]),
            "name": r[2],
            "x": r[3],
            "y": r[4],
        }
        for r in by_type["outlet"]
    ]
    return zones, banks, entrances, outlets


def build_static(con):
    events = [
        {
            "id": r[0],
            "name": r[1],
            "type": r[2],
            "start": dstr(r[3]),
            "end": dstr(r[4]),
            "announced": dstr(r[5]),
            "scope": r[6],
        }
        for r in q(
            con,
            f"""
            SELECT event_id, name, event_type, start_date, end_date,
                   announced_date, local_scope
            FROM {pq('4_context/events')}
            ORDER BY start_date, event_id
            """,
        )
    ]

    walkways = [
        {
            "id": r[0],
            "a": r[1],
            "b": r[2],
            "len_m": float(r[3]) if r[3] is not None else None,
            "closed_from_utc": tstr(r[4], utc=True),
            "closed_to_utc": tstr(r[5], utc=True),
            "reason": r[6],
        }
        for r in q(
            con,
            f"""
            SELECT walkway_id, zone_a, zone_b, length_m, closed_from_utc,
                   closed_to_utc, closure_reason
            FROM {pq('2_machine_decision/floor_walkways')}
            ORDER BY walkway_id
            """,
        )
    ]

    configs = [
        {
            "id": r[0],
            "theme": r[1],
            "rtp": float(r[2]),
            "var_mult": float(r[3]),
            "hit_p": float(r[4]),
            "max_mult": float(r[5]),
            "vol": r[6],
        }
        for r in q(
            con,
            f"""
            SELECT config_id, theme, configured_rtp, payout_multiplier_variance,
                   hit_probability, max_multiplier, volatility_class
            FROM {pq('2_machine_decision/game_math')}
            ORDER BY config_id
            """,
        )
    ]

    machines = [
        {
            "id": r[0],
            "mfr": r[1],
            "theme": r[2],
            "lease": r[5],
            "install": dstr(r[3]),
            "retire": dstr(r[4]),
        }
        for r in q(
            con,
            f"""
            SELECT machine_id, manufacturer, theme, install_date, retire_date,
                   lease_class
            FROM {pq('2_machine_decision/machines')}
            ORDER BY machine_id
            """,
        )
    ]
    return events, walkways, configs, machines


def build_md(con, dates, date_idx):
    """One row per active prepared_daily_view row, ordered by date, machine_id."""
    rows = q(
        con,
        f"""
        SELECT v.gaming_date, v.machine_id, v.bank_id, md.config_id,
               v.available_hours, v.occupied_hours,
               md.scheduled_seconds, md.payout_positive_spins, md.sum_bet_squared,
               gm.payout_multiplier_variance,
               v.coin_in_usd, v.house_win_usd, v.theo_usd, v.paid_spins,
               v.faults_opened, v.repair_cost_usd,
               v.lease_cost_usd, v.service_cost_usd, v.power_cost_usd,
               v.carded_coin_in_usd
        FROM {pq('1_prepared_views/prepared_daily_view')} v
        JOIN {pq('2_machine_decision/machine_day')} md
          ON md.machine_id = v.machine_id AND md.gaming_date = v.gaming_date
        JOIN {pq('2_machine_decision/game_math')} gm
          ON gm.config_id = md.config_id
        WHERE v.active
        ORDER BY v.gaming_date, v.machine_id
        """,
    )
    if len(rows) != MD_ROWS_EXPECTED:
        raise SystemExit(
            f"active prepared_daily_view rows joined: {len(rows)}, "
            f"expected {MD_ROWS_EXPECTED}"
        )

    null_money = Counter()

    def money(value, key):
        if value is None:
            null_money[key] += 1
            return 0.0
        return float(value)

    md = {
        "d": [],
        "m": [],
        "b": [],
        "c": [],
        "ah": [],
        "oh": [],
        "sh": [],
        "ci": [],
        "hw": [],
        "th": [],
        "v": [],
        "sp": [],
        "hs": [],
        "f": [],
        "rc": [],
        "cost": [],
        "cc": [],
    }
    for r in rows:
        gaming_date, machine_id, bank_id, config_id = r[0], r[1], r[2], r[3]
        available_h, occupied_h = r[4], r[5]
        scheduled_seconds, positive_spins, sum_bet_squared = r[6], r[7], r[8]
        payout_variance = r[9]
        coin_in, house_win, theo, paid_spins = r[10], r[11], r[12], r[13]
        faults, repair = r[14], r[15]
        lease, service, power = r[16], r[17], r[18]
        carded = r[19]

        repair_v = money(repair, "repair_cost_usd")
        lease_v = money(lease, "lease_cost_usd")
        service_v = money(service, "service_cost_usd")
        power_v = money(power, "power_cost_usd")

        md["d"].append(date_idx[gaming_date])
        md["m"].append(machine_id)
        md["b"].append(bank_id)
        md["c"].append(config_id)
        md["ah"].append(rnd(available_h, 3))
        md["oh"].append(rnd(occupied_h, 3))
        md["sh"].append(
            round(float(scheduled_seconds) / 3600.0, 3)
            if scheduled_seconds is not None
            else None
        )
        md["ci"].append(rnd(money(coin_in, "coin_in_usd"), 2))
        md["hw"].append(rnd(money(house_win, "house_win_usd"), 2))
        md["th"].append(rnd(money(theo, "theo_usd"), 2))
        if sum_bet_squared is None or payout_variance is None:
            md["v"].append(0)
        else:
            md["v"].append(
                int(round(float(sum_bet_squared) * float(payout_variance) / 10000.0, 0))
            )
        md["sp"].append(as_int(paid_spins))
        md["hs"].append(as_int(positive_spins))
        md["f"].append(as_int(faults))
        md["rc"].append(rnd(repair_v, 2))
        md["cost"].append(round(lease_v + service_v + power_v + repair_v, 2))
        md["cc"].append(rnd(money(carded, "carded_coin_in_usd"), 2))

    # Convert the string ids collected above to dense indices.
    md["m"] = list(md["m"])
    md["b"] = list(md["b"])
    md["c"] = list(md["c"])
    return md, rows, null_money


def build_pd(con, dates):
    spec = [
        ("ci", "coin_in_usd", "money"),
        ("pay", "payout_usd", "money"),
        ("hw", "house_win_usd", "money"),
        ("th", "theo_usd", "money"),
        ("avail_mh", "available_machine_hours", "hours"),
        ("occ_mh", "occupied_machine_hours", "hours"),
        ("carded_share", "carded_coin_in_share", "ratio"),
        ("pos_cash", "pos_cash_usd", "money"),
        ("pos_cogs", "pos_cogs_usd", "money"),
        ("comp_face", "comp_face_value_usd", "money"),
        ("comp_cost", "comp_cost_usd", "money"),
        ("faults", "faults_opened", "int"),
        ("incidents", "incidents_reported", "int"),
        ("ent_entries", "entrance_zone_entries_observed", "int"),
        ("tot_entries", "total_zone_entries_observed", "int"),
        ("counter_cov", "counter_coverage_share", "ratio"),
        ("mach_cost", "machine_supplied_costs_usd", "money"),
        ("tech_cost", "tech_labor_cost_usd", "money"),
        ("contrib", "contribution_after_supplied_costs_usd", "money"),
        ("active_machines", "active_machines", "int"),
    ]
    cols = ["gaming_date"] + [s[1] for s in spec]
    rows = q(
        con,
        f"SELECT {', '.join(cols)} FROM {pq('1_prepared_views/property_day')} "
        "ORDER BY gaming_date",
    )
    by_date = {r[0]: r for r in rows}
    if len(by_date) != len(dates):
        raise SystemExit(f"property_day rows: {len(by_date)}, expected {len(dates)}")

    pd = {key: [] for key, _, _ in spec}
    for d in dates:
        iso = date.fromisoformat(d)
        if iso not in by_date:
            raise SystemExit(f"property_day missing {d}")
        row = by_date[iso]
        for offset, (key, _col, kind) in enumerate(spec, start=1):
            value = row[offset]
            if kind == "money":
                pd[key].append(rnd(value, 2))
            elif kind == "ratio":
                pd[key].append(rnd(value, 4))
            elif kind == "hours":
                pd[key].append(rnd(value, 3))
            else:
                pd[key].append(as_int(value))
    return pd


def build_players(con):
    rows = q(
        con,
        f"""
        SELECT player_id, period_month, opening_tier, age_band, home_region,
               tracked_coin_in_usd, tracked_net_usd, theo_usd,
               comp_cost_usd, comp_face_value_usd, observed_visits,
               carded_play_hours, points_earned, points_redeemed,
               linked_pos_cash_usd, linked_pos_cogs_usd
        FROM {pq('1_prepared_views/player_period')}
        ORDER BY player_id, period_month
        """,
    )

    tiers = sorted({r[2] for r in rows})
    ages = sorted({r[3] for r in rows if r[3] is not None})
    if "unknown" not in ages:
        ages.append("unknown")
    regions = sorted({r[4] for r in rows})
    months = sorted({r[1] for r in rows})

    tier_idx = {v: i for i, v in enumerate(tiers)}
    age_idx = {v: i for i, v in enumerate(ages)}
    region_idx = {v: i for i, v in enumerate(regions)}
    month_idx = {v: i for i, v in enumerate(months)}

    rows_out = {
        "p": [],
        "mo": [],
        "t": [],
        "a": [],
        "r": [],
        "ci": [],
        "net": [],
        "th": [],
        "cc": [],
        "cf": [],
        "vis": [],
        "hrs": [],
        "pe": [],
        "pr": [],
        "cash": [],
        "cogs": [],
    }
    player_idx = {}
    for r in rows:
        pid = r[0]
        if pid not in player_idx:
            player_idx[pid] = len(player_idx)
        rows_out["p"].append(player_idx[pid])
        rows_out["mo"].append(month_idx[r[1]])
        rows_out["t"].append(tier_idx[r[2]])
        rows_out["a"].append(age_idx[r[3] if r[3] is not None else "unknown"])
        rows_out["r"].append(region_idx[r[4]])
        rows_out["ci"].append(rnd_int(r[5]))
        rows_out["net"].append(rnd(r[6], 1))
        rows_out["th"].append(rnd(r[7], 1))
        rows_out["cc"].append(rnd(r[8], 2))
        rows_out["cf"].append(rnd(r[9], 1))
        rows_out["vis"].append(as_int(r[10]))
        rows_out["hrs"].append(rnd(r[11], 1))
        rows_out["pe"].append(as_int(r[12]))
        rows_out["pr"].append(as_int(r[13]))
        rows_out["cash"].append(rnd(r[14], 1))
        rows_out["cogs"].append(rnd(r[15], 1))

    return {
        "tiers": tiers,
        "ages": ages,
        "regions": regions,
        "months": months,
        "rows": rows_out,
    }, len(player_idx)


def build_ops(con, date_idx):
    faults_rows = q(
        con,
        f"""
        WITH f AS (
            SELECT o.operation_id, o.machine_id, c.gaming_date,
                   o.opened_at_utc, o.opened_at_local,
                   o.work_started_at_utc, o.available_at_utc,
                   o.direct_cost_cents
            FROM {pq('2_machine_decision/operations')} o
            JOIN {pq('2_machine_decision/calendar_day')} c
              ON o.opened_at_utc >= c.gaming_day_start_utc
             AND o.opened_at_utc <  c.gaming_day_end_utc
            WHERE o.event_type = 'fault_repair'
        ), ranked AS (
            SELECT f.operation_id, s.shift, s.actual_headcount,
                   s.planned_headcount,
                   row_number() OVER (
                       PARTITION BY f.operation_id ORDER BY s.start_utc
                   ) AS rn
            FROM f
            JOIN {pq('5_optional/shift_roster')} s
              ON s.role = 'slot_tech'
             AND f.opened_at_utc >= s.start_utc
             AND f.opened_at_utc <  s.end_utc
        )
        SELECT f.operation_id, f.machine_id, f.gaming_date,
               f.opened_at_utc, f.opened_at_local,
               f.work_started_at_utc, f.available_at_utc,
               f.direct_cost_cents,
               ranked.shift, ranked.actual_headcount, ranked.planned_headcount
        FROM f
        LEFT JOIN ranked
          ON ranked.operation_id = f.operation_id AND ranked.rn = 1
        ORDER BY f.opened_at_utc, f.operation_id
        """,
    )
    if len(faults_rows) != 1207:
        raise SystemExit(f"fault_repair rows matched to calendar: {len(faults_rows)}")

    faults = {
        "m": [],
        "d": [],
        "hour": [],
        "wait_h": [],
        "fix_h": [],
        "down_h": [],
        "cost": [],
        "shift": [],
        "understaffed": [],
    }
    for r in faults_rows:
        machine_id, gaming_date = r[1], r[2]
        opened_utc, opened_local = r[3], r[4]
        started, available = r[5], r[6]
        cost_cents = r[7]
        shift, actual, planned = r[8], r[9], r[10]
        faults["m"].append(machine_id)
        faults["d"].append(date_idx[gaming_date])
        faults["hour"].append(opened_local.hour if opened_local is not None else None)
        faults["wait_h"].append(
            round((started - opened_utc).total_seconds() / 3600.0, 3)
            if started is not None
            else None
        )
        faults["fix_h"].append(
            round((available - started).total_seconds() / 3600.0, 3)
            if available is not None and started is not None
            else None
        )
        faults["down_h"].append(
            round((available - opened_utc).total_seconds() / 3600.0, 3)
            if available is not None
            else None
        )
        faults["cost"].append(
            round(cost_cents / 100.0, 2) if cost_cents is not None else None
        )
        faults["shift"].append(shift)
        faults["understaffed"].append(
            bool(actual < planned)
            if actual is not None and planned is not None
            else False
        )

    other_rows = q(
        con,
        f"""
        SELECT machine_id, event_type, opened_at_local, available_at_utc,
               location_id, direct_cost_cents
        FROM {pq('2_machine_decision/operations')}
        WHERE event_type <> 'fault_repair'
        ORDER BY opened_at_utc, operation_id
        """,
    )
    other = [
        {
            "m": r[0],
            "type": r[1],
            "opened_local": tstr(r[2]),
            "available_utc": tstr(r[3], utc=True),
            "location": r[4],
            "cost": round(r[5] / 100.0, 2) if r[5] is not None else None,
        }
        for r in other_rows
    ]
    return faults, other


def main() -> int:
    started = time.perf_counter()
    con = duckdb.connect()

    dates, weekday, sched_h, holiday, date_idx, _spans = build_calendar(con)
    zones, banks, entrances, outlets = build_floor(con)
    events, walkways, configs, machines = build_static(con)
    md, md_rows, null_money = build_md(con, dates, date_idx)
    pd = build_pd(con, dates)
    players, n_players = build_players(con)
    faults, other = build_ops(con, date_idx)

    machine_idx = {m["id"]: i for i, m in enumerate(machines)}
    bank_idx = {b["id"]: i for i, b in enumerate(banks)}
    config_idx = {c["id"]: i for i, c in enumerate(configs)}

    # Dense index conversion for the machine-day arrays.
    try:
        md["m"] = [machine_idx[x] for x in md["m"]]
        md["b"] = [bank_idx[x] for x in md["b"]]
        md["c"] = [config_idx[x] for x in md["c"]]
    except KeyError as exc:
        raise SystemExit(f"unmapped machine/bank/config id: {exc}") from exc

    core = {
        "meta": {
            "generated_utc": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "source": SOURCE,
        },
        "dates": dates,
        "weekday": weekday,
        "sched_h": sched_h,
        "holiday": holiday,
        "events": events,
        "walkways": walkways,
        "zones": zones,
        "banks": banks,
        "entrances": entrances,
        "outlets": outlets,
        "configs": configs,
        "machines": machines,
        "md": md,
        "pd": pd,
    }
    ops = {
        "faults": {
            "m": [machine_idx[x] for x in faults["m"]],
            "d": faults["d"],
            "hour": faults["hour"],
            "wait_h": faults["wait_h"],
            "fix_h": faults["fix_h"],
            "down_h": faults["down_h"],
            "cost": faults["cost"],
            "shift": faults["shift"],
            "understaffed": faults["understaffed"],
        },
        "other": [
            {
                "m": machine_idx[o["m"]],
                "type": o["type"],
                "opened_local": o["opened_local"],
                "available_utc": o["available_utc"],
                "location": o["location"],
                "cost": o["cost"],
            }
            for o in other
        ],
    }

    paths = [
        write_json("core.json", core),
        write_json("players.json", players),
        write_json("ops.json", ops),
    ]

    elapsed = time.perf_counter() - started
    print(f"calendar days: {len(dates)}")
    print(f"zones/banks/entrances/outlets: {len(zones)}/{len(banks)}/"
          f"{len(entrances)}/{len(outlets)}")
    print(f"machines/configs: {len(machines)}/{len(configs)}")
    print(f"md rows: {len(md['d'])}")
    print(f"pd rows: {len(pd['ci'])}")
    print(f"players: {len(players['rows']['p'])} rows, {n_players} distinct players")
    print(f"faults: {len(ops['faults']['m'])}; other operations: {len(ops['other'])}")
    if null_money:
        print("null money values coerced to 0: " + ", ".join(
            f"{k}={v}" for k, v in sorted(null_money.items())
        ))
    else:
        print("null money values coerced to 0: none")
    for path in paths:
        size_mb = os.path.getsize(path) / (1024 * 1024)
        print(f"{path.name}: {size_mb:.3f} MB")
    print(f"elapsed: {elapsed:.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
