{{ config(materialized='view', tags=['bronze','eurostat']) }}
select
    source, dataset, description, country_code, year, month, value, unit, extracted_at,
    year || '-' || lpad(cast(month as varchar), 2, '0') as year_month
from {{ source('bronze_raw', 'eurostat_raw') }}
