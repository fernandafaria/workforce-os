# Workforce OS — Build Prompt

**Target:** Agent coding (Joe, Codex, Claude Code, etc.)
**Repo:** `thecognitivelab/workforceOS`
**Status:** Core motor funcional. Expandir para produção.

---

## 1. O QUE É

Workforce OS é uma plataforma que orquestra 150+ agentes especialistas (FeBrain) com knowledge bases setoriais. **Um motor. Duas skins.**

```
                  WORKFORCE OS MOTOR
                 (FastAPI + LangGraph + Supabase)
                        │
          ┌─────────────┴─────────────┐
          ▼                           ▼
    SECOND BRAIN                  WORKFORCE
    Tomador de decisão            Empresas
    R$497-2.497/mês/CPF          R$5-20k/mês/CNPJ
    PLG + Inbound                Sales-led
```

**Princípio fundador:** Tudo que enriquece o motor enriquece todas as skins. Skins não duplicam lógica.

---

## 2. STACK

```yaml
backend:
  language: Python 3.13
  framework: FastAPI
  orchestration: LangGraph
  mcp: FastMCP
  rag: LangChain + Voyage embeddings

data:
  primary: Supabase (PostgreSQL + pgvector)
  auth: Supabase Auth (JWT + RLS)
  cache: Upstash Redis

frontend:
  framework: React 18 + Vite
  styling: tokens.css (Apple design system)
  state: Zustand
  components: Shadcn/ui + custom

models:
  primary: DeepSeek V4 Pro (~90%)
  secondary: Claude Sonnet 4 (~10% — divergência/Board Mode)
  embeddings: Voyage AI

deploy:
  api: Railway
  frontend: Vercel
  cron: Supabase pg_cron
```

---

## 3. O QUE JÁ EXISTE

### Backend (`api/`) — 27 arquivos Python

| Módulo | Arquivo | Estado | Descrição |
|--------|---------|--------|-----------|
| API Gateway | `main.py` | ✅ Funcional | 11 endpoints: health, council, group, ping, personas, domains, memories, rituals, agents, MCP |
| Config | `config.py` | ✅ Funcional | Pydantic Settings com Supabase, LLM, cache |
| Router | `router/central.py` | ✅ Funcional | Híbrido: pgvector + domain rules + LLM refine. Diversidade de times nos top-3 |
| Agent Catalog | `agents/catalog.py` | ✅ Funcional | Supabase queries + DOMAIN_AGENT_MAP (23 domínios → 30 agentes) |
| Agent Creator | `agents/creator.py` | ✅ Funcional | Criação de agentes autônomos 24/7 |
| Council | `orchestrator/council.py` | ✅ Funcional | Router → framing → Send[] paralelo → aggregate → memory |
| Group | `orchestrator/group.py` | ✅ Estrutura | LangGraph multi-round debate |
| Ping | `orchestrator/ping.py` | ✅ Estrutura | Briefing diário |
| Base LLM | `orchestrator/_base.py` | 🆕 Novo | Shared httpx DeepSeek call |
| Formatter | `formatter/hierarchical.py` | ✅ Funcional | Jinja2 templates: Council, Group, Ping |
| MCP Server | `mcp_server.py` | ✅ Funcional | 10 tools + 2 resources + 2 prompts via FastMCP |
| Knowledge | `knowledge/retriever.py` | ✅ Estrutura | pgvector RAG |
| Memory | `memory/store.py` | ✅ Estrutura | CRUD Supabase |
| Memory Pipeline | `memory/pipeline.py` | ✅ Funcional | observe → distill → embed → search |
| Rituals | `rituals/runner.py` | ✅ Funcional | 16 protocolos Febrain |
| Channels | `channels/telegram.py` | ✅ Estrutura | Telegram integration |
| Auth | `auth/jwt.py` | ✅ Estrutura | Supabase JWT validation |

### Frontend (`frontend/`) — 11 arquivos React/TSX

| Tela | Arquivo | Estado |
|------|---------|--------|
| Landing | `screens/Landing.tsx` | ✅ Completo |
| Login | `screens/Login.tsx` | ✅ Completo |
| Home | `screens/Home.tsx` | ✅ Completo |
| Conselho | `screens/Conselho.tsx` | ✅ Completo (2 steps, portado do protótipo) |
| Grupo | `screens/Grupo.tsx` | ✅ Completo (portado do protótipo) |
| Criar Agente | `screens/AgentCreate.tsx` | ✅ Completo |
| Ping | `screens/Ping.tsx` | ✅ Completo |

**Deploy atual:** Frontend em https://frontend-fe-produto.vercel.app

---

## 4. O QUE CONSTRUIR (prioridade)

### PRIORIDADE 1 — Produção (Railway deploy)

**Objetivo:** API no ar, conectada ao frontend, respondendo com agentes reais.

- [ ] **Dockerfile + railway.toml** — Deploy da API no Railway
- [ ] **Supabase connection string** — Configurar `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` no .env de produção
- [ ] **DeepSeek API key** — Configurar `DEEPSEEK_API_KEY` no .env de produção
- [ ] **Frontend ↔ API** — Conectar `frontend/src/` aos endpoints reais (substituir mock data)
  - `POST /council` → tela Conselho
  - `POST /group` → tela Grupo
  - `GET /personas` → tela Home (catálogo)
  - `GET /ping` → tela Ping
- [ ] **Health check** — Endpoint `/health` com Supabase + contagem de agentes
- [ ] **CORS** — Restringir origins pra produção (hoje é `*`)

### PRIORIDADE 2 — Agentes Reais

**Objetivo:** Router funcionando com embeddings reais, agentes respondendo com SOULs completos.

- [ ] **pgvector match_personas** — Verificar se a RPC `match_personas` existe no Supabase. Se não, criar migration SQL:
  ```sql
  CREATE OR REPLACE FUNCTION match_personas(query_text text, match_limit int)
  RETURNS TABLE(slug text, handle text, name text, home_team text, similarity float)
  LANGUAGE plpgsql AS $$
  BEGIN
    RETURN QUERY
    SELECT p.slug, p.handle, p.name, p.home_team,
           (1.0 - (p.embedding <=> voyage_embed(query_text)::vector)) AS similarity
    FROM personas p
    WHERE p.embedding IS NOT NULL
    ORDER BY p.embedding <=> voyage_embed(query_text)::vector
    LIMIT match_limit;
  END;
  $$;
  ```
- [ ] **voyage_embed function** — Verificar se existe no Supabase
- [ ] **Agent SOUL loading** — `AgentCatalog.get_prompt()` carrega `persona_md` da tabela `personas`. Verificar se os 150+ agentes têm `persona_md` populado.
- [ ] **Group orchestrator** — Implementar LangGraph multi-round: `init → loop[Send[]] → consensus → synthesize`
- [ ] **Ping orchestrator** — Implementar briefing diário com RAG vertical

### PRIORIDADE 3 — Auth + Onboarding

**Objetivo:** Usuário cria conta, faz onboarding setorial, começa a usar.

- [ ] **Supabase Auth UI** — Login/signup integrado na tela de Login
- [ ] **Onboarding flow** — CEO escolhe setor + cargo → sistema carrega KB vertical + agentes relevantes
- [ ] **RLS policies** — `personas`, `memories`, `conversations` com row-level security por `user_id`
- [ ] **Rate limiting** — Upstash Redis no API Gateway (middleware FastAPI)

### PRIORIDADE 4 — Memória + Recorrência

**Objetivo:** O sistema lembra decisões passadas e evolui com o CEO.

- [ ] **Memory injection** — Antes de cada `/council`, buscar últimas 5 memórias do usuário e injetar no contexto
- [ ] **Memory distill automation** — Após cada sessão, rodar pipeline: observe → distill → embed (já existe, precisa integrar no flow)
- [ ] **Ping diário automático** — pg_cron job que gera briefing e notifica (Telegram/email)

### PRIORIDADE 5 — Billing + GTM

**Objetivo:** Cobrar.

- [ ] **Stripe integration** — Plans: Free (3 consultas/mês), Pro (R$497), Executive (R$997), Enterprise (R$2.497)
- [ ] **Usage tracking** — Contador de consultas por user_id
- [ ] **Paywall** — Bloquear após free tier

---

## 5. O QUE NÃO FAZER

- ❌ **Criar agentes do zero.** Usar os 150+ do FeBrain. Se precisar de novo → adicionar no FeBrain primeiro.
- ❌ **Reconstruir a UI.** O frontend já existe. Conectar, não reconstruir.
- ❌ **Router 100% LLM.** Custo + latência matam. Híbrido: embeddings + regras + LLM só refinamento.
- ❌ **Formatter genérico.** CEOs precisam de estrutura hierárquica (sumário → perspectivas → fontes).
- ❌ **Deploy sem health check.** 1 verificação, sem polling loop.
- ❌ **Agentes exclusivos de uma skin.** Se serve ao Second Brain, serve ao Workforce.
- ❌ **Modelos caros como padrão.** DeepSeek V4 Pro cobre 90%. Claude só divergência/Board Mode.
- ❌ **Lorcana Brasil.** Vertical separada, motor próprio.
- ❌ **Supabase Febrain separado.** Usar a instância existente. Nunca recriar o banco.

---

## 6. ARQUITETURA DE REFERÊNCIA

Fluxo completo de uma requisição `/council`:

```
1. CEO pergunta: "Devo reajustar o pricing enterprise em 6%?"
2. Frontend → POST /council { question, context }
3. API Gateway → valida JWT, rate limit
4. ROUTER
   ├── embed_query("pricing enterprise reajuste 6%")
   ├── pgvector similarity search → personas
   ├── domain rules: "pricing" → @patrick-campbell, @bobby-pinero
   └── return: [patrick-campbell, bobby-pinero, april-dunford]
5. ORCHESTRATOR
   ├── framing → prepara prompt por agente
   ├── Send[] → 3 agentes em paralelo (DeepSeek V4 Pro)
   ├── aggregate → coleta respostas
6. FORMATTER
   ├── Template Jinja2: Summary → Perspectives → Devil's Advocate → Sources
7. API Gateway → JSON response → Frontend renderiza
8. MEMORY (async, fire-and-forget)
   └── Supabase: INSERT observational_memory
```

---

## 7. COMANDOS RÁPIDOS

```bash
# Dev
cd ~/code/workforce-os
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev

# Deploy API (Railway)
railway up

# Deploy Frontend (Vercel)
cd frontend && vercel --prod

# Push para o repo
git add -A && git commit -m "..." && git push upstream main
```

---

## 8. ARQUIVOS DE REFERÊNCIA

| Arquivo | Conteúdo |
|---------|----------|
| `ARCHITECTURE.md` | Arquitetura completa (7 seções, diagrama ASCII) |
| `api/main.py` | API Gateway — comece lendo este |
| `api/config.py` | Config centralizada |
| `api/router/central.py` | Router híbrido |
| `api/agents/catalog.py` | Catálogo + domain map |
| `api/orchestrator/council.py` | Orquestrador Council |
| `api/formatter/hierarchical.py` | Formatador Jinja2 |
| `api/mcp_server.py` | MCP Server |
| `~/code/Febrain/_shared/PLATFORM-ARCHITECTURE.md` | Arquitetura do OS + skins |
| `~/code/Febrain/teams/` | 27 times, 150+ agentes |
| `~/Downloads/secondbrain/screens.jsx` | Protótipo original (5.390 linhas) |

---

*Build prompt gerado em 28 Mai 2026. Comece pela Prioridade 1.*
