import duckdb, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data-repo", "data")
con = duckdb.connect()

def q(sql, n=20):
    print("\n---", sql[:120].replace("\n", " "), "---")
    df = con.execute(sql).df()
    print(df.head(n).to_string())
    return df

q(f"SELECT * FROM read_parquet('{DATA}/5_optional/machine_hour.parquet') LIMIT 5")
q(f"SELECT * FROM read_parquet('{DATA}/2_machine_decision/machine_day.parquet') LIMIT 3")
q(f"SELECT * FROM read_parquet('{DATA}/2_machine_decision/operations.parquet') LIMIT 5")
q(f"SELECT * FROM read_parquet('{DATA}/5_optional/shift_roster.parquet') LIMIT 10")
q(f"SELECT * FROM read_parquet('{DATA}/3_guests/loyalty_ledger.parquet') WHERE event_type='redeem' LIMIT 5")
q(f"SELECT * FROM read_parquet('{DATA}/1_prepared_views/player_period.parquet') LIMIT 3")
q(f"SELECT * FROM read_parquet('{DATA}/1_prepared_views/prepared_daily_view.parquet') LIMIT 3")
q(f"SELECT * FROM read_parquet('{DATA}/4_context/events.parquet')")
q(f"SELECT * FROM read_parquet('{DATA}/2_machine_decision/floor_locations.parquet') LIMIT 8")
q(f"SELECT * FROM read_parquet('{DATA}/2_machine_decision/floor_walkways.parquet')")
q(f"SELECT * FROM read_parquet('{DATA}/2_machine_decision/calendar_day.parquet') LIMIT 3")
q(f"SELECT * FROM read_parquet('{DATA}/4_context/zone_traffic_hourly.parquet') LIMIT 5")

print("\n=== counts ===")
q(f"SELECT active, count(*), avg(available_seconds), min(available_seconds), max(available_seconds), sum(CASE WHEN available_seconds<3600 THEN 1 ELSE 0 END) as short FROM read_parquet('{DATA}/5_optional/machine_hour.parquet') GROUP BY 1")
q(f"SELECT count(*) n, count(distinct machine_id) m FROM read_parquet('{DATA}/5_optional/machine_hour.parquet') WHERE active")
q(f"SELECT count(*) FROM read_parquet('{DATA}/5_optional/machine_hour.parquet')")
q(f"SELECT gaming_date, count(*) c FROM read_parquet('{DATA}/2_machine_decision/calendar_day.parquet') GROUP BY 1 ORDER BY 1 LIMIT 3")
q(f"SELECT min(gaming_date), max(gaming_date), count(*) FROM read_parquet('{DATA}/2_machine_decision/calendar_day.parquet')")
print("\noperations types")
q(f"SELECT event_type, count(*) FROM read_parquet('{DATA}/2_machine_decision/operations.parquet') GROUP BY 1")
print("\nroster")
q(f"SELECT role, shift, count(*), avg(planned_headcount), avg(actual_headcount) FROM read_parquet('{DATA}/5_optional/shift_roster.parquet') GROUP BY 1,2 ORDER BY 1,2")
q(f"SELECT count(*) FROM read_parquet('{DATA}/5_optional/shift_roster.parquet')")
print("\nroster overlap: for each fault ticket count matching roster rows")
q(f"""SELECT cnt, count(*) FROM (
 SELECT o.operation_id, count(r.assignment_id) cnt
 FROM read_parquet('{DATA}/2_machine_decision/operations.parquet') o
 LEFT JOIN read_parquet('{DATA}/5_optional/shift_roster.parquet') r
   ON r.role='slot_tech' AND o.opened_at_utc >= r.start_utc AND o.opened_at_utc < r.end_utc
 WHERE o.event_type='fault_repair' GROUP BY 1) GROUP BY 1 ORDER BY 1""")
print("\nledger redeem points sign")
q(f"SELECT count(*), sum(points_delta), min(points_delta), max(points_delta), sum(face_value_cents), sum(economic_cost_cents) FROM read_parquet('{DATA}/3_guests/loyalty_ledger.parquet') WHERE event_type='redeem'")
q(f"SELECT event_type, count(*), min(points_delta), max(points_delta) FROM read_parquet('{DATA}/3_guests/loyalty_ledger.parquet') GROUP BY 1")
print("\nfloor loc node types")
q(f"SELECT node_type, count(*) FROM read_parquet('{DATA}/2_machine_decision/floor_locations.parquet') GROUP BY 1")
q(f"SELECT location_id, parent_location_id, node_type, zone_id, bank_id FROM read_parquet('{DATA}/2_machine_decision/floor_locations.parquet') WHERE node_type='slot' LIMIT 5")
print("\nplayer_period months / tiers")
q(f"SELECT period_month, count(*), count(distinct player_id), sum(theo_usd), sum(comp_cost_usd) FROM read_parquet('{DATA}/1_prepared_views/player_period.parquet') GROUP BY 1 ORDER BY 1")
q(f"SELECT opening_tier, count(*) FROM read_parquet('{DATA}/1_prepared_views/player_period.parquet') GROUP BY 1")
print("\nzone traffic zones")
q(f"SELECT zone_id, count(*), min(hour_start_utc), max(hour_start_utc), count(distinct sensor_id) FROM read_parquet('{DATA}/4_context/zone_traffic_hourly.parquet') GROUP BY 1 ORDER BY 1")
q(f"SELECT counter_status, count(*) FROM read_parquet('{DATA}/4_context/zone_traffic_hourly.parquet') GROUP BY 1")
print("\nprepared zones")
q(f"SELECT zone_id, count(*), sum(available_hours), sum(theo_usd) FROM read_parquet('{DATA}/1_prepared_views/prepared_daily_view.parquet') WHERE active GROUP BY 1 ORDER BY 1")
print("\nproperties")
q(f"SELECT * FROM read_parquet('{DATA}/1_prepared_views/property_day.parquet') LIMIT 2")
