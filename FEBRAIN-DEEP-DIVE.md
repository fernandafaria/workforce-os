# Febrain Deep Dive — O que o Workforce OS deve wrappear, não reconstruir

**Data:** 2026-05-27  
**Escopo:** Análise completa do ecossistema Febrain para integração com Workforce OS

---

## 1. HERMES AGENTS — 150 agentes executáveis

```
~/code/Febrain/hermes/agents/
├── simon-willison/
│   ├── SOUL.md       ← Prompt completo da persona (5.8KB)
│   └── config.yaml   ← Config Hermes: modelo, system_prompt, runtime
├── andrej-karpathy/  (não exportado, mas tem knowledge base)
├── claire-vo/        ← CEO Orchestrator
├── ... 147 outros
└── README.md
```

**Cada agente tem:**
- **SOUL.md** — persona completa: Identity, Core Philosophy, Responsibilities, Communication Style
- **config.yaml** — runtime Hermes: modelo (anthropic/deepseek), system_prompt inline, reasoning_effort
- **Knowledge base** — em `teams/<time>/knowledge/<slug>/` — index.md + fontes crawleadas (blogs, papers, podcasts)
- **Supabase row** — `personas` table: slug, handle, persona_md, embedding (Voyage), domains, home_team, autonomous_template

**O que o Workforce OS DEVE usar:**
- `personas.persona_md` → system prompt (já estamos usando via AgentCatalog)
- `personas.embedding` → match_personas() RPC (pgvector similarity)
- `config.yaml` → modelo preferido do agente (Claude Opus vs DeepSeek)

---

## 2. MOTOR DE CRIAÇÃO DE PERSONAS — Pipeline completo

```
CRIAR AGENTE:
  python scripts/febrain_agents.py new --team ai-engineering --name "Eugene Yan"
  → Cria teams/ai-engineering/agents/eugene-yan.md com frontmatter YAML

VALIDAR:
  python scripts/febrain_agents.py validate
  → Checa contrato AGENT-PROFILE.md em todas as personas

SYNC (gerar artefatos):
  python scripts/febrain_agents.py sync
  → Regenera _meta/agent-registry.md + rag/agent_sources.json

EXPORT HERMES:
  python scripts/febrain_agents.py export-soul --slug simon-willison
  → Gera hermes/agents/simon-willison/SOUL.md + config.yaml

DEPLOY (seed Supabase):
  python supabase/seed_personas_skills.py
  → Upsert personas, skills, teams no Supabase
  → Gera embeddings (Voyage)
  → Popula autonomous_template

ATIVAR (24/7):
  INSERT INTO agent_triggers (company_id, persona_id, cron_expression, ...)
  → pg_cron dispara run-agent-trigger nos horários agendados
```

**O que o Workforce OS DEVE usar:**
- `febrain_agents.py export-soul` → exportar agentes pro formato Hermes
- `seed_personas_skills.py` → já roda no deploy do Febrain, mantém Supabase atualizado
- Agent triggers → pg_cron já faz briefing 24/7 (Ping mode)

---

## 3. OPENCLAW — Daemon de agentes pessoais

```
~/code/Febrain/openclaw/
├── agents/
│   ├── claire-vo/    ← Claire Vo como daemon pessoal
│   ├── jarvis/        ← Jarvis (assistente)
│   └── swyx/          ← Swyx (AI Engineering lead)
├── package.json       ← openclaw ^2026.4.15
└── README.md
```

**Função:** Daemon local persistente com cron + heartbeat nativos.  
**Canais:** WhatsApp, Discord, Matrix, Teams, Telegram.  
**Uso:** Agente pessoal do founder rodando local. Separado da infra multi-tenant.

**O que o Workforce OS DEVE usar:**
- OpenClaw como **runtime local** para o CEO (Second Brain pessoal)
- Ou: pg_cron + run-agent-trigger (Supabase) para o mesmo fim (preferível)

---

## 4. RAG SYSTEM — 130+ módulos Python

### Core RAG (produção)
```
rag/
├── embeddings.py       ← Voyage embeddings (text → vector)
├── retriever.py        ← pgvector similarity search + filters
├── reranker.py         ← Cross-encoder re-ranking
├── chunker.py          ← Markdown chunking inteligente
├── summarizer.py       ← Sumarização hierárquica (LLM)
├── structured_rag.py   ← RAG com output JSON estruturado
├── semantic_search.py  ← Busca semântica com filtros
└── classifier.py       ← Zero-shot topic classification
```

### Knowledge Management
```
rag/
├── firecrawl_updater.py   ← Crawleia fontes (blogs, sites) diariamente
├── indexer.py             ← Indexa documentos no pgvector
├── topics.py              ← BERTopic — descobre tópicos automaticamente
├── keyphrases.py          ← Extrai keywords (KBIR)
└── agent_sources.json     ← Fontes de cada agente (gerado por sync)
```

### Conversation & Memory
```
rag/
├── conversation_memory.py        ← Memória de conversa persistente
├── neural_conversation_session.py ← Sessão neural multi-turno
├── distill_memory.py             ← Compressão de conversas → observações
├── user_conversation_context.py  ← Contexto de usuário entre sessões
└── persona_lifecycle.py          ← Ciclo de vida da persona (criação → ativação)
```

### MCP Servers
```
rag/
├── server.py               ← MCP Server principal (28 tools, stdio)
├── server_febrain.py       ← MCP Server Febrain (stdio)
├── server_febrain_http.py  ← MCP HTTP Server (FastAPI, 8 tools)
├── server_http.py          ← MCP HTTP genérico
├── server_supabase.py      ← MCP Supabase
├── server_postgres.py      ← MCP PostgreSQL
└── mcp_evolved_tools.py    ← Ferramentas MCP evolutivas
```

**O que o Workforce OS DEVE usar:**
- `rag/retriever.py` — em vez de KnowledgeRetriever custom
- `rag/server_febrain_http.py` — MCP Server HTTP já existe, só rodar
- `rag/conversation_memory.py` — em vez de MemoryStore custom
- `rag/distill_memory.py` — em vez de Observer/Reflector custom

---

## 5. PIPELINES — Product Discovery + Triple Diamond

```
scripts/
├── handoff.py              ← D1→D2→D3 workflow (JSON, agent-native)
├── febrain_pipeline.py     ← Product Discovery Pipeline (7 stages)
├── febrain_agents.py       ← CRUD de personas
├── validate_memory.py      ← Validação de memória
├── validate_pipeline_personas.py ← Validação de personas
└── promote_persona.py      ← Promover persona (draft → canonical)

teams/triple-diamond/       ← Time dedicado
├── CLAUDE.md               ← Meta-orchestrator (Fernanda)
├── specialist-mapping.yaml ← 22 especialistas mapeados
├── memory/                 ← decisions-log, risks, action-items
└── orchestrator/
    └── conselho-conductor.md ← Prompt do orquestrador
```

---

## 6. RUNTIME 24/7 — pg_cron + Edge Functions

```
Supabase:
├── pg_cron (054_cron_tick.sql)
│   └── enqueue_due_cron_triggers() → processing_queue
├── supabase/functions/run-agent-trigger/
│   ├── lê trigger + persona
│   ├── chama LLM (Claude/DeepSeek)
│   ├── grava agent_runs (tokens, cost, output)
│   └── posta via company_channels (Slack/Telegram/Discord)
├── company_channels — Slack, Telegram, Discord
└── 45+ edge functions no total
```

**O que o Workforce OS DEVE usar:**
- `run-agent-trigger` → briefing diário (Ping) já existe
- `handoff-api` → Triple Diamond workflow já existe como edge function
- `company_channels` → entrega em canais já existe

---

## 7. O QUE O WORKFORCE OS REALMENTE PRECISA CONSTRUIR

| Camada | Febrain já tem | Workforce OS precisa construir |
|--------|---------------|------|
| **Agentes** | 150 personas + Hermes runtime | NADA — só referenciar |
| **Router** | `match_personas()` RPC | Domain rules map + LLM refinement (não existe) |
| **Orquestração** | `handoff.py` (D1→D2→D3) | **LangGraph graphs** (Council/Group/Ping) — NÃO EXISTE |
| **Formatter** | `structured_rag.py` | Templates Jinja2 hierárquicos (não existe) |
| **MCP Server** | 28 tools (stdio) | FastMCP HTTP wrapper (não existe) |
| **API Gateway** | NÃO EXISTE | FastAPI + SSE (não existe) |
| **Knowledge** | 7 verticais + RAG completo | NADA — só referenciar |
| **Memory** | `conversation_memory.py` + `observational_memory` | NADA — só referenciar |
| **Briefing 24/7** | pg_cron + run-agent-trigger | NADA — já funciona |
| **Auth** | Supabase Auth + RLS | NADA — já funciona |
| **Frontend** | Second Brain (React 18 telas) | NADA — já existe |

---

## 8. ARQUITETURA FINAL — Workforce OS como Thin Wrapper

```
Workforce OS (NOVO — o que construir)
│
├── api/main.py             ← FastAPI Gateway (NOVO)
├── api/orchestrator/        ← LangGraph graphs (NOVO — não existe no Febrain)
│   ├── council.py           ← Conselho 1:1
│   ├── group.py             ← Grupo debate
│   └── ping.py              ← Briefing (wrappa run-agent-trigger)
├── api/router/central.py    ← Domain rules + LLM refine (NOVO)
├── api/formatter/           ← Jinja2 templates (NOVO)
├── api/mcp_server.py        ← FastMCP HTTP wrapper (NOVO)
│
└── (todo o resto é Febrain)
    ├── Agentes: 150 personas no Supabase
    ├── Knowledge: 7 verticais + RAG (rag/retriever.py)
    ├── Memory: observational_memory + conversation_memory.py
    ├── Runtime: pg_cron + run-agent-trigger
    ├── Auth: Supabase JWT + RLS
    └── MCP: rag/server.py (28 tools)
```

**Total a construir: ~800 linhas Python.** O resto é Febrain.
