# Workforce OS — Próximas Fases (Task Breakdown)

**Data:** 2026-05-27
**Status:** Planejado

---

## Fase 1 — Deploy + Conectar ao Real (1-2 dias)

| # | Task | O que fazer | Dependência |
|---|------|------------|-------------|
| 1.1 | **Railway deploy** | `railway up` com Dockerfile. Configurar env vars (SUPABASE_URL, DEEPSEEK_API_KEY, ANTHROPIC_API_KEY) | Auth Railway |
| 1.2 | **Vercel deploy** | `vercel --prod` no frontend/. Configurar VITE_API_URL apontando pra Railway | Deploy Railway |
| 1.3 | **Conectar AgentCreate ao Supabase** | POST /agents/create → INSERT real na tabela agent_triggers (não mock) | Supabase schema |
| 1.4 | **Conectar Conselho/Grupo ao LangGraph real** | Trocar chamadas mock por LangGraph graphs com agentes Febrain | MCP Server rodando |
| 1.5 | **Health check** | GET /health confirmando: Supabase OK, 150 agentes, 7 verticais | Tudo acima |

## Fase 2 — Rituais & Protocolos (3-4 dias)

| # | Task | O que fazer | Reuso Febrain |
|---|------|------------|---------------|
| 2.1 | **RitualRunner** | `api/rituals/runner.py` — carrega SKILL.md, constrói LangGraph graph, executa | `_shared/protocols/*/SKILL.md` |
| 2.2 | **War Room → Grupo** | Modo Grupo vira protocolo war-room (Parallel Fan-Out + Devil's Advocate) | `protocols/war-room/` |
| 2.3 | **Sparring → Conselho c/ divergência** | Modo Conselho com opção "ativar sparring" (2 agents discordam, CEO decide) | `protocols/sparring/` |
| 2.4 | **Board Review** | Novo modo: Board Review — CEO apresenta, board critica, output refinado | `protocols/board-review/` |
| 2.5 | **Pre-Mortem** | Novo modo: "O que pode dar errado?" — análise pessimista paralela | `protocols/pre-mortem/` |
| 2.6 | **Deal Review** | Novo modo: Análise de oportunidade → Go/No-Go | `protocols/deal-review/` |
| 2.7 | **Rituais agendados** | `/rituals` endpoint: listar, agendar, executar rituais com pg_cron | `protocols/rituals/` + `pg_cron` |

## Fase 3 — Entrega em Canais (2-3 dias)

| # | Task | O que fazer | Reuso Febrain |
|---|------|------------|---------------|
| 3.1 | **Telegram webhook** | Receber msg do usuário → Router → LangGraph → responder no Telegram | `company_channels` |
| 3.2 | **WhatsApp via Telegram** | Mesmo fluxo, bridge Telegram→WhatsApp | `company_channels` |
| 3.3 | **Notificações push** | Web push quando agente 24/7 tem update novo | — |
| 3.4 | **Email digest** | Resumo semanal por email (Conselhos da semana + decisões) | — |

## Fase 4 — Memória & Personalização (2-3 dias)

| # | Task | O que fazer | Reuso Febrain |
|---|------|------------|---------------|
| 4.1 | **Memory pipeline** | Pós-sessão: Observer extrai decisões → Supabase observational_memory | `rag/distill_memory.py` |
| 4.2 | **Contexto cross-session** | Agentes leem memórias anteriores do usuário antes de responder | `rag/conversation_memory.py` |
| 4.3 | **Perfil do executivo** | Extrair padrões: setor, estilo de decisão, vieses | `rag/user_conversation_context.py` |
| 4.4 | **Onboarding setorial** | Primeiro uso: escolher setor → carregar vertical KB → sugerir agentes | `_shared/knowledge/verticais/` |

## Fase 5 — Lançamento Alpha (3-4 dias)

| # | Task | O que fazer |
|---|------|------------|
| 5.1 | **Landing page** | Página pública: o que é, como funciona, pricing (R$497-2.497) |
| 5.2 | **Free tier** | 3 consultas grátis/mês → paywall |
| 5.3 | **Auth** | Supabase Auth: login/signup com email ou Google |
| 5.4 | **Analytics** | PostHog: funil (visit → signup → first council → pay) |
| 5.5 | **Feedback loop** | NPS pós-sessão, "essa recomendação foi útil?" |
| 5.6 | **20 design partners** | Convidar 20 executivos, onboarding manual (Theo), coletar feedback |

---

## Ordem de execução

```
Fase 1 (Deploy) ──────────────────────────► 1-2 dias
  │
  ├── Fase 2 (Rituais) ────────────────────► 3-4 dias  
  │     │
  │     └── Fase 3 (Canais) ───────────────► 2-3 dias
  │           │
  │           └── Fase 4 (Memória) ─────────► 2-3 dias
  │                 │
  │                 └── Fase 5 (Alpha) ──────► 3-4 dias
  │
  TOTAL: ~12-16 dias
```

## O que NÃO está no plano (V2+)

- Workforce (B2B) — Squad Builder, multi-user, dashboard
- Mobile nativo (React Native)
- White label
- Integrações enterprise (Slack, Jira, Teams)
- Fine-tuning com feedback real
