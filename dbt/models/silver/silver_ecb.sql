{{ config(
    materialized='incremental',
    unique_key=['series_key','year','month'],
    on_schema_change='fail',
    tags=['silver','ecb']
) }}
with source as (
    select * from {{ ref('bronze_ecb') }}
    {% if is_incremental() %}
        where year_month > (select coalesce(max(year_month), '2019-01') from {{ this }})
    {% endif %}
),
labelled as (
    select
        source, series_key, description, period,
        cast(year as integer) as year, cast(month as integer) as month, year_month,
        cast(value as double precision) as value, trim(unit) as unit, extracted_at,
        case series_key
            when 'EXR.M.USD.EUR.SP00.A' then 'eur_usd_rate'
            when 'FM.B.U2.EUR.4F.KR.MRR_FR.LEV' then 'ecb_mro_rate'
            when 'BSI.M.U2.Y.V.M10.X.1.U2.2300.Z01.E' then 'm3_money_supply'
            else lower(replace(series_key, '.', '_'))
        end as series_label,
        row_number() over (partition by series_key, year, month order by extracted_at desc) as row_num
    from source where value is not null
)
select source, series_key, series_label, description, period, year, month, year_month, value, unit, extracted_at
from labelled where row_num = 1
