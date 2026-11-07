"""Back Forty vs rest of floor (excl. High-Limit) before / during / after the Main Entrance - Back Forty
walkway closure (W-ENT-B40, 2025-03-03 to 2025-04-07). Ratio-of-sums. Run from the project root."""
import duckdb

D = "challenge-repo/data/"
c = duckdb.connect()
c.sql(f"create view d as select * from '{D}1_prepared_views/prepared_daily_view.parquet' where active")
c.sql("""create view p as select case when gaming_date<'2025-03-03' then '1_before' when gaming_date<'2025-04-07'
  then '2_closed' else '3_after' end period, zone_name='Back Forty' bf, theo_usd, 1 n
  from d where zone_name<>'High-Limit Room'""")
print(c.sql("""with t as (select period, bf, sum(theo_usd)/sum(n) x from p group by 1,2)
  select a.period, round(a.x) bf_theo_day, round(b.x) rest_theo_day, round(a.x/b.x,3) bf_vs_rest
  from t a join t b on a.period=b.period and a.bf and not b.bf order by 1""").df().to_string(index=False))
