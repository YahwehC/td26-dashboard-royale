import duckdb, os, pandas as pd, numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data-repo", "data")
con = duckdb.connect()

# ---- A quick ----
df = con.execute(f"""
SELECT mh.machine_id, mh.gaming_date, mh.local_hour, mh.available_seconds, mh.coin_in_cents,
       mh.active, md.config_id, gm.configured_rtp,
       mh.coin_in_cents * (1-gm.configured_rtp)/100.0 AS theo,
       GREATEST(0, 3600-mh.available_seconds) AS down_s
FROM read_parquet('{DATA}/5_optional/machine_hour.parquet') mh
JOIN read_parquet('{DATA}/2_machine_decision/machine_day.parquet') md
  ON md.machine_id=mh.machine_id AND md.gaming_date=mh.gaming_date
JOIN read_parquet('{DATA}/2_machine_decision/game_math.parquet') gm ON gm.config_id=md.config_id
WHERE mh.active
""").df()
print("A rows", len(df), "theo", df.theo.sum(), "down_h", df.down_s.sum()/3600)
rate = df.groupby(['machine_id','local_hour']).apply(lambda g: g.theo.sum()/(g.available_seconds.sum()/3600), include_groups=False).rename('r')
df = df.join(rate, on=['machine_id','local_hour'])
df['lost'] = df.down_s/3600*df.r
print("lost", df.lost.sum(), "share", df.lost.sum()/df.theo.sum())
print("theo from machine_day", con.execute(f"SELECT sum(theo_cents)/100 FROM read_parquet('{DATA}/2_machine_decision/machine_day.parquet') WHERE active").fetchone())

# ---- B bank-hour ----
bh = con.execute(f"""
SELECT mh.machine_id, mh.hour_start_utc, mh.gaming_date, mh.local_hour,
       fl.bank_id, mh.available_seconds, mh.occupied_seconds,
       GREATEST(0,3600-mh.available_seconds) AS down_s
FROM read_parquet('{DATA}/5_optional/machine_hour.parquet') mh
JOIN read_parquet('{DATA}/2_machine_decision/floor_locations.parquet') fl
  ON fl.location_id=mh.location_id AND fl.node_type='slot'
WHERE mh.active
""").df()
print("bank null", bh.bank_id.isna().sum(), "rows", len(bh))
bh['isdown'] = bh.down_s>=1800
# k per bank-hour
g = bh.groupby(['bank_id','hour_start_utc','gaming_date','local_hour']).agg(k=('isdown','sum'), n=('machine_id','count')).reset_index()
print("k distribution", g.k.value_counts().sort_index().to_dict())
# occupancy excluding down machines
up = bh[~bh.isdown].groupby(['bank_id','hour_start_utc']).agg(occ_s=('occupied_seconds','sum'), av_s=('available_seconds','sum')).reset_index()
up['occ'] = up.occ_s/up.av_s
g = g.merge(up, on=['bank_id','hour_start_utc'], how='left')
g['weekday'] = pd.to_datetime(g['gaming_date']).dt.weekday
print("k>=1 bank-hours", (g.k>=1).sum(), "with occ", ((g.k>=1)&g.occ.notna()).sum(), "k0 with occ", ((g.k==0)&g.occ.notna()).sum())
cells = g.dropna(subset=['occ']).groupby(['bank_id','local_hour','weekday','k']).agg(occ=('occ','mean'), n=('occ','size')).reset_index()
p = cells.pivot_table(index=['bank_id','local_hour','weekday'], columns='k', values=['occ','n'])
print(p.head())
# both cells
both = cells.pivot_table(index=['bank_id','local_hour','weekday'], columns='k', values='occ').dropna()
w = cells[cells.k>=1].set_index(['bank_id','local_hour','weekday'])['n'].rename('w')
both = both.join(w).dropna()
both['diff']=both[1]-both[0]
print("cells both", len(both), "treated total", both.w.sum())
print("wmean diff", (both.w*both['diff']).sum()/both.w.sum(), "baseline", (both.w*both[0]).sum()/both.w.sum())

# ---- C ----
ro = con.execute(f"""
SELECT o.operation_id, o.machine_id, o.opened_at_utc, o.opened_at_local, o.work_started_at_utc,
       date_diff('second', o.opened_at_utc, o.work_started_at_utc)/3600.0 AS wait_h,
       r.shift, r.actual_headcount, r.planned_headcount, r.zone_id
FROM read_parquet('{DATA}/2_machine_decision/operations.parquet') o
JOIN read_parquet('{DATA}/5_optional/shift_roster.parquet') r
  ON r.role='slot_tech' AND o.opened_at_utc>=r.start_utc AND o.opened_at_utc<r.end_utc
WHERE o.event_type='fault_repair'
""").df()
print("C n", len(ro), "wait neg", (ro.wait_h<0).sum(), "null", ro.wait_h.isna().sum())
print(ro.groupby(['shift','planned_headcount','actual_headcount']).size())
print(ro[ro.actual_headcount<ro.planned_headcount]['shift'].value_counts())

# ---- E comp ----
comp = con.execute(f"""
SELECT c.gaming_date, -sum(l.points_delta) pts, sum(l.face_value_cents)/100.0 face,
       sum(l.economic_cost_cents)/100.0 cost, count(*) n
FROM read_parquet('{DATA}/3_guests/loyalty_ledger.parquet') l
JOIN read_parquet('{DATA}/2_machine_decision/calendar_day.parquet') c
  ON l.event_at_utc>=c.gaming_day_start_utc AND l.event_at_utc<c.gaming_day_end_utc
WHERE l.event_type='redeem'
GROUP BY 1 ORDER BY 1
""").df()
comp['ratio']=comp.pts/comp.face
print("E comp days", len(comp), comp.gaming_date.min(), comp.gaming_date.max())
# rolling detection variants
s = comp.set_index('gaming_date')['ratio']
print("first 5", s.head())
for mode in ['centered','trailing','leading']:
    first=None
    for i in range(7, len(s)-6):
        d=s.index[i]
        bef = s.iloc[i-7:i].mean()
        aft = s.iloc[i:i+7].mean()
        if aft < 0.7*bef:
            first=(d,bef,aft); break
    print(mode, first)
print(comp[(comp.gaming_date>='2025-04-25')&(comp.gaming_date<='2025-05-05')].to_string())
print("sum ratio before/after", comp[comp.gaming_date<'2025-05-01'].pts.sum()/comp[comp.gaming_date<'2025-05-01'].face.sum(),
      comp[comp.gaming_date>='2025-05-01'].pts.sum()/comp[comp.gaming_date>='2025-05-01'].face.sum())

# D closure quick
pv = con.execute(f"SELECT * FROM read_parquet('{DATA}/1_prepared_views/prepared_daily_view.parquet') WHERE active").df()
print("D rows", len(pv), pv.gaming_date.nunique())
pv['b40']=pv.zone_id=='Z-B40'
d = pv.groupby(['gaming_date','b40']).agg(theo=('theo_usd','sum'), av=('available_hours','sum')).reset_index()
print(d.head())
print("daily min av", d.av.min())

# F events / property
prop = con.execute(f"SELECT gaming_date, coin_in_usd, local_weekday FROM read_parquet('{DATA}/1_prepared_views/property_day.parquet')").df()
print("prop", len(prop), prop.coin_in_usd.isna().sum())
ev = con.execute(f"SELECT * FROM read_parquet('{DATA}/4_context/events.parquet')").df()
print(ev[['event_id','start_date','end_date']])
