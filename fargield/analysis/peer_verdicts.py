"""Compare the GM's bottom 10 to same-game peers and to same-game machines outside Back Forty.
Rates are ratio-of-sums (theo per machine-day on active rows). Run from the project root."""
import duckdb

D = "challenge-repo/data/"
c = duckdb.connect()
c.sql(f"create view d as select * from '{D}1_prepared_views/prepared_daily_view.parquet' where active")
print(c.sql("""select theme, (zone_name='Back Forty') back_forty, count(distinct machine_id) machines,
  round(sum(theo_usd)/count(*)) theo_day, round(sum(occupied_hours)/sum(available_hours),3) occ
  from d group by 1,2 order by 1,2""").df().to_string(index=False))
print(c.sql("""select machine_id, theme, zone_name, count(*) n_days, round(sum(theo_usd)/count(*)) theo_day
  from d where machine_id in ('M-5076','M-1158','M-1120','M-1118','M-1238','M-1181','M-1035','M-1179','M-1017','M-1265')
  group by all order by theo_day""").df().to_string(index=False))
