# RoK KP Dashboard

Dashboard gratuito para importar exports do Rise of Kingdoms, guardar histórico e compartilhar métricas com aliados.

## Métricas

- T4 Kills: 5 pontos cada
- T5 Kills: 10 pontos cada
- T4 Deaths: 30 pontos cada
- T5 Deaths: 70 pontos cada

```text
DKPi = ((T4 Kills × 5) + (T5 Kills × 10) + (T4 Deaths × 30) + (T5 Deaths × 70)) / Power inicial do grupo
```

O app tem abas para `KP Geral`, `Metas`, `Kill Points`, `Death Points`, `Combined`, `Histórico`, `Jogadores` e `Imports`.

## Goals

A aba `Metas` compara os pontos combinados de cada jogador contra metas por faixa de power.

Preset inicial `Balanceado`:

| Faixa | Target DKPi |
| --- | ---: |
| 0-10M | 0.008 |
| 10M-30M | 0.012 |
| 30M-60M | 0.018 |
| 60M-90M | 0.024 |
| 90M+ | 0.030 |

```text
Target Points = Power atual × Target DKPi
Progress %    = Combined Points / Target Points
Gap to Goal   = max(Target Points − Combined Points, 0)
```

## Histórico

A aba `Histórico` mostra:
- Evolução do Combined Points, DKPi, Kill/Death e jogadores ativos ao longo do tempo
- Comparação direta entre qualquer par de relatórios importados

## Rodar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

Sem Supabase configurado, o app usa SQLite em `data/rok_dashboard.sqlite`.

## Publicar grátis online

1. Crie um repositório no GitHub e envie estes arquivos.
2. Crie um projeto gratuito no Supabase.
3. No Supabase, abra o SQL Editor e rode o conteúdo de `supabase_schema.sql`.
4. No Streamlit Community Cloud, crie um app apontando para o repositório e `app.py`.
5. Em `Settings > Secrets`, adicione:

```toml
SUPABASE_URL = "https://seu-projeto.supabase.co"
SUPABASE_KEY = "sua-service-role-key-ou-anon-key"
ADMIN_PASSWORD = "uma-senha-forte-para-lideranca"
```

Para uso compartilhado, prefira a `service_role key` guardada apenas nos Secrets do Streamlit.
Não coloque essa chave no GitHub.
Sem `ADMIN_PASSWORD`, a edição de metas fica bloqueada. Aliados ainda conseguem visualizar o dashboard.

## Fluxo de uso

1. Abra o dashboard online.
2. Faça upload do arquivo `statsExport.xlsx` ou `.xls`.
3. Confirme a data do relatório.
4. Use `Delta do período` quando houver mais de um relatório importado para ver apenas a diferença entre períodos.
5. Edite metas na aba `Metas` usando a senha admin.
6. Compartilhe o link do Streamlit com os aliados.

## Mudanças nesta versão

| Área | Melhoria |
| --- | --- |
| `app.py` | Aba **Histórico** com gráficos de evolução e comparação entre KVKs |
| `app.py` | Coluna **Death/Kill Ratio** na aba Jogadores |
| `app.py` | Métrica de **Participação** e **Jogadores Ativos** na aba KP Geral |
| `app.py` | **Paginação** na tabela de ranking completo |
| `app.py` | **Exportar metas CSV** na aba Metas |
| `app.py` | Scatter duplo na aba Jogadores (Power×Combined e Kill×Death) |
| `rok_metrics.py` | **Deduplicação** de character_id no normalize_stats |
| `rok_metrics.py` | Mensagens de erro em português |
| `rok_metrics.py` | Guard de 50 MB no upload |
| `rok_metrics.py` | `kingdom_summary()` helper para KPIs rápidos |
| `storage.py` | `aggregate_imports()` para histórico via SQL (evita carregar todos os DataFrames em memória) |
| `storage.py` | Pragmas adicionais (`cache_size`, `temp_store`) no SQLite |
| `storage.py` | Índice extra `rok_imports_date_idx` |
| `storage.py` | `SUPABASE_BATCH_SIZE` constante extraída |
| `supabase_schema.sql` | Índice `rok_stats_import_id_idx`; coluna `updated_at` em `rok_goal_bands` |
