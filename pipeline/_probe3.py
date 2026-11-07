import duckdb, os, pandas as pd, numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data-repo", "data")
con = duckdb.connect()
comp = con.execute(f"""
SELECT c.gaming_date, -sum(l.points_delta) pts, sum(l.face_value_cents)/100.0 face
FROM read_parquet('{DATA}/3_guests/loyalty_ledger.parquet') l
JOIN read_parquet('{DATA}/2_machine_decision/calendar_day.parquet') c
  ON l.event_at_utc>=c.gaming_day_start_utc AND l.event_at_utc<c.gaming_day_end_utc
WHERE l.event_type='redeem'
GROUP BY 1 ORDER BY 1
""").df()
s = comp.set_index('gaming_date')['pts']/comp.set_index('gaming_date')['face']
s.index = pd.to_datetime(s.index)
print(s.loc['2025-04-20':'2025-05-10'])

def first_where(after, before, scale=0.7):
    for i in range(7, len(s)-6):
        if after(i) < scale*before(i):
            return s.index[i]
    return None

variants = {}
# 1 mean of daily ratios, before [i-7,i), after [i,i+7)
variants['meanratio_lead'] = first_where(lambda i: s.iloc[i:i+7].mean(), lambda i: s.iloc[i-7:i].mean())
# 2 ratio of sums
variants['sumratio_lead'] = first_where(lambda i: s.iloc[i:i+7].sum()/7, lambda i: s.iloc[i-7:i].sum()/7)  # same
# centered MA at i vs i-7
ma = s.rolling(7, center=True).mean()
variants['centered_ma'] = next((s.index[i] for i in range(7,len(s)-6) if ma.iloc[i] < .7*ma.iloc[i-7]), None)
# trailing MA
ma2 = s.rolling(7).mean()
variants['trailing_ma'] = next((s.index[i] for i in range(7,len(s)) if ma2.iloc[i] < .7*ma2.iloc[i-7]), None)
# all 7 after days low
variants['all7low'] = first_where(lambda i: s.iloc[i:i+7].mean(), lambda i: s.iloc[i-7:i].mean()) if False else next((s.index[i] for i in range(7,len(s)-6) if (s.iloc[i:i+7] < .7*s.iloc[i-7:i].mean()).all()), None)
# first day after which 7-day mean low AND no day in window above 0.7*before
variants['sustain'] = next((s.index[i] for i in range(7,len(s)-6) if s.iloc[i:i+7].mean() < .7*s.iloc[i-7:i].mean() and (s.iloc[i:i+7] <= .7*s.iloc[i-7:i].mean()).all()), None)
# changepoint min SSE (mean model), min segment 7
best=None
for i in range(7,len(s)-7):
    a=s.iloc[:i]; b=s.iloc[i:]
    sse=((a-a.mean())**2).sum()+((b-b.mean())**2).sum()
    if best is None or sse<best[0]: best=(sse,s.index[i])
variants['changepoint']=best[1]
print(variants)
for name in ['meanratio_lead']:
    i=list(s.index).index(pd.Timestamp('2025-04-28'))
    print('4/28 after', s.iloc[i:i+7].mean(), 'before', s.iloc[i-7:i].mean(), 'thr', .7*s.iloc[i-7:i].mean())
    for d in ['2025-04-28','2025-04-29','2025-04-30','2025-05-01']:
        i=list(s.index).index(pd.Timestamp(d))
        print(d, 'after mean', round(s.iloc[i:i+7].mean(),3), 'before mean', round(s.iloc[i-7:i].mean(),3), 'thr', round(.7*s.iloc[i-7:i].mean(),3), 'max after', round(s.iloc[i:i+7].max(),3))
