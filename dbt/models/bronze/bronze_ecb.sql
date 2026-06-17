{{ config(materialized='view', tags=['bronze','ecb']) }}
select source, series_key, description, period, year, month, value, unit, extracted_at,
    year || '-' || lpad(cast(month as varchar), 2, '0') as year_month
from {{ source('bronze_raw', 'ecb_raw') }}
