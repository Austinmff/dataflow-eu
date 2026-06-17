{{ config(materialized='table', tags=['gold','country_comparison']) }}
with latest as (
    select *, row_number() over (partition by country_code order by year_month desc) as recency_rank
    from {{ ref('gold_eu_indicators') }}
),
prior_year as (
    select country_code, year, month, gdp_per_capita_eur as gdp_per_capita_eur_py,
        unemployment_rate_pct as unemployment_rate_pct_py, inflation_rate_pct as inflation_rate_pct_py, population as population_py
    from {{ ref('gold_eu_indicators') }}
)
select l.country_code, l.year, l.month, l.year_month as latest_period,
    l.gdp_per_capita_eur, l.unemployment_rate_pct, l.inflation_rate_pct, l.population, l.eur_usd_rate, l.ecb_mro_rate_pct,
    {{ pct_change('l.gdp_per_capita_eur', 'py.gdp_per_capita_eur_py') }} as gdp_per_capita_yoy_pct,
    {{ pct_change('l.unemployment_rate_pct', 'py.unemployment_rate_pct_py') }} as unemployment_yoy_pct,
    {{ pct_change('l.inflation_rate_pct', 'py.inflation_rate_pct_py') }} as inflation_yoy_pct,
    rank() over (order by l.gdp_per_capita_eur desc nulls last) as gdp_rank,
    rank() over (order by l.unemployment_rate_pct asc nulls last) as employment_rank,
    rank() over (order by l.inflation_rate_pct asc nulls last) as inflation_rank,
    current_timestamp as dbt_updated_at
from latest l
left join prior_year py on l.country_code = py.country_code and l.year - 1 = py.year and l.month = py.month
where l.recency_rank = 1
order by gdp_per_capita_eur desc nulls last
