{{ config(materialized='table', tags=['gold','wide_table']) }}
with eurostat as (
    select
        country_code, year, month, year_month,
        max(case when dataset = 'nama_10_pc' then value end) as gdp_per_capita_eur,
        max(case when dataset = 'une_rt_m' then value end) as unemployment_rate_pct,
        max(case when dataset = 'prc_hicp_manr' then value end) as inflation_rate_pct,
        max(case when dataset = 'demo_pjan' then value end) as population
    from {{ ref('silver_eurostat') }} where is_aggregate = false
    group by country_code, year, month, year_month
),
ecb as (
    select
        year, month, year_month,
        max(case when series_label = 'eur_usd_rate' then value end) as eur_usd_rate,
        max(case when series_label = 'ecb_mro_rate' then value end) as ecb_mro_rate_pct,
        max(case when series_label = 'm3_money_supply' then value end) as m3_money_supply_eur_millions
    from {{ ref('silver_ecb') }}
    group by year, month, year_month
)
select
    e.country_code, e.year, e.month, e.year_month,
    e.gdp_per_capita_eur, e.unemployment_rate_pct, e.inflation_rate_pct, e.population,
    ecb.eur_usd_rate, ecb.ecb_mro_rate_pct, ecb.m3_money_supply_eur_millions,
    current_timestamp as dbt_updated_at
from eurostat e left join ecb on e.year_month = ecb.year_month
