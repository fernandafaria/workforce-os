# Workforce OS — Fork do Motor Febrain

**Status:** Em planejamento
**Decisão:** Workforce OS deixa de ser thin wrapper sobre Febrain e passa a ser o **dono do motor**. Febrain segue como repositório de origem das personas (curadoria editorial das SOULs), mas a infraestrutura de runtime, eval, lifecycle e geração on-demand é absorvida aqui.

---

## 1. Por que forkar

O motor real do Febrain não cabe em "wrapper de 800 linhas Python" como o `FEBRAIN-DEEP-DIVE.md` original sugeria. A auditoria do Supabase de produção (`ftlzbhmjjtetrchfcxtv`) revelou cinco sub-motores convivendo no mesmo schema, com tabelas, RPCs, edge functions, eval framework e governança próprias. Para o Workforce OS evoluir o produto (Conselho/Grupo/Ping/Rituais) sem ter que coordenar PRs entre dois repos, faz sentido absorver o que é runtime de execução e deixar no Febrain só o que é **fonte editorial das personas**.

Princípio operacional:

> **Febrain = fonte das SOULs.** Workforce OS = motor que as executa, eval-a, versionar, e (quando necessário) spawn agentes novos.

---

## 2. Escopo do fork

### 2.1. ✅ Entra no Workforce OS

| Sub-motor | O que é | Estado em prod | Esforço de absorção |
|-----------|---------|----------------|---------------------|
| **Council / Group / Ping** | Orquestração das 150 personas canonical via LangGraph + Router híbrido + Formatter hierárquico | Em uso. Embeddings recém-backfilled (150/150). | ✅ Já está aqui — refinar |
| **Persona Lifecycle + Eval** | `persona_versions`, `agent_evals`, `agent_eval_runs`, colunas `lifecycle_stage / promoted_at / deprecated_at / supersedes_persona_id / baseline_eval_run_id` | Schema deployado, 0 runs. Pipeline Python no Febrain (`scripts/promote_persona.py`, `rag/persona_lifecycle.py`). | 🟡 Médio — portar 2 scripts Python + 1 edge function de eval |
| **Dynamic Agents (spawn on-demand)** | Detecta lacuna de expertise no Council, gera agente temporário via LLM, eval, executa, dissolve. Tabelas `dynamic_agents` + `agent_spawn_log` (com `expertise_gap_embedding`, `parallel_group_id`, `max_uses`, `expires_at`) | Schema deployado, 0 spawns. Lógica de detecção+spawn no Febrain. | 🔴 Alto valor / médio esforço — é o diferencial do produto |
| **Synthetic Personas + Cohorts** | Geração de respondentes sintéticos para VoC/pesquisa. `synthetic_personas`, `synthetic_persona_cohorts`, `voc_raw_collected`, `voc_insights` | Schema + filesystem library no Febrain (`rag/synthetic_personas/library/cohorts/`). | 🟡 Médio — sub-produto auto-contido, fácil de modularizar |

### 2.2. ❌ Fica no Febrain (não absorver)

| Sub-motor | Por que fica fora |
|-----------|-------------------|
| **Twins (cognitive twins de pessoas reais)** | 105 twins ativos. É outro PRODUTO (twin pessoal vs board executivo), com corpus + interview + reliability eval próprios. Pode até virar Workforce OS Twin no futuro, em PR separado, mas hoje é confusão de escopo. |
| **Lorcana.ai** | Vertical separado, motor próprio, schema próprio. |
| **BR-Gov ingest pipeline** | Crawler de dados governamentais brasileiros. Independente do motor de personas. |
| **Curadoria editorial das 150 SOULs** | A escrita/edição dos `persona_md` continua no Febrain (markdown files em `teams/<team>/agents/<slug>.md`). Workforce OS consome o resultado. O fluxo `export-soul → seed_personas_skills.py → upsert no Supabase` permanece no Febrain. |

### 2.3. 🟡 Modular — depende de decisão posterior

| Sub-motor | Pergunta aberta |
|-----------|-----------------|
| **Cockpit Pipelines (`cockpit_pipeline_runs`, `team_missions`, `mission_runs`)** | É a engine multi-stage com gating humano. Útil pra rituais complexos (Board Review, Triple Diamond), mas hoje só tem 1 run histórica. Recomendação: portar quando começarmos a expor rituais com gates no Workforce OS. |
| **`handoff-api` edge function** | Triple Diamond workflow do Febrain. Conexão entre fases D1→D2→D3. Útil se quisermos expor Triple Diamond no Second Brain. |

---

## 3. Estrutura proposta do repo após fork

```
workforce-os/
├── api/                              # FastAPI gateway + orquestração (atual, evolui)
│   ├── main.py
│   ├── config.py
│   ├── auth/
│   ├── agents/
│   │   ├── catalog.py                # Query personas + match_personas RPC
│   │   ├── creator.py                # Trigger 24/7 agents
│   │   └── lifecycle.py              # 🆕 promote/deprecate/version personas
│   ├── orchestrator/
│   │   ├── __init__.py               # CouncilOrchestrator, GroupOrchestrator, PingOrchestrator (LangGraph)
│   │   └── _base.py
│   ├── router/central.py
│   ├── formatter/hierarchical.py
│   ├── knowledge/
│   │   ├── embeddings.py             # 🆕 Voyage helper centralizado
│   │   └── retriever.py
│   ├── memory/
│   │   ├── pipeline.py
│   │   └── store.py
│   ├── rituals/runner.py
│   ├── channels/telegram.py
│   ├── mcp_server.py
│   │
│   ├── dynamic_agents/               # 🆕 ABSORVIDO do Febrain
│   │   ├── detector.py               # Detecta gap de expertise no Council
│   │   ├── spawner.py                # Gera SOUL temporária via LLM
│   │   ├── eval.py                   # Eval rápido antes de usar
│   │   └── lifecycle.py              # max_uses, expires_at, dissolved_at
│   │
│   ├── synthetic_personas/           # 🆕 ABSORVIDO do Febrain (módulo de pesquisa)
│   │   ├── generator.py              # Gera N personas a partir de brief
│   │   ├── cohort.py                 # Compõe cohort (diversity axes)
│   │   ├── library.py                # Persistência (filesystem + Supabase)
│   │   └── voc.py                    # Voice of Customer rollup
│   │
│   └── evals/                        # 🆕 ABSORVIDO do Febrain
│       ├── persona_eval.py           # Roda eval contra baseline
│       ├── council_eval.py           # Eval da qualidade da resposta agregada
│       └── prompts/                  # Prompts de eval (consistency, depth, actionability)
│
├── supabase/
│   ├── functions/                    # Edge functions OWNED pelo Workforce OS
│   │   ├── backfill-persona-embeddings/   # ✅ deployada
│   │   ├── spawn-dynamic-agent/      # 🆕 cria agente temporário
│   │   ├── eval-persona/             # 🆕 roda eval contra baseline
│   │   └── generate-synthetic-cohort/  # 🆕 gera cohort de respondentes
│   └── migrations/
│       └── README.md                 # Migrations vivem no Febrain por enquanto;
│                                     # ver §5 para o plano de domain ownership
│
├── frontend/                         # React + Vite (Second Brain UI)
├── scripts/
│   ├── backfill_embeddings.py        # 🆕 invoca edge function via service_role
│   └── promote_persona.py            # 🆕 absorvido do Febrain
│
├── ARCHITECTURE.md                   # Reescrever após fork concluído
├── BUILD.md                          # Reescrever
├── FORK.md                           # ← este documento
├── FEBRAIN-DEEP-DIVE.md              # Mantém como referência histórica
├── NEXT-PHASES.md                    # Reescrever pós-fork
└── PROTOCOLS-RITUALS.md
```

---

## 4. Ordem de execução do fork

### Fase 0 — Foundations (este PR)

Já feito ou em curso neste branch:

- [x] Backfill de embeddings das 150 personas (Voyage-4, 1024d) — 150/150 sucesso
- [x] `match_personas` RPC chamada com `query_embedding` correto (era `query_text`)
- [x] Helper centralizado de Voyage embeddings (`api/knowledge/embeddings.py`)
- [x] Memory injection no Council (busca top-5 memórias do user antes da sessão)
- [x] `user_id` real propagado para o orchestrator (não mais `"anonymous"` hardcoded)
- [x] `model_ref` corrigido no banco (21 orchestrators → claude-opus-4-7, 129 specialists → deepseek-chat)
- [x] RLS habilitada em `observational_memory` + `memory_embeddings`
- [x] Migration `001_initial_schema.sql` convertida em stub de aviso (era fantasia)
- [x] `vercel.json` da raiz removido (era incompatível — frontend já tem o seu)
- [x] Orchestrators duplicados (`council.py / group.py / ping.py`) removidos — única implementação no `__init__.py`
- [x] Edge function `backfill-persona-embeddings` deployada (v2, idempotente)

### Fase 1 — Persona Lifecycle + Eval (1-2 dias)

- [ ] Portar `scripts/promote_persona.py` do Febrain → `scripts/promote_persona.py`
- [ ] Portar `rag/persona_lifecycle.py` → `api/agents/lifecycle.py`
- [ ] Edge function `eval-persona` (workforce-os/supabase/functions/) que roda eval contra `baseline_eval_run_id`
- [ ] Endpoint `POST /personas/{slug}/eval` no FastAPI
- [ ] Endpoint `POST /personas/{slug}/promote` (atomic: cria nova versão, roda eval, promove se score >= baseline)

### Fase 2 — Dynamic Agents (2-3 dias)

- [ ] `api/dynamic_agents/detector.py` — detecta gap após o Council ter rodado (responses inconsistentes ou cobertura baixa)
- [ ] `api/dynamic_agents/spawner.py` — gera SOUL temporária (DeepSeek), faz eval rápido, insere em `dynamic_agents`
- [ ] Edge function `spawn-dynamic-agent` para spawn cross-process
- [ ] LangGraph node opcional no Council: `framing → execute_agents → check_coverage → [spawn?] → re-execute → synthesize`
- [ ] TTL: `expires_at = now() + interval '24h'`, cron job que move pra `status='dissolved'`

### Fase 3 — Synthetic Personas (2 dias)

- [ ] Portar `rag/synthetic_personas/library/cohorts/` (filesystem library) → `data/cohorts/`
- [ ] `api/synthetic_personas/generator.py` (LLM-based)
- [ ] `api/synthetic_personas/cohort.py` com `diversity_axes`
- [ ] Endpoints `POST /cohorts`, `GET /cohorts/{slug}`, `POST /cohorts/{slug}/run` (responder a brief)
- [ ] Edge function `generate-synthetic-cohort`

### Fase 4 — Hardening (1 dia)

- [ ] Rate limiting (slowapi) em todos os endpoints expostos
- [ ] CORS por env var (`ALLOWED_ORIGINS` em vez de `*`)
- [ ] CI: pytest mockando LLMs + lint Python + lint TS
- [ ] Telegram webhook signature verification
- [ ] Trace via LangSmith (já tem `langgraph_runs` table no banco)

---

## 5. Domain ownership pós-fork

| Domínio | Owner | Repo |
|---------|-------|------|
| Curadoria das 150 SOULs (markdown editorial) | Febrain | `Febrain/teams/*/agents/*.md` |
| Pipeline `export-soul → seed_personas_skills.py` (transformar md em row) | Febrain | `Febrain/scripts/` + `Febrain/supabase/seed_personas_skills.py` |
| Schema das tabelas core (personas, memories, etc) | Febrain *(por enquanto)* | `Febrain/supabase/migrations/` |
| Lifecycle/eval de personas (executar promoções) | Workforce OS | `workforce-os/api/agents/lifecycle.py` |
| Council/Group/Ping orchestration | Workforce OS | `workforce-os/api/orchestrator/` |
| Router (match_personas client + domain rules) | Workforce OS | `workforce-os/api/router/` + `agents/catalog.py` |
| Memory pipeline (observe/distill/embed/search) | Workforce OS | `workforce-os/api/memory/` |
| Dynamic agent spawn | Workforce OS | `workforce-os/api/dynamic_agents/` |
| Synthetic personas / cohorts | Workforce OS | `workforce-os/api/synthetic_personas/` |
| Twins (corpus + interview + eval) | Febrain | `Febrain/rag/twin/` + `Febrain/supabase/functions/twin-*` |
| Edge functions de embedding genéricas | Febrain | `Febrain/supabase/functions/generate-embedding` |
| Edge functions específicas do motor | Workforce OS | `workforce-os/supabase/functions/` |

**Schema das tabelas:** por enquanto, fica no Febrain. Migrations passam pelo repo Febrain → aplicadas no Supabase compartilhado. Quando o Workforce OS estiver com 3+ tabelas novas dele (dynamic_agents fica complicado, evals, etc), avaliamos mover ownership do schema dessas tabelas específicas pra cá.

---

## 6. Riscos & mitigações

| Risco | Mitigação |
|-------|-----------|
| Duplicação de código Python (Febrain tem `rag/`, Workforce OS portará pedaços) | Portar somente o que executa em runtime do motor. Curadoria (markdown, scripts de seed) fica no Febrain. |
| Schema drift entre os dois repos | Por enquanto, single source of truth = Febrain migrations. Workforce OS NÃO escreve migrations no schema compartilhado sem PR no Febrain. |
| Edge functions sobreescritas | Edge functions do Workforce OS são prefixadas com namespace claro (`backfill-*`, `spawn-*`, `eval-persona`) e ficam em `workforce-os/supabase/functions/`. Edge functions do Febrain (`generate-embedding`, `agent-chat`, etc) permanecem no Febrain. |
| Custo de Voyage / LLM dispara com dynamic_agents | TTL agressivo (`expires_at = now() + 24h`), `max_uses` por agente, `cost_ledger` já existe e captura tudo. Alert no `budget_tracking`. |
| Personas perdem qualidade quando editadas no Febrain | Eval pipeline obriga `agent_evals` run com score >= `baseline_eval_run_id` antes de `promoted_at` ser setado. Workforce OS expõe esse gate via `POST /personas/{slug}/promote`. |

---

## 7. O que NÃO vai mudar

- Frontend (Second Brain React/Vite) — continua igual. O fork é backend.
- Schema de produção — só evoluímos via migrations no Febrain por ora.
- Modelos default — DeepSeek para specialists, Claude Opus 4.7 para orchestrators (a partir do fix de `model_ref` neste PR).
- Voyage como provider de embeddings — voyage-4, 1024 dimensões.
- Supabase como base — não há intenção de trocar de provider.

---

*Documento vivo. Atualizar a cada fase concluída.*
