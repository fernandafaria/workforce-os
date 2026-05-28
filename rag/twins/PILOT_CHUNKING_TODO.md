# Twin Corpus Chunking — Pilot (5 twins)

**Status:** Pendente — metadata dos 105 twins migrada para Supabase em 2026-05-12.
Os chunks de corpus (`public.twin_corpus_chunk`) ainda não foram populados
para nenhum twin.

## Pilot selecionado

5 twins com 2+ sources web (não-YouTube) e `authorization=public_figure`,
diversos por home_team. Selecionados automaticamente por
`scripts/migrate_twins_to_supabase.py --pilot-out`.

| id | home_team | URLs web confiáveis |
|---|---|---|
| `alex-xu` | tech-specialists | blog.bytebytego.com (newsletter + system design PDFs) |
| `ana-couto` | branding | anacouto.com.br, laje-ac.com.br |
| `andrew-ng` | (não declarado) | deeplearning.ai, wikipedia |
| `eugene-yan` | ai-engineering | eugeneyan.com/writing, eugeneyan.com |
| `sundar-pichai` | tech-leadership | (depende — checar `rag/twins/persons/sundar-pichai.yaml`) |

Lista canônica em `/tmp/twins_pilot.json` (regenerável via script).

## Por que não foi feito agora

O sandbox de desenvolvimento **não tem** `FIRECRAWL_API_KEY` nem `VOYAGE_API_KEY`
configuradas em `.env.local`. Tentar fetch + embed daqui falharia silenciosamente
ou consumiria contexto sem produzir dado real.

Também: a regra-mãe "YouTube só no DO runner" se aplica genericamente para
fetching de mídia — qualquer pipeline com proxy/embedding deve rodar no DO
runner para evitar bot-detection e ter egress aberto.

## Como executar (no DO runner)

```bash
# Pré-requisitos no DO runner:
# - FIRECRAWL_API_KEY (~$0.50 para 5 twins × 2 URLs)
# - VOYAGE_API_KEY (~$0.01 embedding)
# - psycopg2 com SUPABASE service-role connection string

cd /opt/syntheticalpha
python scripts/migrate_twins_to_supabase.py --pilot-out /tmp/twins_pilot.json

# Pipeline (a escrever — não existe ainda):
python rag/twins/run_pilot_chunking.py \
  --pilot-file /tmp/twins_pilot.json \
  --supabase-url $SUPABASE_URL \
  --service-role $SUPABASE_SERVICE_ROLE_KEY \
  --max-chunks-per-source 20
```

## Schema esperado em `twin_corpus_chunk`

```sql
INSERT INTO public.twin_corpus_chunk (
  person_id, source_url, source_type, source_date,
  first_person, text, token_count, quality_score, holdout, embedding
) VALUES (...);
```

`embedding` é `vector(1024)` (Voyage v4). `quality_score` é float 0-1
(heurística: comprimento normalizado + first_person bias).
`holdout=true` para 20% das chunks de cada twin (eval set).

## Métrica de sucesso do pilot

Para cada um dos 5 twins, depois do run:

```sql
SELECT person_id, COUNT(*) AS chunks, AVG(token_count) AS avg_tokens,
       SUM(token_count) AS total_tokens, SUM(holdout::int) AS holdout_count
FROM public.twin_corpus_chunk
WHERE person_id IN ('alex-xu','ana-couto','andrew-ng','eugene-yan','sundar-pichai')
GROUP BY person_id;
```

Esperado: 10-50 chunks por twin, avg_tokens ~400, holdout ≈ 20%.

Se um twin retorna 0 chunks: source URL bloqueou crawler ou conteúdo é muito
curto. Documentar em `rag/twins/persons/<id>.yaml` no campo `notes` e seguir
para próximo twin.
