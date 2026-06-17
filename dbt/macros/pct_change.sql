{% macro pct_change(current_col, prior_col) %}
case when {{ prior_col }} is null or {{ prior_col }} = 0 then null
else round(cast(({{ current_col }} - {{ prior_col }}) / {{ prior_col }} * 100 as numeric), 2)
end
{% endmacro %}
