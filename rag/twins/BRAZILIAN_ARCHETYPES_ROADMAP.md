# Brazilian Archetypes — Roadmap & Plano de Corpus

> **Propósito**: contrato vivo do plano de corpus dos 40 arquétipos populacionais brasileiros. Consolidado em 2026-04-27 numa sessão de planejamento (branch `claude/analyze-gstack-febrain-UJrYN`) para handoff entre sessões. Complementa `BRAZILIAN_ARCHETYPES.md` (status técnico) com **estratégia, fases e decisões pendentes**.
>
> **Quem lê isso:** qualquer sessão futura do Claude Code que vá disparar archetype, escrever spec novo, ou conectar Research Layer aos archetypes.

---

## 1. Contexto

A estratégia FeBrain de virar **fábrica de produtinhos LatAm** depende de uma camada de research que use archetypes sintéticos (LGPD-safe) para descobrir dores e validar variantes **antes** de escrever código. O gstack do Garry Tan (analisado na sessão de origem) acelera o lado da produção mas não traz research populacional — a Research Layer FeBrain é construção própria sobre os archetypes existentes em `rag/twins/persons/arch-*.yaml`.

**Regra-mãe inegociável (CLAUDE.md):** zero dados inventados. Toda URL/quote/stat vem de WebSearch ou fonte verificada. Dispatch 026/027 queimados com YT IDs chutados provaram o custo.

---

## 2. Estado atual (2026-04-27)

### Validados (passed Hamel Layer-1, p70 ≥ 0.72)

| # | Slug | p70 | Twin ID |
|---|---|---|---|
| 1 | `arch-c-mae-se-urbano` | 0.744 | confirmado em PR #202/#164 main |
| 16 | `arch-a-clevel-jovem` | 0.745 | `aebe2404-cc31-44e4-99a8-3006f78b4a55` (PR #211) |

**Cobertura validada:** ~25M adultos BR (cluster mãe C SE + cluster C-level jovem A).

### Specs prontos para dispatch (corpus já ingestado no DO runner)

| # | Slug | Chunks | Hold | Cobertura est. |
|---|---|---|---|---|
| 25 | `arch-c-universitario-primeira-gen` | 543 | 107 | ~6M |
| 29 | `arch-c-aposentado-inss` | 393 | 78 | ~14M |
| 24 | `arch-d-adolescente-periferia` | 148 | 29 | ~4M |
| 20 | `arch-d-desempregada-mae-solo` | 71 | 14 | ~3M |
| 15 | `arch-b-pequeno-empresario` | 61 | 13 | ~7M |

### Planejados sem spec

33 archetypes restantes — ver lista completa em `BRAZILIAN_ARCHETYPES.md` §"Os 40 arquétipos planejados".

**Cobertura projetada quando 40 estiverem validados:** ~100% adultos BR + decisor PJ pequeno/médio.

---

## 3. Gold standard de corpus

Padrão extraído do `arch-c-mae-se-urbano.yaml` (validado p70=0.744). Todo spec novo replica essa estrutura.

| Camada | Qtd mínima | Fontes recomendadas BR |
|---|---|---|
| Ethnografia acadêmica | 3 URLs | Scielo (RBCS, Cadernos Saúde Pública, Tempo Social USP), UFMG, PUC, Unisinos, FGV |
| Jornalismo longform | 3 URLs | Piauí, Agência Pública, Exame, Brazil Journal, InfoMoney, ECOA, Nexo |
| Dados estruturados | 2 URLs | IBGE PNAD, Sebrae, Datafolha, Latinobarómetro, Wikipedia PT (classes/renda) |
| Voz 1ª pessoa (YouTube) | 3-6 URLs | Mano a Mano, Mamilos, TVT, Brasil de Fato, Ponte Jornalismo, podcasts setoriais |
| **Total** | **≥ 11 sources** | **target ≥ 100 chunks pós-ingestão** |

**Regras inegociáveis:**
- Toda URL via WebSearch (regra-mãe)
- YouTube fetch SÓ no DO runner com Webshare proxy (sandbox Claude Code não funciona — bot-detection + firewall)
- Hamel Layer-1 p70 ≥ 0.72 — se não passar, **expandir corpus**, não baixar gate
- LGPD `authorization: archetype_synthetic` — agregado, nunca PII

---

## 4. Débitos técnicos a destravar (Fase 0)

Bloqueadores que precisam ser resolvidos antes de escalar:

1. ~~**Bug `ls -t` no dispatch selection**~~ — ✅ resolvido em `claude/brazilian-archetypes-phase-8MfFg` (Fase 0). `actions/checkout` zera mtimes; troca para `ls | sort | tail` aproveita o naming `YYYY-MM-DD-NNN-*.yml` para ordenação cronológica via lexical sort.
2. ~~**SQLite → Supabase migration**~~ — ✅ decisão tomada (Opção D, 2026-04-27). Migration `074a_entrepreneur_twins.sql` já checked-in com HNSW pgvector defaults. Falta apenas execução operacional (deploy verify + sync + re-eval) — ver §5 Plano Executável.
3. **Hamel Layer-2 (stylometry) + Layer-3 (LLM-judge pairwise)** — só scaffold em `eval_twin.py`. Layer-1 sozinho é suficiente para discovery, mas insuficiente para crítica.
4. **Composição cross-arquétipo** — chat simultâneo com 2+ archetypes ainda não existe. Necessário para discovery que precisa "olhar do aposentado" + "olhar da mãe C" sobre o mesmo produto.

---

## 5. Plano em 3 fases

### Fase 0 — Destravar (1-2 dias)

- [x] Fix bug `ls -t` no workflow → resolvido em `claude/brazilian-archetypes-phase-8MfFg` (`.github/workflows/twins-run.yml:179`, troca para `ls | sort | tail` lexical)
- [x] **Decisão SQLite → Supabase: Opção D** (Supabase managed + HNSW), confirmada por @fernanda em 2026-04-27 após board review com `@garry` + `@teresa` + `@chip`. Análise + plano executável abaixo.
- [x] Validar saldo Anthropic — @fernanda recargará para **$100** (2026-04-27). Cobre Fase 1 (~$25) + Fase 2 (~$25) com buffer ~$50 para iniciar Fase 3 (~10 dos 28 archetypes restantes; saldo adicional sob demanda da fábrica).

#### Análise: SQLite → Supabase migration (entrada para decisão @fernanda)

**Estado atual do código:**
- Migração `supabase/migrations/074a_entrepreneur_twins.sql` já está checked in (135 linhas, schema espelha 1:1 o SQLite local em `rag/twins/storage.py`).
- Sync script pronto: `rag/twins/sync_to_supabase.py` lê SQLite e escreve em Supabase via REST.
- DO runner usa SQLite em `rag/twins/twins.db` (build/eval/ingest).
- Webapp (`product/web/src/`) e edge functions (`product/supabase/functions/`) **ainda não referenciam** tabelas `twin_*` — confirmado via grep.
- `SYNC_GUIDE.md` reporta blocker como "awaiting Supabase DB password" — operacional, não de código.

**Opção A — Migrar agora (antes da Fase 2)**
- ✅ Webapp passa a ter base pra UI de archetypes (ainda precisa código frontend, mas dado fica acessível)
- ✅ Edge functions podem chamar twins (chat com archetype via API REST, sem precisar SSH no DO runner)
- ✅ Loop bidirecional da Research Layer (skill `pain-signal-scraping` escreve sinais nos `arch-*.yaml` → corpus expande) só funciona com twins em Supabase, porque o skill roda no servidor da webapp/edge function, não no DO runner
- ✅ Composição cross-arquétipo (débito técnico #4) fica viável com SQL nativo no Supabase em vez de juntar múltiplos `.db`
- ❌ Custo de tempo: ~1 dia (deploy migration + sync de 2 archetypes validados + smoke test)
- ❌ Pequeno risco de schema-breaking durante Fase 2 se descobrirmos campos faltando — mitigado por migrations incrementais

**Opção B — Adiar até pós-Fase 2 (≥12 archetypes validados)**
- ✅ Schema mais maduro depois de 12 specs (potencial economia em refactor)
- ✅ Fase 1 não bloqueada — DO runner roda sozinho com SQLite
- ❌ Research Layer travada: Fase 1 prevê escrever Research Layer "depois de ≥3 validados", mas sem Supabase a Layer não pode ler archetypes do servidor
- ❌ Sync de 12 archetypes em batch é mais arriscado que sync incremental de 1-2 (debug fica pior)
- ❌ Roadmap original explicitamente nota "Bloqueia acesso da webapp/agentes aos twins" — adiar prolonga o bloqueio

**Opção D — A + HNSW index (decisão final 2026-04-27)**
- A inteira (acima) +
- ✅ Performance de vector search: `074a:50-51` **já cria HNSW index** com pgvector defaults (`m=16, ef_construction=64`) — coincide exatamente com recomendação do `@chip` para corpus < 1M chunks. Não precisa nova migration. Search before building (`@garry`).
- ⚠️ HNSW é approximate retrieval — recall pode mudar vs scan linear (SQLite). Re-eval de `arch-c-mae-se-urbano` no Supabase é **obrigatória** antes de declarar Fase 0 fechada (`@chip`).

**Opção C (descartada):** GCP/AWS migration. Análise concluiu: 6 semanas de retrabalho sem ganho real no estado atual; AWS Activate credits não pagam Supabase (ToS), `074a` já checked-in há semanas, BYOC Supabase é Enterprise-only (custom pricing). Re-avaliar quando: cloud spend > $1k/mês OU corpus > 10M chunks OU DAU > 100k.

**Board votes (2026-04-27):** `@garry` D · `@teresa` D (caveat: spike testando assumption do pain-signal antes de codar Research Layer) · `@chip` D (caveat: re-eval pós-migração + HNSW config como acima)

**Plano executável (consolidado pelos 4 inputs):**

| # | Passo | Quem | Status |
|---|---|---|---|
| 1 | Verificar se `074a` deployou em prod (Supabase MCP `list_migrations`) | @fernanda (precisa auth Supabase) | ⏳ |
| 2 | Se não deployou: `supabase db push` ou re-trigger CI | @fernanda | ⏳ |
| 3 | ~~Criar migration HNSW~~ — **descartado**: `074a` já tem HNSW com defaults ótimos | — | ✅ skip |
| 4 | Rodar `python rag/twins/sync_to_supabase.py --db-path rag/twins/twins.db` para 2 archetypes validados | @fernanda (precisa `SUPABASE_SERVICE_ROLE_KEY`) | ⏳ |
| 5 | **Re-eval `arch-c-mae-se-urbano` contra Supabase** — gate p70 ≥ 0.72 (`@chip` obrigatório) | DO runner (precisa Anthropic + Supabase keys) | ⏳ |
| 6 | Smoke test cross-archetype query (proof Composição #4 funciona) | DO runner / SQL direto | ⏳ |
| 7 | Se passos 5-6 OK: marcar Fase 0 fechada e iniciar Fase 1 | — | ⏳ |

**Itens que ficam para Fase 1 (não bloqueiam Fase 0):**
- Spike de assumption testing (`@teresa`): testar manualmente com 50 queixas Reclame Aqui se categorização automática representa cluster, antes de codar `pain-signal-scraping`
- Hamel Layer-2/3 (`@chip` endorsa adiar): débito técnico independente, entra antes de shipping cross-archetype pra users finais

### Fase 1 — Fechar os 5 specs prontos (~1 semana, ~$25)

Corpus já ingestado no DO runner. Falta dispatch + eval.

**Sequência recomendada (corpus mais robusto primeiro, magro por último):**

1. `arch-c-universitario-primeira-gen` (543 chunks) — corpus mais forte, baseline confiável
2. `arch-c-aposentado-inss` (393 chunks) — alto impacto populacional
3. `arch-d-adolescente-periferia` (148 chunks)
4. `arch-d-desempregada-mae-solo` (71 chunks) — risco de gate por corpus magro
5. `arch-b-pequeno-empresario` (61 chunks) — risco de gate por corpus magro

**Regras operacionais:**
- 1 dispatch/dia (timeout 90min com corpus > 300 chunks)
- Build + eval custa ~$5/archetype Anthropic
- Se #4 ou #5 falharem gate p70 ≥ 0.72: **expandir corpus** (não baixar gate)
- Webshare proxy obrigatório no DO runner

**Resultado esperado:** 5-7 archetypes validados → cobertura ~50-60M adultos BR.

### Fase 2 — 5 archetypes high-impact (~3 semanas, ~$25 + ~25h escrita)

Critério de seleção: **alto peso populacional** + **utilidade direta pra fábrica de produtinhos**.

| # | Slug proposto | População | Por que |
|---|---|---|---|
| 2 | `arch-c-clt-operacional-jovem-pai` | ~15M | Base trabalhadora consumidora |
| 3 | `arch-c-app-worker-informal` | ~5M | Uber/iFood — ascendente, pain-rich |
| 5 | `arch-c-mei-vendedor-ne` | ~6M | B2B fábrica (cluster diferente do #15) |
| 10 | `arch-b-jovem-profissional` | ~8M | Early adopter SaaS / fintech |
| 21 | `arch-d-informal-norte` | ~5M | Cobertura regional faltante |

**Resultado esperado:** 12 archetypes validados → ~80% adultos BR cobertos.

### Fase 3 — Completar 28 restantes (~3-4 meses, ~$140 + ~140h)

Regional (5), minorias (4), demais classes (~19). Sequenciar **por demanda real da fábrica** — qual produtinho precisa de qual archetype. Não construir especulativamente.

---

## 6. Conexão com a Research Layer (loop fechado)

A Research Layer FeBrain (a ser construída em `_shared/templates/RESEARCH-LAYER-LOOP.md` + 3 skills + 1 persona em `product-discovery`) **só começa a ser escrita depois de ≥3 archetypes validados na Fase 1** — testar protocolo contra archetypes que falham gate enviesa o desenho.

### Decisões já tomadas para a Research Layer

- **Owner:** `@teresa-torres` + `product-discovery`
- **Skill `pain-signal-scraping`:** apenas protocolo Markdown na primeira iteração (sem Python stub)
- **Archetypes-exemplo nos skills:** `arch-c-mae-se-urbano` e `arch-a-clevel-jovem` (validados)

### Loop bidirecional com archetypes

O skill `pain-signal-scraping` **não é só consumidor** dos archetypes. Queixas coletadas em Reclame Aqui / Reddit-BR / YouTube comments viram **categoria nova de source** nos `arch-*.yaml`, expandindo corpus dos 12 archetypes além das 11 sources atuais.

**Implicação:** a Research Layer auto-melhora os archetypes ao longo do tempo. Cada produtinho lançado coleta pain signals → expande corpus dos clusters relevantes → archetype fica melhor → próximo produtinho gera melhor sinal.

---

## 7. Ordem de execução recomendada

1. **Hoje/amanhã:** Fase 0 (fix `ls -t` + decisão Supabase migration)
2. **Esta semana:** dispatch sequencial dos 5 prontos (Fase 1)
3. **Após ≥3 validados na Fase 1:** começar a escrever os 5 arquivos da Research Layer
4. **Próximas 3 semanas:** specs + dispatch dos 5 high-impact da Fase 2 em paralelo com pilotos da Research Layer
5. **Mensal a partir daí:** Fase 3 sob demanda da fábrica

---

## 8. Decisões pendentes (precisam de @fernanda)

| # | Decisão | Status / Bloqueia |
|---|---|---|
| 1 | ~~Quem fixa o bug `ls -t`?~~ | ✅ resolvido em PR #253 |
| 2 | ~~SQLite → Supabase agora ou depois de 12 archetypes?~~ | ✅ Opção D escolhida (Supabase + HNSW). Execução operacional pendente — ver §5 Plano Executável |
| 3 | Autorizar dispatch da Fase 1 (~$25, 5 dias DO runner)? | Fase 1 |
| 4 | Sequencial 1-a-1 ou batch de 2 dispatches em paralelo? | Throughput Fase 1 |
| 5 | **Executar passos 1-7 do plano Opção D** (precisa Supabase auth) | **Fase 0 fechamento** |

---

## 9. Handoff para próxima sessão

### Estado ao início da sessão 2026-04-27 (Fase 1 — branch `claude/fase-1-archetypes-dispatch-98b645`)

**Fase 0 — código travado (PR #253 mergeado):**
- ✅ Fix `ls -t` no `twins-run.yml` (lexical sort)
- ✅ Decisão Opção D (Supabase + HNSW) com board review @garry/@teresa/@chip
- ✅ Descoberta: `074a:50-51` já cria HNSW com pgvector defaults (`m=16, ef_construction=64`) — não precisa nova migration
- ✅ Saldo Anthropic recargado para $100 (cobre Fase 1+2 + buffer Fase 3)

**Fase 0 — operacional, status confirmado por @fernanda em 2026-04-27 (Fase 1 abrindo):**

| # | Passo | Status |
|---|---|---|
| 1 | `074a` deployou em prod (PR #250 catch-up 015-083) | ✅ aplicado, ⚠️ HNSW index ainda não verificado individualmente (#250 menciona patches em `074a` durante apply manual). |
| 2 | Re-trigger CI se necessário | ✅ N/A (já aplicado via #250) |
| 3 | Sync dos 2 archetypes validados via `sync_to_supabase.py` | ⚠️ **rodou parcialmente / falhou** — precisa retry/debug em sessão dedicada |
| 4 | Re-eval `arch-c-mae-se-urbano` contra Supabase (gate p70 ≥ 0.72) | ⏳ pendente (bloqueado pelo #3) |
| 5 | Smoke test cross-archetype query | ⏳ pendente (bloqueado pelo #3) |

**Decisão @fernanda 2026-04-27:** Fase 1 (dispatch + eval no DO runner) **prossegue em paralelo** com débito ops, já que DO runner usa SQLite local e não depende de Supabase para build/eval. Sync pra Supabase rodará retroativamente quando o passo 3 for desbloqueado.

**Não-bloqueante mas importante:**
- HNSW recall ainda não foi medido contra scan linear — re-eval (passo 4) continua sendo gate antes de declarar Fase 0 100% fechada.
- Próxima sessão pode (a) destravar passos 3-5 em paralelo com Fase 1, ou (b) deixar pra depois dos 3 archetypes validados, antes de iniciar Research Layer (que depende de Supabase pra escrever pain signals).

### Prompt sugerido ao abrir nova sessão (Fase 1)

> Continuação do trabalho do PR #253 (já mergeado, espero). Ler `rag/twins/BRAZILIAN_ARCHETYPES_ROADMAP.md` §5 antes de começar. Fase 0 fechada (Opção D travada, ops items 1-5 executados — confirmar status). Hoje vamos executar **Fase 1**: dispatch sequencial dos 5 specs prontos via `rag/twins/.dispatch/*.yml`, na ordem do §5 (corpus mais robusto primeiro: `arch-c-universitario-primeira-gen` 543 chunks → `arch-c-aposentado-inss` 393 → `arch-d-adolescente-periferia` 148 → `arch-d-desempregada-mae-solo` 71 → `arch-b-pequeno-empresario` 61). Regras: 1 dispatch/dia, gate p70 ≥ 0.72, se #4 ou #5 falharem **expandir corpus** (não baixar gate). Após ≥3 archetypes validados na Fase 1, começar Research Layer (owner @teresa-torres + product-discovery, scraper só protocolo Markdown, archetypes-exemplo `arch-c-mae-se-urbano` e `arch-a-clevel-jovem`).

### Decisões já tomadas (não relitigar)

- **Owner Research Layer:** `@teresa-torres` + `product-discovery`
- **Skill `pain-signal-scraping`:** apenas protocolo Markdown na primeira iteração (sem Python stub)
- **Archetypes-exemplo nos skills:** `arch-c-mae-se-urbano` e `arch-a-clevel-jovem` (validados)
- **Storage:** Supabase managed + pgvector HNSW (Opção D, decisão 2026-04-27). GCP/AWS migration descartada — re-avaliar só se cloud spend > $1k/mês OU corpus > 10M chunks OU DAU > 100k.
- **Specs novos** seguem template do `arch-c-mae-se-urbano.yaml` (≥11 sources, ≥100 chunks, p70 ≥ 0.72)
- **Spike de assumption testing** do `@teresa` (50 queixas Reclame Aqui categorização manual vs auto) entra **antes** de codar `pain-signal-scraping` na Research Layer

---

**Última atualização:** 2026-04-27 (sessão Fase 1 — branch `claude/fase-1-archetypes-dispatch-98b645`)
**Branch de origem:** `claude/brazilian-archetypes-phase-8MfFg` (PR #253) → `main`
**Próxima revisão:** após dispatch 030 (`arch-c-universitario-primeira-gen`) rodar — confirmar p70 ≥ 0.72 antes de seguir pro #2 da fila Fase 1 (`arch-c-aposentado-inss`).

### Fase 1 — sequência de dispatch (1 por dia)

| # | Slug | Chunks | Dispatch file | Status |
|---|---|---|---|---|
| 1 | `arch-c-universitario-primeira-gen` | 543 | `2026-04-27-030-*` | ⏳ disparado nesta sessão |
| 2 | `arch-c-aposentado-inss` | 393 | `2026-04-28-031-*` (a criar) | pendente |
| 3 | `arch-d-adolescente-periferia` | 148 | `2026-04-29-032-*` (a criar) | pendente |
| 4 | `arch-d-desempregada-mae-solo` | 71 | `2026-04-30-033-*` (a criar) | pendente — risco de gate |
| 5 | `arch-b-pequeno-empresario` | 61 | `2026-05-01-034-*` (a criar) | pendente — risco de gate |
