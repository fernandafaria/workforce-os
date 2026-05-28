# Workforce OS — Arquitetura (Revisão Final)

**Versão:** 2.0  
**Data:** 2026-05-27  
**Status:** Para ratificação

---

## Princípio Fundador

> **Um motor. Uma base de dados. Duas skins. Zero duplicação.**

---

## Diagrama de Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        SKINS (Interface de Usuário)                      │
│                                                                          │
│  ┌──────────────────────────────┐  ┌──────────────────────────────┐     │
│  │       SECOND BRAIN            │  │         WORKFORCE             │     │
│  │       React 18 + Vite         │  │       React 18 + Vite         │     │
│  │                                │  │                               │     │
│  │  ICP: Tomador de decisão        │  │  Buyer: Empresa (CTO/VP)     │     │
│  │        (Gerente → CEO)           │  │                               │     │
│  │  Preço: R$497-2.497/mês/CPF     │  │  Preço: R$5-20k/mês/CNPJ     │     │
│  │  Modos: Criar Agente 24/7,     │  │  Modos: Squad Builder,       │     │
│  │         Conselho, Grupo,        │  │         Dashboard, Tasks     │     │
│  │         Board Export           │  │                               │     │
│  │  GTM: PLG + Inbound           │  │  GTM: Sales-led + Outbound   │     │
│  │  Deploy: Vercel               │  │  Deploy: Vercel              │     │
│  └──────────────┬───────────────┘  └──────────────┬────────────────┘     │
│                 │                                  │                      │
│                 │         HTTP/SSE (JSON)          │                      │
│                 └──────────────┬──────────────────┘                      │
│                                │                                          │
├────────────────────────────────┼──────────────────────────────────────────┤
│                                ▼                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                      API GATEWAY (FastAPI)                          │  │
│  │                                                                      │  │
│  │  /council     → Conselho 1:1 (SSE streaming)                        │  │
│  │  /group       → Grupo debate multi-agente (SSE)                     │  │
│  │  /ping        → Briefing diário                                     │  │
│  │  /personas    → Catálogo de agentes                                 │  │
│  │  /rituals     → Board review, deep dive, war room                   │  │
│  │  /memories    → Memória longitudinal                                │  │
│  │                                                                      │  │
│  │  Auth: Supabase JWT · Rate Limit: Upstash · Deploy: Railway         │  │
│  └──────────────────────────┬─────────────────────────────────────────┘  │
│                              │                                            │
│  ┌───────────────────────────┼─────────────────────────────────────────┐  │
│  │                    ORQUESTRAÇÃO (LangGraph)                          │  │
│  │                                                                      │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐    │  │
│  │  │     ROUTER      │  │    FORMATTER    │  │   ORCHESTRATOR    │    │  │
│  │  │                 │  │                 │  │                   │    │  │
│  │  │ query → embed   │  │ raw responses → │  │ Council: router   │    │  │
│  │  │ → match personas│  │ sumário +       │  │ → Send[] agents   │    │  │
│  │  │ → score + rank  │  │ perspectivas +  │  │ → aggregate       │    │  │
│  │  │ → return top-k  │  │ devil's adv. +  │  │ → format          │    │  │
│  │  │                 │  │ fontes          │  │                   │    │  │
│  │  └─────────────────┘  └─────────────────┘  │ Group: init →     │    │  │
│  │                                              │ loop[Send[]] →   │    │  │
│  │  Híbrido: pgvector    Template: Jinja2      │ consensus →       │    │  │
│  │  + regras domain-map  Output: JSON + MD     │ synthesize        │    │  │
│  │  + LLM refinamento                           └──────────────────┘    │  │
│  └───────────────────────────┬─────────────────────────────────────────┘  │
│                               │                                           │
│  ┌───────────────────────────┼─────────────────────────────────────────┐  │
│  │                    MCP SERVER (FastMCP)                              │  │
│  │                                                                      │  │
│  │  @mcp.tool        @mcp.resource        @mcp.prompt                  │  │
│  │                                                                      │  │
│  │  get_agent()       knowledge://          council_template            │  │
│  │  match_agents()    verticals/{name}      group_template              │  │
│  │  search_knowledge() agents/{slug}        ping_template               │  │
│  │  run_council()     memories/{user}       ritual_templates            │  │
│  │  run_group()                                                         │  │
│  │  run_ritual()      Transport: stdio + SSE + HTTP                     │  │
│  └───────────────────────────┬─────────────────────────────────────────┘  │
│                               │                                           │
├───────────────────────────────┼───────────────────────────────────────────┤
│                               ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                        DATA (Supabase)                               │  │
│  │                                                                      │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │  │
│  │  │  personas   │  │  knowledge  │  │   memory    │  │    auth    │ │  │
│  │  │             │  │             │  │             │  │            │ │  │
│  │  │ · 150 rows  │  │ · 7 verts   │  │ · decisions │  │ · JWT      │ │  │
│  │  │ · souls     │  │ · 72KB BR   │  │ · patterns  │  │ · RLS      │ │  │
│  │  │ · embeddings│  │ · agent KBs │  │ · timeline  │  │ · tenants  │ │  │
│  │  │ · domains   │  │ · pgvector  │  │ · pgvector  │  │            │ │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘ │  │
│  │                                                                      │  │
│  │  ┌─────────────────────────────────────────────────────────────┐   │  │
│  │  │  pg_cron: agent triggers 24/7 · enqueue_due_cron_triggers() │   │  │
│  │  │  Edge Functions: run-agent-trigger (LLM call + delivery)    │   │  │
│  │  │  Channels: Telegram · Slack · Discord (company_channels)    │   │  │
│  │  └─────────────────────────────────────────────────────────────┘   │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Separação de Responsabilidades

| Camada | Responsabilidade | Onde roda |
|--------|-----------------|-----------|
| **Skins** | Interface de usuário, fluxo de onboarding, UX específica do buyer | Vercel (React/Vite) |
| **API Gateway** | Autenticação, rate limiting, roteamento HTTP, SSE streaming | Railway (FastAPI) |
| **Orquestração** | Router, Formatter, LangGraph graphs, lógica de negócio | Railway (FastAPI) |
| **MCP Server** | Exposição de tools/resources/prompts, schema automático | Railway (FastMCP) |
| **Data** | Persistência, busca vetorial, auth, tarefas agendadas | Supabase |

### O que NÃO é responsabilidade de cada camada

| Camada | NÃO faz |
|--------|---------|
| Skins | Orquestração de agentes, busca vetorial, formatação hierárquica |
| API Gateway | Lógica de negócio, seleção de agentes, RAG |
| Orquestração | Persistência direta, autenticação, UI |
| MCP Server | Orquestração complexa (delega ao LangGraph), UI |
| Supabase | Compute (LLM calls, LangGraph, streaming) |

---

## 3. Fluxo de uma Requisição (Conselho 1:1)

```
1. CEO pergunta: "Devo reajustar o pricing enterprise em 6%?"
   │
2. Second Brain UI → POST /council
   │
3. API Gateway → valida JWT, rate limit
   │
4. ROUTER
   ├── embed_query("pricing enterprise reajuste 6%")
   ├── pgvector similarity search → personas
   ├── domain rules: "pricing" → @patrick-campbell, @bobby-pinero
   ├── LLM refine: "Adicione @april-dunford (posicionamento)"
   └── return: [patrick-campbell, bobby-pinero, april-dunford]
   │
5. ORCHESTRATOR (LangGraph)
   ├── StateGraph: CouncilSession
   ├── Node: framing → prepara prompt por agente
   ├── Send[] → 3 agentes em paralelo (get_agent_prompt + LLM call)
   ├── Node: aggregate → coleta respostas
   └── Node: check → verifica qualidade (modelo secundário)
   │
6. FORMATTER
   ├── Template Jinja2: council_hierarchical.j2
   ├── Estrutura: Summary → Perspectives → Devil's Advocate → Sources
   └── Output: JSON + Markdown
   │
7. API Gateway → SSE stream → Second Brain UI
   │
8. MEMORY (pós-resposta, async)
   ├── Observer: extrai decisão ("CEO decidiu reajustar +6%")
   └── Supabase: INSERT observational_memory
```

---

## 4. Stack Tecnológica

```yaml
runtime:
  language: Python 3.13
  framework: FastAPI
  orchestration: LangGraph (StateGraph, Send API, checkpointing)
  mcp: FastMCP (25.3k stars, 70% market share)
  rag: LangChain (embeddings, retrievers, document loaders)
  
data:
  primary: Supabase (PostgreSQL + pgvector)
  auth: Supabase Auth (JWT + RLS)
  cache: Upstash Redis (rate limiting, session cache)
  
frontend:
  framework: React 18 + Vite
  styling: tokens.css (Apple design system — existente)
  state: Zustand
  components: Shadcn/ui + custom (ChatBubble, SpecialistCard, etc.)
  
models:
  primary: DeepSeek V4 Pro (~90% chamadas)
  secondary: Claude Sonnet 4 (~10% — divergência, Board Mode)
  embeddings: Voyage AI (já configurado no Febrain)
  
deploy:
  api: Railway (FastAPI)
  frontend: Vercel (React/Vite)
  cron: Supabase pg_cron (briefings 24/7)
  
monitoring:
  tracing: LangSmith
  metrics: Prometheus + Grafana
  errors: Sentry
```

---

## 5. Estrutura de Diretórios

```
~/code/workforce-os/
│
├── api/                          # FastAPI + LangGraph Backend
│   ├── main.py                   # FastAPI app, endpoints
│   ├── mcp_server.py             # FastMCP server (tools/resources/prompts)
│   ├── router/
│   │   ├── central.py            # Router: embed → match → rank
│   │   └── domain_map.py         # Mapa de domínios → agentes
│   ├── orchestrator/
│   │   ├── council.py            # LangGraph: Conselho 1:1
│   │   ├── group.py              # LangGraph: Grupo debate
│   │   ├── ping.py               # LangGraph: Briefing diário
│   │   └── state.py              # State schemas (TypedDict)
│   ├── formatter/
│   │   ├── hierarchical.py       # Formatter hierárquico
│   │   └── templates/            # Jinja2 templates
│   ├── agents/
│   │   ├── catalog.py            # Supabase persona queries
│   │   └── loader.py             # Carrega SOUL + KB
│   ├── knowledge/
│   │   ├── retriever.py          # RAG: pgvector + Voyage
│   │   └── verticals.py          # 7 verticais setoriais
│   ├── memory/
│   │   └── store.py              # Memória longitudinal (Supabase)
│   ├── rituals/
│   │   └── runner.py             # Board review, deep dive, war room
│   └── auth/
│       └── jwt.py                # Supabase JWT validation
│
├── frontend/                     # React + Vite (Second Brain UI)
│   ├── src/
│   │   ├── screens/              # 18 telas do Second Brain
│   │   ├── components/           # ChatBubble, SpecialistCard, etc.
│   │   ├── hooks/                # useAgentCatalog, useCouncil, etc.
│   │   └── styles/               # tokens.css (design system)
│   └── index.html
│
├── shared/                       # Tipos e contratos
│   └── schemas.py                # Pydantic models compartilhados
│
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 6. Princípios de Design

1. **Skin não sabe de LangGraph.** Skin só chama POST /council.
2. **Router é pluggable.** Se um dia for 100% embedding, troca sem afetar resto.
3. **Formatter é template.** Jinja2. Layout novo = template novo, sem código.
4. **MCP Server é a interface canônica.** Toda tool/resource/prompt exposto via MCP.
5. **Supabase é shared-nothing com runtime.** Morreu API? Dados intactos. Subiu API nova? Conecta e continua.
6. **Modelo primário é DeepSeek V4 Pro.** Claude só onde precisar de divergência ou Board Mode.
7. **ICP é a decisão, não o cargo.** Gerente → CEO. A dor é a mesma: decidir sozinho sobre algo que afeta o negócio. O Router seleciona os mesmos agentes para um gerente de marketing e para um CEO. O que muda é o onboarding (setor, nível de senioridade, tipo de decisão frequente).

---

## 7. ICP Expandido — Second Brain

| Nível | Cargo típico | Decisão frequente | Agentes mais acionados |
|-------|-------------|-------------------|----------------------|
| **Gerente** | Gerente de Marketing, TI, Vendas | Contratar agência ou time interno? Trocar ferramenta? | @patrick-campbell, @april-dunford, @chris-voss |
| **Diretor** | Diretor Comercial, Operações, Produto | Reestruturar área? Entrar em novo segmento? | @rumelt, @roger-martin, @bobby-pinero |
| **VP** | VP de Estratégia, Growth, Tecnologia | M&A? Internacionalização? Stack tecnológico? | @roger-martin, @bill-gurley, @tim-cook |
| **C-level** | CEO, CFO, COO | Fundraising? Sucessão? Pricing estratégico? | @paul-graham, @ruth-porat, @naval-ravikant |

**Preço:** R$497-2.497/mês/CPF. Cartão corporativo. Sem aprovação de procurement.

**GTM:** PLG + Inbound. Free tier (3 consultas/mês) → conversão pra pago. O produto se vende na primeira sessão de Conselho.
