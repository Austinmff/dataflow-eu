# LinkedIn Post Draft — DataFlow EU

---

## Versão em português (PT-PT, para o mercado de Portugal)

🇪🇺 Acabei de terminar o DataFlow EU — um pipeline de dados completo, end-to-end, construído para mostrar como trabalho como Data Engineer.

O que faz: extrai indicadores económicos (PIB, desemprego, inflação, taxas de câmbio) das APIs públicas do Eurostat e do BCE, transforma-os através de uma Arquitetura Medallion (Bronze → Silver → Gold) com dbt, valida a qualidade dos dados automaticamente com Great Expectations, e serve tudo num dashboard interativo em Streamlit.

Stack: Apache Airflow · dbt Core · PostgreSQL/DuckDB · Great Expectations · Docker Compose · GitHub Actions · Streamlit

O que tentei demonstrar, mais do que só "saber usar as ferramentas":

→ Decisões de arquitetura documentadas (ADRs) — porquê DuckDB em dev e PostgreSQL em produção, porquê Medallion em vez de subject-area, porquê TaskFlow API
→ Testes reais, não decorativos — 93% de cobertura, incluindo um bug genuíno que os testes apanharam antes de chegar a produção
→ CI/CD a sério — lint, testes, compilação dbt e build Docker correm a cada commit
→ Um runbook operacional — porque um pipeline só está "pronto" quando alguém consegue recuperá-lo às 3 da manhã sem mim por perto

Projeto 100% reprodutível com `make setup && make run`. Código aberto, ADRs incluídos, sem assumir nada que não esteja documentado.

🔗 [link do repositório]

À procura de oportunidades como Data Engineer em Portugal e Espanha. Aberto a conversas.

#DataEngineering #Airflow #dbt #Python #OpenToWork

---

## Versão em inglês (para alcance internacional)

🇪🇺 Just shipped DataFlow EU — a full end-to-end data pipeline built to show how I actually work as a Data Engineer, not just what tools I know.

What it does: ingests economic indicators (GDP, unemployment, inflation, exchange rates) from the Eurostat and ECB public APIs, transforms them through a Medallion Architecture (Bronze → Silver → Gold) with dbt, automatically validates data quality with Great Expectations, and serves it all through an interactive Streamlit dashboard.

Stack: Apache Airflow · dbt Core · PostgreSQL/DuckDB · Great Expectations · Docker Compose · GitHub Actions · Streamlit

What I tried to demonstrate, beyond just "knows the tools":

→ Documented architecture decisions (ADRs) — why DuckDB in dev and PostgreSQL in prod, why Medallion over subject-area, why the TaskFlow API
→ Tests that actually mean something — 93% coverage, including one real bug they caught before it would have hit production
→ CI/CD that's actually wired up — lint, tests, dbt compilation, and Docker build run on every commit
→ An operational runbook — because a pipeline isn't "done" until someone else can recover it at 3am without me around

100% reproducible with `make setup && make run`. Open source, ADRs included, nothing assumed that isn't documented.

🔗 [repo link]

Looking for Data Engineer opportunities in Portugal and Spain. Open to conversations.

#DataEngineering #Airflow #dbt #Python #OpenToWork

---

## Notes for Austin before posting

- Replace `[link do repositório]` / `[repo link]` with the actual GitHub URL
- Consider attaching 2-3 screenshots: the Streamlit dashboard, the dbt lineage graph (from `make dbt-docs`), and the GitHub Actions green checkmarks
- Post the PT version if targeting Portuguese recruiters/companies directly; post the EN version if also targeting international remote roles or Spain (many Spanish tech recruiters read English-language posts)
- Tag a couple of relevant hashtags but avoid hashtag spam — 4-5 is the sweet spot for LinkedIn's algorithm
- Best posting times for engagement: Tuesday-Thursday, 8-10am or 5-6pm local time