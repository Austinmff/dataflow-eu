"""
DataFlow EU — Painel de Indicadores Econômicos / Economic Indicators Dashboard / Panel de Indicadores Económicos
Camada Gold (Eurostat & BCE) via Medallion Architecture
"""

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine

# --------------------------------------------------------------------------
# Configuração da página
# --------------------------------------------------------------------------

st.set_page_config(
    page_title="DataFlow EU — Insights",
    page_icon="🇪🇺",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_URI = "postgresql://dataflow:dataflow@postgres:5432/dataflow"

# --------------------------------------------------------------------------
# Estilo (CSS customizado)
# --------------------------------------------------------------------------

st.markdown(
    """
    <style>
        .main { background-color: #0e1117; }
        div[data-testid="stMetric"] {
            background-color: #1c1f26;
            border: 1px solid #2a2e37;
            border-radius: 10px;
            padding: 16px 18px;
        }
        div[data-testid="stMetricLabel"] { font-size: 0.85rem; opacity: 0.75; }
        h1, h2, h3 { font-weight: 650; }
        .indicator-card {
            background-color: #1c1f26;
            border: 1px solid #2a2e37;
            border-radius: 10px;
            padding: 14px 18px;
            margin-bottom: 10px;
        }
        .indicator-card b { color: #6fb3ff; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# Indicadores — metadados independentes de idioma
# --------------------------------------------------------------------------

INDICATOR_META = {
    "gdp_per_capita_eur": {"unit": "€", "format": "€{:,.0f}", "higher_is_better": True},
    "unemployment_rate_pct": {"unit": "%", "format": "{:.1f}%", "higher_is_better": False},
    "inflation_rate_pct": {"unit": "%", "format": "{:.1f}%", "higher_is_better": None},
    "eur_usd_rate": {"unit": "US$", "format": "US$ {:.3f}", "higher_is_better": None},
    "ecb_mro_rate_pct": {"unit": "%", "format": "{:.2f}%", "higher_is_better": None},
}

FLAGS = {
    "AT": "🇦🇹", "BE": "🇧🇪", "BG": "🇧🇬", "CY": "🇨🇾", "CZ": "🇨🇿", "DE": "🇩🇪",
    "DK": "🇩🇰", "EE": "🇪🇪", "EL": "🇬🇷", "ES": "🇪🇸", "FI": "🇫🇮", "FR": "🇫🇷",
    "HR": "🇭🇷", "HU": "🇭🇺", "IE": "🇮🇪", "IT": "🇮🇹", "LT": "🇱🇹", "LU": "🇱🇺",
    "LV": "🇱🇻", "MT": "🇲🇹", "NL": "🇳🇱", "PL": "🇵🇱", "PT": "🇵🇹", "RO": "🇷🇴",
    "SE": "🇸🇪", "SI": "🇸🇮", "SK": "🇸🇰",
}

# --------------------------------------------------------------------------
# Traduções
# --------------------------------------------------------------------------

TEXT = {
    "pt": {
        "lang_label": "🌐 Idioma",
        "title": "🇪🇺 Painel de Indicadores Econômicos da União Europeia",
        "subtitle": (
            "Dados públicos do **Eurostat** e do **Banco Central Europeu (BCE)**, "
            "processados por um pipeline próprio (Airflow + dbt + Postgres) seguindo a "
            "**Medallion Architecture** (Bronze → Silver → Gold)."
        ),
        "warn_no_gold": "⚠️ A camada **Gold** ainda não foi populada. Verifique se a `transformation_pipeline` já executou com sucesso no Airflow.",
        "info_empty": "📭 As tabelas existem, mas ainda não têm linhas. Aguarde o backfill terminar de processar os meses no Airflow.",
        "error_conn": "❌ Erro ao conectar com a camada Gold: {e}",
        "sidebar_filters": "⚙️ Filtros",
        "sidebar_country": "País em foco",
        "sidebar_compare": "Comparar com outros países",
        "sidebar_caption": "💡 Os dados vêm da camada **Gold** do pipeline — já limpos, deduplicados e prontos para consumo analítico.",
        "tab_overview": "🏠 Visão Geral",
        "tab_series": "📈 Séries Temporais",
        "tab_compare": "🌍 Comparação entre Países",
        "tab_glossary": "📖 Glossário",
        "overview_subheader": "Situação mais recente — {country}",
        "overview_last_update": "Última atualização de dados: **{period}**",
        "overview_no_data": "Dados de comparação ainda não disponíveis para este país.",
        "yoy_suffix": "a/a",
        "rank_gdp": "🏆 Ranking de PIB per Capita",
        "rank_gdp_help": "Quanto menor o número, maior o PIB per capita",
        "rank_employment": "💼 Ranking de Emprego",
        "rank_employment_help": "Quanto menor o número, menor o desemprego",
        "rank_inflation": "💶 Ranking de Estabilidade de Preços",
        "rank_inflation_help": "Quanto menor o número, menor a inflação",
        "rank_of": "{rank}º de {total}",
        "series_subheader": "Evolução ao longo do tempo — {country}",
        "series_no_data": "Tabela `gold_eu_time_series` ainda não disponível.",
        "series_x_label": "Período",
        "series_country_label": "País",
        "compare_subheader": "Como os países da UE se comparam",
        "compare_no_data": "Tabela `gold_country_comparison` ainda não disponível.",
        "compare_select_label": "Indicador para comparar",
        "compare_chart_title": "{indicator} por país",
        "compare_country_col": "País",
        "compare_expander": "📋 Ver tabela completa",
        "glossary_subheader": "O que cada indicador significa",
        "glossary_caption": "Explicações em linguagem simples — pensadas para quem não trabalha diretamente com economia (como eu, construindo esse pipeline 😄).",
        "glossary_arch_title": "### Sobre a arquitetura dos dados",
        "glossary_arch_body": (
            "- **Bronze**: dados brutos, exatamente como vieram das APIs do Eurostat e do BCE.\n"
            "- **Silver**: dados limpos, deduplicados e com nomes padronizados.\n"
            "- **Gold**: dados agregados e prontos para análise — é o que este painel consome.\n\n"
            "Pipeline construído com **Apache Airflow** (orquestração), **dbt** (transformação), "
            "**PostgreSQL** (warehouse) e **Great Expectations** (qualidade de dados)."
        ),
        "indicators": {
            "gdp_per_capita_eur": {
                "label": "PIB per Capita",
                "explain": (
                    "Quanto cada habitante do país 'produziria' em média, em euros, se toda a "
                    "riqueza gerada no ano fosse dividida igualmente pela população. É o termômetro "
                    "mais usado para comparar o tamanho da economia entre países de tamanhos diferentes."
                ),
            },
            "unemployment_rate_pct": {
                "label": "Taxa de Desemprego",
                "explain": (
                    "Percentual da população em idade de trabalhar que está sem emprego, mas "
                    "ativamente procurando um. Quanto menor, geralmente melhor para a economia."
                ),
            },
            "inflation_rate_pct": {
                "label": "Inflação (HICP)",
                "explain": (
                    "Quanto os preços de bens e serviços subiram em relação ao ano anterior. "
                    "O ideal costuma ficar perto de 2% ao ano — inflação negativa ou muito alta "
                    "são ambas sinais de alerta para uma economia."
                ),
            },
            "eur_usd_rate": {
                "label": "Câmbio EUR/USD",
                "explain": (
                    "Quantos dólares americanos equivalem a 1 euro. É o mesmo indicador para "
                    "todos os países da zona do euro — mostra a força da moeda europeia frente ao dólar."
                ),
            },
            "ecb_mro_rate_pct": {
                "label": "Taxa de Juros do BCE",
                "explain": (
                    "A taxa básica de juros definida pelo Banco Central Europeu (equivalente à "
                    "Selic no Brasil). Influencia o custo do crédito, financiamentos e investimentos "
                    "em toda a zona do euro."
                ),
            },
        },
        "countries": {
            "AT": "Áustria", "BE": "Bélgica", "BG": "Bulgária", "CY": "Chipre", "CZ": "Tchéquia",
            "DE": "Alemanha", "DK": "Dinamarca", "EE": "Estônia", "EL": "Grécia", "ES": "Espanha",
            "FI": "Finlândia", "FR": "França", "HR": "Croácia", "HU": "Hungria", "IE": "Irlanda",
            "IT": "Itália", "LT": "Lituânia", "LU": "Luxemburgo", "LV": "Letônia", "MT": "Malta",
            "NL": "Holanda", "PL": "Polônia", "PT": "Portugal", "RO": "Romênia", "SE": "Suécia",
            "SI": "Eslovênia", "SK": "Eslováquia",
        },
    },
    "en": {
        "lang_label": "🌐 Language",
        "title": "🇪🇺 European Union Economic Indicators Dashboard",
        "subtitle": (
            "Public data from **Eurostat** and the **European Central Bank (ECB)**, "
            "processed by a custom pipeline (Airflow + dbt + Postgres) following the "
            "**Medallion Architecture** (Bronze → Silver → Gold)."
        ),
        "warn_no_gold": "⚠️ The **Gold** layer hasn't been populated yet. Check whether `transformation_pipeline` has run successfully in Airflow.",
        "info_empty": "📭 The tables exist but have no rows yet. Wait for the backfill to finish processing the months in Airflow.",
        "error_conn": "❌ Error connecting to the Gold layer: {e}",
        "sidebar_filters": "⚙️ Filters",
        "sidebar_country": "Focus country",
        "sidebar_compare": "Compare with other countries",
        "sidebar_caption": "💡 Data comes from the pipeline's **Gold** layer — already cleaned, deduplicated, and ready for analysis.",
        "tab_overview": "🏠 Overview",
        "tab_series": "📈 Time Series",
        "tab_compare": "🌍 Country Comparison",
        "tab_glossary": "📖 Glossary",
        "overview_subheader": "Latest snapshot — {country}",
        "overview_last_update": "Last data update: **{period}**",
        "overview_no_data": "Comparison data isn't available for this country yet.",
        "yoy_suffix": "YoY",
        "rank_gdp": "🏆 GDP per Capita Ranking",
        "rank_gdp_help": "The lower the number, the higher the GDP per capita",
        "rank_employment": "💼 Employment Ranking",
        "rank_employment_help": "The lower the number, the lower the unemployment",
        "rank_inflation": "💶 Price Stability Ranking",
        "rank_inflation_help": "The lower the number, the lower the inflation",
        "rank_of": "#{rank} of {total}",
        "series_subheader": "Evolution over time — {country}",
        "series_no_data": "The `gold_eu_time_series` table isn't available yet.",
        "series_x_label": "Period",
        "series_country_label": "Country",
        "compare_subheader": "How EU countries compare",
        "compare_no_data": "The `gold_country_comparison` table isn't available yet.",
        "compare_select_label": "Indicator to compare",
        "compare_chart_title": "{indicator} by country",
        "compare_country_col": "Country",
        "compare_expander": "📋 View full table",
        "glossary_subheader": "What each indicator means",
        "glossary_caption": "Plain-language explanations — written for people who don't work directly with economics (like me, building this pipeline 😄).",
        "glossary_arch_title": "### About the data architecture",
        "glossary_arch_body": (
            "- **Bronze**: raw data, exactly as it came from the Eurostat and ECB APIs.\n"
            "- **Silver**: cleaned, deduplicated data with standardized names.\n"
            "- **Gold**: aggregated data, ready for analysis — this is what this dashboard consumes.\n\n"
            "Pipeline built with **Apache Airflow** (orchestration), **dbt** (transformation), "
            "**PostgreSQL** (warehouse), and **Great Expectations** (data quality)."
        ),
        "indicators": {
            "gdp_per_capita_eur": {
                "label": "GDP per Capita",
                "explain": (
                    "How much each resident of the country would 'produce' on average, in euros, "
                    "if all the wealth generated in the year were split equally across the population. "
                    "It's the most common way to compare economy size across countries of different sizes."
                ),
            },
            "unemployment_rate_pct": {
                "label": "Unemployment Rate",
                "explain": (
                    "The percentage of the working-age population that is jobless but actively "
                    "looking for work. Lower is generally better for the economy."
                ),
            },
            "inflation_rate_pct": {
                "label": "Inflation (HICP)",
                "explain": (
                    "How much prices for goods and services rose compared to the previous year. "
                    "The ideal is usually close to 2% per year — both negative and very high inflation "
                    "are warning signs for an economy."
                ),
            },
            "eur_usd_rate": {
                "label": "EUR/USD Exchange Rate",
                "explain": (
                    "How many US dollars equal 1 euro. It's the same figure for all eurozone "
                    "countries — it shows the strength of the euro against the dollar."
                ),
            },
            "ecb_mro_rate_pct": {
                "label": "ECB Interest Rate",
                "explain": (
                    "The base interest rate set by the European Central Bank. It affects the cost "
                    "of credit, loans, and investment across the entire eurozone."
                ),
            },
        },
        "countries": {
            "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "CY": "Cyprus", "CZ": "Czechia",
            "DE": "Germany", "DK": "Denmark", "EE": "Estonia", "EL": "Greece", "ES": "Spain",
            "FI": "Finland", "FR": "France", "HR": "Croatia", "HU": "Hungary", "IE": "Ireland",
            "IT": "Italy", "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "MT": "Malta",
            "NL": "Netherlands", "PL": "Poland", "PT": "Portugal", "RO": "Romania", "SE": "Sweden",
            "SI": "Slovenia", "SK": "Slovakia",
        },
    },
    "es": {
        "lang_label": "🌐 Idioma",
        "title": "🇪🇺 Panel de Indicadores Económicos de la Unión Europea",
        "subtitle": (
            "Datos públicos de **Eurostat** y del **Banco Central Europeo (BCE)**, "
            "procesados por un pipeline propio (Airflow + dbt + Postgres) siguiendo la "
            "**Medallion Architecture** (Bronze → Silver → Gold)."
        ),
        "warn_no_gold": "⚠️ La capa **Gold** todavía no ha sido poblada. Verifique si el `transformation_pipeline` ya se ejecutó con éxito en Airflow.",
        "info_empty": "📭 Las tablas existen, pero aún no tienen filas. Espere a que el backfill termine de procesar los meses en Airflow.",
        "error_conn": "❌ Error al conectar con la capa Gold: {e}",
        "sidebar_filters": "⚙️ Filtros",
        "sidebar_country": "País en foco",
        "sidebar_compare": "Comparar con otros países",
        "sidebar_caption": "💡 Los datos provienen de la capa **Gold** del pipeline — ya limpios, deduplicados y listos para el análisis.",
        "tab_overview": "🏠 Resumen",
        "tab_series": "📈 Series Temporales",
        "tab_compare": "🌍 Comparación entre Países",
        "tab_glossary": "📖 Glosario",
        "overview_subheader": "Situación más reciente — {country}",
        "overview_last_update": "Última actualización de datos: **{period}**",
        "overview_no_data": "Los datos de comparación aún no están disponibles para este país.",
        "yoy_suffix": "interanual",
        "rank_gdp": "🏆 Ranking de PIB per Cápita",
        "rank_gdp_help": "Cuanto menor el número, mayor el PIB per cápita",
        "rank_employment": "💼 Ranking de Empleo",
        "rank_employment_help": "Cuanto menor el número, menor el desempleo",
        "rank_inflation": "💶 Ranking de Estabilidad de Precios",
        "rank_inflation_help": "Cuanto menor el número, menor la inflación",
        "rank_of": "{rank}º de {total}",
        "series_subheader": "Evolución en el tiempo — {country}",
        "series_no_data": "La tabla `gold_eu_time_series` aún no está disponible.",
        "series_x_label": "Período",
        "series_country_label": "País",
        "compare_subheader": "Cómo se comparan los países de la UE",
        "compare_no_data": "La tabla `gold_country_comparison` aún no está disponible.",
        "compare_select_label": "Indicador para comparar",
        "compare_chart_title": "{indicator} por país",
        "compare_country_col": "País",
        "compare_expander": "📋 Ver tabla completa",
        "glossary_subheader": "Qué significa cada indicador",
        "glossary_caption": "Explicaciones en lenguaje simple — pensadas para quien no trabaja directamente con economía (como yo, construyendo este pipeline 😄).",
        "glossary_arch_title": "### Sobre la arquitectura de los datos",
        "glossary_arch_body": (
            "- **Bronze**: datos brutos, tal como llegaron de las APIs de Eurostat y del BCE.\n"
            "- **Silver**: datos limpios, deduplicados y con nombres estandarizados.\n"
            "- **Gold**: datos agregados y listos para análisis — es lo que consume este panel.\n\n"
            "Pipeline construido con **Apache Airflow** (orquestación), **dbt** (transformación), "
            "**PostgreSQL** (warehouse) y **Great Expectations** (calidad de datos)."
        ),
        "indicators": {
            "gdp_per_capita_eur": {
                "label": "PIB per Cápita",
                "explain": (
                    "Cuánto 'produciría' en promedio cada habitante del país, en euros, si toda la "
                    "riqueza generada en el año se dividiera equitativamente entre la población. "
                    "Es el indicador más usado para comparar el tamaño de la economía entre países de distinto tamaño."
                ),
            },
            "unemployment_rate_pct": {
                "label": "Tasa de Desempleo",
                "explain": (
                    "Porcentaje de la población en edad de trabajar que está sin empleo, pero "
                    "buscando uno activamente. Cuanto menor, generalmente mejor para la economía."
                ),
            },
            "inflation_rate_pct": {
                "label": "Inflación (HICP)",
                "explain": (
                    "Cuánto subieron los precios de bienes y servicios respecto al año anterior. "
                    "Lo ideal suele estar cerca del 2% anual — tanto la inflación negativa como la "
                    "muy alta son señales de alerta para una economía."
                ),
            },
            "eur_usd_rate": {
                "label": "Tipo de Cambio EUR/USD",
                "explain": (
                    "Cuántos dólares estadounidenses equivalen a 1 euro. Es el mismo indicador para "
                    "todos los países de la zona euro — muestra la fuerza del euro frente al dólar."
                ),
            },
            "ecb_mro_rate_pct": {
                "label": "Tasa de Interés del BCE",
                "explain": (
                    "La tasa de interés base fijada por el Banco Central Europeo. Influye en el costo "
                    "del crédito, los financiamientos y las inversiones en toda la zona euro."
                ),
            },
        },
        "countries": {
            "AT": "Austria", "BE": "Bélgica", "BG": "Bulgaria", "CY": "Chipre", "CZ": "Chequia",
            "DE": "Alemania", "DK": "Dinamarca", "EE": "Estonia", "EL": "Grecia", "ES": "España",
            "FI": "Finlandia", "FR": "Francia", "HR": "Croacia", "HU": "Hungría", "IE": "Irlanda",
            "IT": "Italia", "LT": "Lituania", "LU": "Luxemburgo", "LV": "Letonia", "MT": "Malta",
            "NL": "Países Bajos", "PL": "Polonia", "PT": "Portugal", "RO": "Rumanía", "SE": "Suecia",
            "SI": "Eslovenia", "SK": "Eslovaquia",
        },
    },
}

LANG_OPTIONS = {"pt": "🇧🇷 Português", "en": "🇬🇧 English", "es": "🇪🇸 Español"}

# --------------------------------------------------------------------------
# Seletor de idioma (fica no topo da sidebar, fora de qualquer bloco de dados)
# --------------------------------------------------------------------------

lang_choice = st.sidebar.selectbox(
    "🌐 Idioma / Language / Idioma",
    options=list(LANG_OPTIONS.keys()),
    format_func=lambda k: LANG_OPTIONS[k],
    index=0,
)
T = TEXT[lang_choice]


def indicator_label(key: str) -> str:
    return T["indicators"].get(key, {}).get("label", key)


def country_label(code: str) -> str:
    name = T["countries"].get(code, code)
    return f"{FLAGS.get(code, '')} {name}".strip()


def format_value(value, indicator_key: str) -> str:
    if pd.isna(value):
        return "—"
    fmt = INDICATOR_META.get(indicator_key, {}).get("format", "{:.2f}")
    try:
        return fmt.format(value)
    except (ValueError, TypeError):
        return str(value)


# --------------------------------------------------------------------------
# Carga de dados
# --------------------------------------------------------------------------

@st.cache_resource
def get_engine():
    return create_engine(DB_URI)


@st.cache_data(ttl=600)
def load_table(table_name: str) -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql(f"SELECT * FROM gold.{table_name}", engine)


def table_exists(table_name: str) -> bool:
    engine = get_engine()
    query = """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'gold' AND table_name = %(t)s
    """
    result = pd.read_sql(query, engine, params={"t": table_name})
    return not result.empty


# --------------------------------------------------------------------------
# Cabeçalho
# --------------------------------------------------------------------------

st.title(T["title"])
st.markdown(T["subtitle"])

# --------------------------------------------------------------------------
# Verifica se há dados
# --------------------------------------------------------------------------

try:
    if not table_exists("gold_eu_indicators"):
        st.warning(T["warn_no_gold"])
        st.stop()

    indicators_df = load_table("gold_eu_indicators")
    timeseries_df = load_table("gold_eu_time_series") if table_exists("gold_eu_time_series") else pd.DataFrame()
    comparison_df = load_table("gold_country_comparison") if table_exists("gold_country_comparison") else pd.DataFrame()

    if indicators_df.empty:
        st.info(T["info_empty"])
        st.stop()

except Exception as e:
    st.error(T["error_conn"].format(e=e))
    st.stop()

# --------------------------------------------------------------------------
# Sidebar — filtros
# --------------------------------------------------------------------------

st.sidebar.header(T["sidebar_filters"])

available_countries = sorted(indicators_df["country_code"].dropna().unique().tolist())
default_country = "PT" if "PT" in available_countries else available_countries[0]

selected_country = st.sidebar.selectbox(
    T["sidebar_country"],
    options=available_countries,
    index=available_countries.index(default_country),
    format_func=country_label,
)

compare_countries = st.sidebar.multiselect(
    T["sidebar_compare"],
    options=[c for c in available_countries if c != selected_country],
    default=[c for c in ("DE", "ES", "FR") if c in available_countries and c != selected_country][:2],
    format_func=country_label,
)

st.sidebar.markdown("---")
st.sidebar.caption(T["sidebar_caption"])

# --------------------------------------------------------------------------
# Abas
# --------------------------------------------------------------------------

tab_overview, tab_series, tab_compare, tab_glossary = st.tabs(
    [T["tab_overview"], T["tab_series"], T["tab_compare"], T["tab_glossary"]]
)

# ---- Tab 1: Visão Geral -----------------------------------------------

with tab_overview:
    st.subheader(T["overview_subheader"].format(country=country_label(selected_country)))

    if not comparison_df.empty and selected_country in comparison_df["country_code"].values:
        row = comparison_df[comparison_df["country_code"] == selected_country].iloc[0]
        period = row.get("latest_period", "—")
        st.caption(T["overview_last_update"].format(period=period))

        cols = st.columns(4)
        metric_specs = [
            ("gdp_per_capita_eur", "gdp_per_capita_yoy_pct"),
            ("unemployment_rate_pct", "unemployment_yoy_pct"),
            ("inflation_rate_pct", "inflation_yoy_pct"),
            ("eur_usd_rate", None),
        ]
        for col, (key, delta_key) in zip(cols, metric_specs):
            meta = INDICATOR_META[key]
            value = row.get(key)
            delta = None
            delta_color = "normal"
            if delta_key and pd.notna(row.get(delta_key)):
                delta = f"{row[delta_key]:+.1f}% {T['yoy_suffix']}"
                if meta["higher_is_better"] is True:
                    delta_color = "normal"
                elif meta["higher_is_better"] is False:
                    delta_color = "inverse"
                else:
                    delta_color = "off"
            col.metric(
                indicator_label(key),
                format_value(value, key),
                delta=delta,
                delta_color=delta_color,
            )

        st.markdown("---")
        rank_cols = st.columns(3)
        rank_specs = [
            ("gdp_rank", T["rank_gdp"], T["rank_gdp_help"]),
            ("employment_rank", T["rank_employment"], T["rank_employment_help"]),
            ("inflation_rank", T["rank_inflation"], T["rank_inflation_help"]),
        ]
        for col, (key, label, help_text) in zip(rank_cols, rank_specs):
            rank_val = row.get(key)
            total = len(comparison_df)
            display = T["rank_of"].format(rank=int(rank_val), total=total) if pd.notna(rank_val) else "—"
            col.metric(label, display, help=help_text)
    else:
        st.info(T["overview_no_data"])

# ---- Tab 2: Séries Temporais -------------------------------------------

with tab_series:
    st.subheader(T["series_subheader"].format(country=country_label(selected_country)))

    if timeseries_df.empty:
        st.info(T["series_no_data"])
    else:
        countries_to_plot = [selected_country] + compare_countries
        ts = timeseries_df[timeseries_df["country_code"].isin(countries_to_plot)].copy()
        ts["country_label"] = ts["country_code"].map(country_label)
        ts["year_month"] = pd.to_datetime(ts["year_month"], format="%Y-%m", errors="coerce")

        indicators_present = [i for i in INDICATOR_META if i in ts["indicator"].unique()]
        grid = st.columns(2)

        for idx, ind_key in enumerate(indicators_present):
            meta = INDICATOR_META[ind_key]
            label = indicator_label(ind_key)
            sub = ts[ts["indicator"] == ind_key].sort_values("year_month")
            if sub.empty:
                continue

            fig = px.line(
                sub,
                x="year_month",
                y="value",
                color="country_label",
                title=f"{label} ({meta['unit']})",
                template="plotly_dark",
                labels={
                    "year_month": T["series_x_label"],
                    "value": label,
                    "country_label": T["series_country_label"],
                },
            )
            fig.update_layout(
                height=380,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                margin=dict(t=60, b=20, l=10, r=10),
            )
            grid[idx % 2].plotly_chart(fig, use_container_width=True)

# ---- Tab 3: Comparação entre Países -------------------------------------

with tab_compare:
    st.subheader(T["compare_subheader"])

    if comparison_df.empty:
        st.info(T["compare_no_data"])
    else:
        comp = comparison_df.copy()
        comp[T["compare_country_col"]] = comp["country_code"].map(country_label)

        available_metrics = [k for k in INDICATOR_META if k in comp.columns]
        metric_choice = st.selectbox(
            T["compare_select_label"],
            options=available_metrics,
            format_func=indicator_label,
        )
        meta = INDICATOR_META[metric_choice]
        label = indicator_label(metric_choice)

        ascending = not meta["higher_is_better"] if meta["higher_is_better"] is not None else False
        comp_sorted = comp.dropna(subset=[metric_choice]).sort_values(metric_choice, ascending=ascending)

        fig_bar = px.bar(
            comp_sorted,
            x=metric_choice,
            y=T["compare_country_col"],
            orientation="h",
            color=metric_choice,
            color_continuous_scale="Blues" if meta["higher_is_better"] else "Reds",
            title=T["compare_chart_title"].format(indicator=label),
            template="plotly_dark",
            labels={metric_choice: f"{label} ({meta['unit']})"},
        )
        fig_bar.update_layout(height=650, margin=dict(t=60, b=20, l=10, r=10))
        st.plotly_chart(fig_bar, use_container_width=True)

        with st.expander(T["compare_expander"]):
            display_cols = [T["compare_country_col"]] + [
                c for c in ("gdp_per_capita_eur", "unemployment_rate_pct", "inflation_rate_pct") if c in comp.columns
            ]
            rename_map = {c: indicator_label(c) for c in display_cols if c in INDICATOR_META}
            st.dataframe(
                comp[display_cols].rename(columns=rename_map),
                use_container_width=True,
                hide_index=True,
            )

# ---- Tab 4: Glossário ----------------------------------------------------

with tab_glossary:
    st.subheader(T["glossary_subheader"])
    st.caption(T["glossary_caption"])

    for key, meta in INDICATOR_META.items():
        label = indicator_label(key)
        explain = T["indicators"].get(key, {}).get("explain", "")
        st.markdown(
            f"""
            <div class="indicator-card">
                <b>{label}</b> ({meta['unit']})<br>
                {explain}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown(T["glossary_arch_title"])
    st.markdown(T["glossary_arch_body"])