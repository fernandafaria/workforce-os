# Febrain — Protocolos, Rituais e Pipelines → Workforce OS

## 1. PROTOCOLOS (Skills Cross-Team)

16 protocolos de interação multi-agente. **Cada um é um padrão LangGraph.**

| Protocolo | Padrão | Agentes | Uso no Second Brain |
|-----------|--------|---------|---------------------|
| **war-room** | Parallel Fan-Out/Gather + Generator-Critic | 5+ | **Grupo mode** — debate estruturado com Devil's Advocate |
| **sparring** | Thesis → Antithesis → Synthesis (Hegelian) | 2+1 arbitro | **Conselho com divergência** — dois agentes discordam, CEO decide |
| **board-review** | Exec produces → Board reviews → Revised | 1+2-4 | **Board Mode** — CEO apresenta, board critica, output refinado |
| **pre-mortem** | Parallel pessimistic analysis → Risk map | 3-5 | **Análise de risco** — "O que pode dar errado?" |
| **deal-review** | Multi-agent assessment → Go/No-Go | 3-5 | **Decisão de investimento** — M&A, parceria, contratação |
| **deep-dive** | Single-agent solo analysis | 1 | **Ping aprofundado** — um especialista faz homework |
| **retro** | Parallel reflection → Improvement backlog | 3-5 | **Pós-projeto** — o que funcionou, o que não |
| **standup** | Parallel fan-out, no debate | 3-7 | **Briefing rápido** — status telegráfico |
| **qbr** | Full parallel → Synthesis → Priorities | 5+ | **Revisão trimestral** — cada área reporta |
| **one-on-one** | 1v1 conversation | 1+1 | **Mentoring session** |
| **pair-consulting** | Two specialists collaborate | 2 | **Consultoria dupla** |
| **second-opinion** | Independent review | 1 | **Validação externa** |
| **red-team** | Adversarial challenge | 2-3 | **Teste de stress** — "Por que isso vai falhar?" |
| **launch-readiness** | Multi-function go/no-go | 5+ | **Pré-lançamento** |
| **hiring-panel** | Multi-interviewer assessment | 3 | **Contratação** |
| **onboarding-brief** | Context injection | 1 | **Briefing de contexto** |

---

## 2. RITUAIS (Cadência Automatizada)

```
/rituals due              → mostra o que está devido agora
/rituals list             → agenda completa
/rituals run <nome>       → executa ritual (invoca protocolo)
/rituals add <ritual>     → agenda novo ritual
/rituals snooze <nome>    → adia
/rituals skip <nome>      → pula
```

**Isso é o Ping "Briefing Diário" do Second Brain, mas generalizado:**
- Todo dia 7h → `/rituals run standup` → briefing do setor
- Toda segunda → board-review com os mesmos 3 advisors
- Toda sexta → retro da semana
- Fim do trimestre → QBR automático

---

## 3. PIPELINES (Workflows End-to-End)

20 pipelines com múltiplos estágios:

| Pipeline | Estágios | Aplicação |
|----------|---------|-----------|
| **product-discovery** | 7 stages (market→interviews→ideation→prototype→convergence→build→learning) | Desenvolvimento de produto |
| **go-to-market** | Estratégia de entrada | Lançamento |
| **growth-engine** | Growth loops | Escala |
| **content-marketing** | Produção de conteúdo | Marketing |
| **board-review** | Board meeting prep | Governança |
| **deep-dive** | Análise setorial | Pesquisa |
| **deal-review** | Due diligence | M&A/Investimento |

**O Product Discovery Pipeline tem 7 stages com subagentes, schemas YAML, e validação.**

---

## 4. MAPEAMENTO → WORKFORCE OS

### O que o Second Brain (skin) expõe pro usuário:

```
Second Brain UI
│
├── PING (Briefing)
│   └── Por trás: /rituals run standup → agentes Febrain
│
├── CONSELHO (1:1)
│   └── Por trás: protocolos: deep-dive, sparring, second-opinion
│
├── GRUPO (Debate)
│   └── Por trás: protocolos: war-room, pre-mortem, deal-review
│
├── BOARD MODE
│   └── Por trás: protocolo: board-review + pipeline: board-review
│
└── RITUAIS (Agendados)
    └── Por trás: skill: rituals + pg_cron scheduling
```

### O que o Workforce OS (motor) precisa implementar:

```python
# api/rituals/runner.py
class RitualRunner:
    """Wrappa os 16 protocolos Febrain como endpoints LangGraph."""
    
    async def execute(ritual_type: str, context: dict) -> dict:
        # 1. Carrega SKILL.md do protocolo
        # 2. Constrói LangGraph graph baseado no pattern
        # 3. Seleciona agentes via Router
        # 4. Executa e formata
```

**Isso reduz o Workforce OS a um wrapper de ~500 linhas** que traduz "protocolo Febrain" → "endpoint FastAPI".

---

## 5. O que NÃO está no Febrain (e o Workforce OS constrói)

| Gap | Solução |
|-----|---------|
| Protocolos são markdown, não executáveis | LangGraph graphs gerados a partir do SKILL.md |
| Sem API HTTP pública | FastAPI Gateway |
| Sem streaming SSE | LangGraph + SSE |
| Router não usa domain rules | CentralRouter (híbrido) |
| Formatter não tem templates de board | Jinja2 templates |
