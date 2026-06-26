{{ config(
    materialized='incremental',
    unique_key=['dataset','country_code','year','month'],
    on_schema_change='fail',
    tags=['silver','eurostat']
) }}
with source as (
    select * from {{ ref('bronze_eurostat') }}
    {% if is_incremental() %}
        where year_month > (select coalesce(max(year_month), '2019-01') from {{ this }})
    {% endif %}
),
deduplicated as (
    select
        source, dataset, description, upper(trim(country_code)) as country_code,
        cast(year as integer) as year, cast(month as integer) as month, year_month,
        cast(value as double precision) as value, trim(unit) as unit, extracted_at,
        case when upper(trim(country_code)) like '%\_%' escape '\' then true else false end as is_aggregate,
        row_number() over (partition by dataset, country_code, year, month order by extracted_at desc) as row_num
    from source where value is not null
)
select source, dataset, description, country_code, year, month, year_month, value, unit, is_aggregate, extracted_at
from deduplicated where row_num = 1
