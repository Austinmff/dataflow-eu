{{ config(materialized='table', tags=['gold','time_series']) }}
with indicators as (
    select
        country_code,
        year,
        month,
        year_month,
        'gdp_per_capita_eur' as indicator,
        'GDP per Capita (EUR)' as indicator_label,
        'EUR' as unit,
        gdp_per_capita_eur as value
    from {{ ref('gold_eu_indicators') }}
    where gdp_per_capita_eur is not null
    union all
    select
        country_code,
        year,
        month,
        year_month,
        'unemployment_rate_pct',
        'Unemployment Rate (%)',
        '%',
        unemployment_rate_pct
    from {{ ref('gold_eu_indicators') }}
    where unemployment_rate_pct is not null
    union all
    select
        country_code, year, month, year_month, 'inflation_rate_pct', 'HICP Inflation Rate (%)', '%', inflation_rate_pct
    from {{ ref('gold_eu_indicators') }}
    where inflation_rate_pct is not null
    union all
    select country_code, year, month, year_month, 'eur_usd_rate', 'EUR/USD Exchange Rate', 'USD', eur_usd_rate
    from {{ ref('gold_eu_indicators') }}
    where eur_usd_rate is not null
    union all
    select country_code, year, month, year_month, 'ecb_mro_rate_pct', 'ECB MRO Rate (%)', '%', ecb_mro_rate_pct
    from {{ ref('gold_eu_indicators') }}
    where ecb_mro_rate_pct is not null
)
select
    country_code, year, month, year_month, indicator, indicator_label, unit, value,
    avg(value)
        over (partition by country_code, indicator order by year_month rows between 11 preceding and current row)
    as rolling_avg_12m
from indicators
order by indicator, country_code, year_month
