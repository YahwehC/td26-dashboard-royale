import duckdb, os, pandas as pd, numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data-repo", "data")
con = duckdb.connect()
bh = con.execute(f"""
SELECT mh.machine_id, mh.hour_start_utc, mh.gaming_date, mh.local_hour,
       fl.bank_id, mh.available_seconds, mh.occupied_seconds,
       GREATEST(0,3600-mh.available_seconds) AS down_s
FROM read_parquet('{DATA}/5_optional/machine_hour.parquet') mh
JOIN read_parquet('{DATA}/2_machine_decision/floor_locations.parquet') fl
  ON fl.location_id=mh.location_id AND fl.node_type='slot'
WHERE mh.active
""").df()
bh['isdown'] = bh.down_s>=1800
g = bh.groupby(['bank_id','hour_start_utc','gaming_date','local_hour']).agg(k=('isdown','sum')).reset_index()
g['treated'] = (g.k>=1).astype(int)
up = bh[~bh.isdown].groupby(['bank_id','hour_start_utc']).agg(occ_s=('occupied_seconds','sum'), av_s=('available_seconds','sum')).reset_index()
up['occ'] = up.occ_s/up.av_s
g = g.merge(up, on=['bank_id','hour_start_utc'], how='left')
g['weekday'] = pd.to_datetime(g['gaming_date']).dt.day_of_week
print('treated', g.treated.sum(), 'treated with occ', ((g.treated==1)&g.occ.notna()).sum())
cells = g.dropna(subset=['occ']).groupby(['bank_id','local_hour','weekday','treated']).agg(occ=('occ','mean'), n=('occ','size')).reset_index()
pv = cells.pivot_table(index=['bank_id','local_hour','weekday'], columns='treated', values='occ')
nn = cells.pivot_table(index=['bank_id','local_hour','weekday'], columns='treated', values='n')
both = pv.dropna(subset=[0,1]).join(nn[1].rename('w')).dropna()
both['diff']=both[1]-both[0]
print('cells', len(both), 'treated weight', both.w.sum())
wmean=(both.w*both['diff']).sum()/both.w.sum(); base=(both.w*both[0]).sum()/both.w.sum()
print('wmean diff', wmean, 'baseline', base, 'ratio', wmean/base)
# bootstrap
rng=np.random.default_rng(42)
d=both['diff'].to_numpy(); w=both['w'].to_numpy(); b=both[0].to_numpy()
bs=[]
for _ in range(1000):
    idx=rng.integers(0,len(d),len(d))
    bs.append((w[idx]*d[idx]).sum()/w[idx].sum())
print('CI', np.percentile(bs,[2.5,97.5]))
