import duckdb, sys, os
os.chdir(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data-repo", "data"))
con = duckdb.connect()
for t,f in [("pdv","1_prepared_views/prepared_daily_view"),("pd","1_prepared_views/property_day"),("pp","1_prepared_views/player_period"),
            ("md","2_machine_decision/machine_day"),("gm","2_machine_decision/game_math"),("ops","2_machine_decision/operations"),
            ("pl","2_machine_decision/placements"),("mach","2_machine_decision/machines"),("fl","2_machine_decision/floor_locations"),
            ("cal","2_machine_decision/calendar_day"),("ses","3_guests/sessions"),("players","3_guests/players"),("led","3_guests/loyalty_ledger"),
            ("fnb","3_guests/fnb_transactions"),("trips","3_guests/trips"),("zt","4_context/zone_traffic_hourly"),("ev","4_context/events"),
            ("roster","5_optional/shift_roster"),("inc","5_optional/security_incidents"),("mh","5_optional/machine_hour"),
            ("city","4_context/real_sources/city_visitation_monthly"),("wx","4_context/real_sources/weather_daily")]:
    con.sql(f"create view {t} as select * from '{f}.parquet'")
def p(s, n=60):
    r=con.sql(s); print(r.columns)
    for x in r.fetchall()[:n]: print(tuple(round(v,4) if isinstance(v,float) else (float(v) if type(v).__name__=='Decimal' else v) for v in x))
    print()
if __name__=="__main__":
    for s in sys.stdin.read().split(";;"):
        if s.strip(): p(s)
