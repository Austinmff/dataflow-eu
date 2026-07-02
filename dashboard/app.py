import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine

st.set_page_config(page_title="DataFlow EU - Insights", page_icon="🇪🇺", layout="wide")

st.title("🇪🇺 Painel de Indicadores Econômicos da União Europeia")
st.markdown("Análise consolidada da camada **Gold** (Eurostat & BCE)")

DB_URI = "postgresql://dataflow:dataflow@postgres:5432/dataflow"

@st.cache_data
def load_data(query):
    engine = create_engine(DB_URI)
    return pd.read_sql(query, engine)

try:
    engine = create_engine(DB_URI)
    # Busca todas as tabelas em TODOS os schemas (exceto os internos do Postgres)
    table_query = """
        SELECT table_schema, table_name 
        FROM information_schema.tables 
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY table_schema, table_name;
    """
    tables_df = pd.read_sql(table_query, engine)
    
    if not tables_df.empty:
        # Cria uma lista formatada no padrão "schema"."tabela"
        tables_df['full_name'] = tables_df['table_schema'] + '."' + tables_df['table_name'] + '"'
        tables_list = tables_df['full_name'].tolist()
        
        st.sidebar.header("⚙️ Configurações do Painel")
        selected_table = st.sidebar.selectbox("Selecione a tabela de análise:", tables_list)
        
        # Carrega dados
        df = load_data(f'SELECT * FROM {selected_table}')
        
        st.markdown(f"### 📈 Visão Geral: `{selected_table}`")
        
        # Identifica colunas automaticamente para os gráficos
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        date_col = next((c for c in df.columns if 'date' in c or 'period' in c or 'time' in c), None)
        geo_col = next((c for c in df.columns if 'geo' in c or 'country' in c or 'pais' in c), None)
        
        # KPIs básicos
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total de Linhas", f"{len(df):,}")
        with col2:
            if numeric_cols:
                st.metric(f"Valor Médio ({numeric_cols[0]})", f"{df[numeric_cols[0]].mean():.2f}")
        with col3:
            if geo_col and geo_col in df.columns:
                st.metric("Países/Regiões", f"{df[geo_col].nunique()}")
                
        st.markdown("---")
        
        # Gráficos
        col_left, col_right = st.columns(2)
        
        with col_left:
            if date_col and numeric_cols:
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                df = df.sort_values(by=date_col)
                fig_line = px.line(df, x=date_col, y=numeric_cols[0], color=geo_col if geo_col else None,
                                   title="Evolução dos Indicadores no Tempo", template="plotly_dark")
                st.plotly_chart(fig_line, use_container_width=True)
            else:
                st.info("Sem colunas temporais ou numéricas para gráfico de linha.")
                
        with col_right:
            if categorical_cols and numeric_cols:
                top_cats = df.groupby(categorical_cols[0])[numeric_cols[0]].mean().reset_index()
                fig_bar = px.bar(top_cats, x=categorical_cols[0], y=numeric_cols[0],
                                 title="Comparativo por Categoria", template="plotly_dark")
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("Dados insuficientes para gráfico de barras.")
                
        st.markdown("---")
        st.write("### 📋 Visualização dos Dados Brutos")
        st.dataframe(df.head(100), use_container_width=True)
    else:
        st.warning("O banco de dados 'dataflow' está completamente vazio. Verifique os logs da `transformation_pipeline` no Airflow para confirmar se o dbt executou os modelos com sucesso e se inseriu linhas.")
        
except Exception as e:
    st.error(f"Erro ao conectar com a camada Gold: {e}")
