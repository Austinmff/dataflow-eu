{% macro generate_year_month_spine(start_year=2019, end_year=none) %}
{% if end_year is none %}{% set end_year = run_started_at.year %}{% endif %}
with date_spine as (
{% for year in range(start_year, end_year + 1) %}{% for month in range(1, 13) %}
    select {{ year }} as year, {{ month }} as month, '{{ year }}-{{ '%02d' % month }}' as year_month
    {% if not (loop.last and loop.revindex0 == 0) %}union all{% endif %}
{% endfor %}{% if not loop.last %}union all{% endif %}{% endfor %}
)
select * from date_spine
{% endmacro %}
