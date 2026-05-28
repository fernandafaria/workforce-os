---
type: design-doc
scope: rag/twins
status: proposal
audience: ai-engineering, engineering, product, design
authors: claude-code (synthesis), reviewed-by-pending: @fernanda
last-updated: 2026-05-05
references-verified: 2026-05-05
---

# Febrain Behavioral Simulation Engine (FBSE)

> Extrapolação algorítmica para um motor de simulação de análise comportamental baseado em personas sintéticas com acurácia mensurável. Síntese de 6 papers + arquitetura existente do repo.

---

## TL;DR

A pipeline `rag/twins/` atual responde **uma pergunta isolada como o twin** e mede similaridade cosseno (Layer 1). Para gerar **personas sintéticas que respondem com acurácia em múltiplas dimensões e simulem comportamento contínuo**, faltam 4 capacidades:

1. **Perfil multidimensional** (Big Five + Schwartz + MBTI extraídos do corpus, hoje ausente no `schema.py`)
2. **Cadeia de comportamento** (sequências temporais (contexto→decisão→resultado), não só Q&A pontuais — gap apontado pelo BehaviorChain)
3. **Avaliação multi-dimensional** (separar Opinion / Memory / Logic / Lexical / Tone / Syntactic em vez de uma cosseno só — protocolo do TwinVoice)
4. **Modelo de escolha por preferência** (Graph RAG sobre histórico de decisões, com encoding de preference chain — algoritmo do paper de mobilidade)

O FBSE é a extensão proposta: 7 estágios, dos quais 3 já existem (ingestão, build_twin, chat_with_twin), 4 são novos. Roadmap mapeado para AI Engineering (modelagem), Engineering (infra/Supabase/CI), Product (gating + casos de uso) e Design (UX de avaliação humana).

**Risco-mãe a ser nomeado antes da decisão:** o paper BehaviorChain reporta que **mesmo SOTA falha em simular comportamento humano contínuo com acurácia**. Não devemos prometer "twin fiel" — devemos prometer "twin auditável com score multi-dimensional e gates explícitos por dimensão".

---

## 1. Síntese dos papers

| # | Paper | Contribuição que o FBSE absorve |
|---|---|---|
| 1 | [TwinVoice — A Multi-dimensional Benchmark for Digital Twins via LLM Persona Simulation](https://arxiv.org/pdf/2510.25536) | Taxonomia avaliativa: 3 dimensões de persona (Social / Interpersonal / Narrative) × 6 capacidades (Opinion Consistency, Memory Recall, Logical Reasoning, Lexical Fidelity, Persona Tone, Syntactic Style) × 3 modos de tarefa (Discriminative MCQ / Generative-Ranking / Generative-Scoring). Hosted: [twinvoice.github.io](https://twinvoice.github.io/), código em [github.com/TwinVoice/TwinBench](https://github.com/TwinVoice/TwinBench). |
| 2 | [BehaviorChain — How Far are LLMs from Being Our Digital Twins?](https://aclanthology.org/2025.findings-acl.813.pdf) (Li et al., ACL Findings 2025) | Benchmark de **15.846 comportamentos** distribuídos em **1.001 personas** únicas com history + profile metadata. Tarefa: dado o perfil, **inferir iterativamente o próximo comportamento em cenários dinâmicos**. Resultado declarado no abstract: "even state-of-the-art models struggle with accurately simulating continuous human behavior" — ou seja, validar e gatear, não confiar cego. |
| 3 | [Graph RAG as Human Choice Model — Mobility Agent with Preference Chain](https://arxiv.org/pdf/2508.16172) | Encoding de **preference chain**: sequências temporais (contexto, decisão, resultado) como subgrafo recuperável; LLM gera próxima decisão condicionada ao histórico. Referencia teoria de intenção de Bratman (goals + plans). |
| 4 | [Humanized Agent-based Models: a Framework (h-ABM)](https://www.techrxiv.org/doi/full/10.36227/techrxiv.172349445.53365209/v3) | Framework conceitual para integrar LLMs em Agent-Based Models clássicos — mantém regras macro do ABM (interação multi-agente, ambiente compartilhado) e injeta cognição via LLM por agente. Útil para o passo de simulação multi-twin (não só Q&A 1:1). |

> **Disciplina de referências:** todas as URLs acima foram acessadas via WebFetch nesta sessão. Onde o WebFetch falhou (techrxiv 403), o título e linha-base foram confirmados via WebSearch. Não foram inventados números, autores ou datasets — campo `references-verified` no frontmatter registra a data.

---

## 2. Inventário do que já existe no repo

(Inventário completo via Explore agent; aqui o resumo operacional.)

### Pipeline twins (`rag/twins/`)
- **`schema.py`** — Pydantic discriminated union (`twin_kind: entrepreneur | operator`), com `CompanyContext`, `DecisionFingerprint`, `LinguisticFingerprint`. **Não tem** Big Five / Schwartz / MBTI nem behavior chain.
- **`discover_sources.py`** + **`url_finder.py`** + **`transcribe.py`** — ingestão de corpus (entrevistas, artigos, podcasts, LinkedIn).
- **`build_twin.py`** — Claude extrai Twin estruturado do corpus, dispatch por `twin_kind`, temperatura 0.1 (factual) / 0.5 (linguístico).
- **`corpus_search.py`** — retrieval semântico (cosseno sobre Voyage embeddings).
- **`chat_with_twin.py`** — geração: system prompt do twin + tool `corpus_search` + Claude (T=0.3); decline gracioso ("não costumo falar sobre isso").
- **`eval_twin.py`** — Layer 1: synthesize question → ask twin → cosseno vs. quote held-out; gate p70 ≥ 0.75 (público) ou 0.72 (arquétipo). **Layers 2 (estilometria) e 3 (LLM-as-judge) marcadas como TODO.**
- **`benchmark/`** (1593 LOC) — `runner.py`, `schema.py`, `metrics.py` (chi-quadrado, KL), `storage.py` — twin-vs-human distribuições.

### Personas (Tier 1)
- **`_shared/templates/AGENT-PROFILE.md`** — frontmatter YAML (slug, role, domains, sources, autonomous, tags) + seções prosa (Identity, Core Philosophy, How You Think, How You Communicate, When to Invoke). Sem campo de personality framework.
- **208 personas** em 25 diretórios (13 times canônicos).

### Supabase
- **`personas`** (vector(1024) embedding via Voyage), **`memories`** unified (`memory_type`, `scope`), **`agent_triggers`** + **`agent_runs`** (logs com `tokens_used`, `cost_usd`).
- **Sem tabelas** de Q&A pairs, behavior traces ou preference chains.

### Avaliação existente
- `rag/twins/eval_twin.py` (Layer 1 cosseno), `rag/twins/benchmark/runner.py` (twin-vs-human), `rag/agent_eval.py` (goldens YAML), `rag/eval_judge.py` (deterministic + LLM rubric).

---

## 3. Análise de gap (alvo: persona sintética com acurácia)

| Capacidade alvo | Estado atual | Gap |
|---|---|---|
| Perfil multidimensional (Big Five + Schwartz + MBTI) | ❌ Ausente em `schema.py` | Adicionar `PersonalityProfile` ao discriminated union; extração via LLM com calibração inter-rater. |
| Cadeia de comportamento temporal | ❌ Apenas corpora textuais | Tabela `behavior_chains` no Supabase + extrator que destila eventos do corpus em (timestamp, contexto, decisão, resultado). |
| Encoding de preferência (Graph RAG) | ⚠️ Parcial — RAG vetorial, sem grafo | Ver `_meta/RAG-GRAPHRAG-EVALUATION.md` (já avalia FalkorDB/AGE/LlamaIndex); decidir e implementar. |
| Avaliação multi-dimensional (6 capacidades × 3 dimensões) | ⚠️ Apenas Layer 1 cosseno + benchmark distributions | Implementar Layers 2 (estilometria) e 3 (LLM-as-judge) já scaffolded; adicionar dimensões TwinVoice. |
| Simulação contínua (next-N comportamentos) | ❌ Apenas turn-based Q&A | Loop iterativo `predict_next_behavior(persona, history, scenario)` inspirado no BehaviorChain. |
| Multi-agente (h-ABM) | ❌ Twins respondem isolados | Ambiente compartilhado de simulação onde N twins interagem (escopo Fase 3, opcional). |

---

## 4. Algoritmo proposto: FBSE em 7 estágios

```
┌──────────────────────────────────────────────────────────────────────┐
│                         FBSE PIPELINE                                │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [1] Source Ingestion ─────► [2] Persona Structuring                 │
│      (rag/twins/                  + Personality Profile               │
│       discover_sources,           (NEW: Big Five, Schwartz)          │
│       transcribe)                                                    │
│           │                              │                           │
│           ▼                              ▼                           │
│  [3] Behavior Chain Extraction ──► [4] Knowledge Graph + Preference  │
│      (NEW: events from corpus)        Chain Encoding                 │
│      → (t, context, decision,         (NEW: subgraph retrieval)      │
│         outcome) tuples                                              │
│                                          │                           │
│                                          ▼                           │
│  [5] Response Generation Engine                                      │
│      ├─ Mode A: Discriminative (MCQ from TwinVoice schema)          │
│      ├─ Mode B: Generative open (existing chat_with_twin)            │
│      └─ Mode C: Behavior-chain prediction (NEW, BehaviorChain-style) │
│                                          │                           │
│                                          ▼                           │
│  [6] Multi-dimensional Evaluator (NEW)                               │
│      ├─ Dimension × Capability matrix (3 × 6 = 18 cells)            │
│      ├─ Layer 1: cosseno (existente, expandido por capacidade)      │
│      ├─ Layer 2: stylometry (n-gram + perplexity ratio)             │
│      └─ Layer 3: LLM-as-judge pairwise (Claude Opus rubric)         │
│                                          │                           │
│                                          ▼                           │
│  [7] Gating + Production Decision                                    │
│      ├─ Per-dimension gate (não um número agregado só)              │
│      ├─ Auditoria humana onde falhou                                 │
│      └─ Status: shadow | beta | production                          │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Estágio 1 — Source Ingestion (existente)

**Já implementado.** Sem mudança. Inputs: spec YAML em `rag/twins/persons/<slug>.yaml` com `sources[]` validados (regra-mãe ZERO dados inventados). Output: corpus markdown em `_corpus/<slug>/`.

### Estágio 2 — Persona Structuring com Personality Profile (extensão)

**Modificar `rag/twins/schema.py`:** adicionar ao discriminated union um campo opcional `personality: PersonalityProfile | None`.

```python
class PersonalityProfile(BaseModel):
    """Multi-framework profile extracted from corpus. All scores 0-1, with
    confidence per dimension (sparse signal in 1st-person interviews is
    a known limitation — see Risk #2)."""

    big_five: dict[str, float]       # openness, conscientiousness, extraversion, agreeableness, neuroticism
    big_five_confidence: dict[str, float]
    schwartz_values: dict[str, float]  # 10 motivational types
    mbti_indicators: dict[str, float] | None  # E/I, S/N, T/F, J/P (if extractable)
    extraction_evidence: list[str]   # quoted snippets justifying scores (auditability)
    extracted_by: str                # "claude-opus-4-7" | "human-rated"
    extracted_at: date
```

**Implementação:** novo módulo `rag/twins/extract_personality.py`. Prompt do LLM: para cada dimensão, citar evidência do corpus (snippets) antes de pontuar — força grounding e reduz hallucination de score. Calibração: rodar em 10 personas com auto-relato conhecido (ex: founders que publicaram MBTI ou Big Five) e medir correlação.

> **Por que múltiplas frameworks em vez de só uma?** TwinVoice mistura referências a Big Five **e** Schwartz **e** MBTI. Cada uma tem cobertura diferente: Big Five captura traços, Schwartz captura motivações/valores, MBTI captura preferências cognitivas. Manter os três permite triangulação e debug — se o twin falha em "Opinion Consistency", podemos ver qual framework explicaria melhor.

### Estágio 3 — Behavior Chain Extraction (novo)

**Justificativa:** BehaviorChain mostra que o gap crítico hoje é simulação contínua. Corpus textual sozinho não dá (timestamp, contexto, decisão, resultado) explícitos.

**Schema:**

```python
class BehaviorEvent(BaseModel):
    timestamp: date | str            # ISO date ou descritor relativo ("durante a Série A")
    context: str                     # situação que ativou a decisão
    decision: str                    # o que a pessoa fez
    decision_type: Literal["product", "hiring", "fundraising", "operational", "personal", "communication"]
    outcome: str | None              # resultado observável (se relatado)
    source_ref: str                  # path para chunk do corpus que originou (auditabilidade)
    confidence: float                # quão explícito vs inferido
```

**Migração Supabase:** `behavior_chains` (persona_id, events JSONB[], extracted_at, version) — log + idempotência por hash.

**Extração:** LLM faz pass sobre `_corpus/<slug>/` com prompt: "extraia eventos no formato (timestamp, contexto, decisão, resultado) somente quando explícitos no texto; marque inferidos com confidence < 0.6". Eventos são depois validados por humano em batch (skill `distill-memory` já existe e serve).

### Estágio 4 — Knowledge Graph + Preference Chain (novo)

**Adoção dependente de** `_meta/RAG-GRAPHRAG-EVALUATION.md` — esse documento já avalia FalkorDB / Apache AGE / LlamaIndex. Decisão recomendada: **Apache AGE** (mesma instância Postgres do Supabase, sem operador novo).

**Nós:** `Persona`, `Context`, `Decision`, `Outcome`, `Value` (Schwartz), `Trait` (Big Five), `BehaviorEvent`.

**Arestas:**
- `(BehaviorEvent)-[:FOLLOWS]->(BehaviorEvent)` — ordem temporal
- `(Context)-[:LED_TO]->(Decision)` — causa
- `(Decision)-[:CAUSED]->(Outcome)`
- `(Persona)-[:HOLDS]->(Value)` com peso
- `(Decision)-[:EXPRESSES]->(Value)` — alinhamento decisão↔valor

**Preference Chain (algoritmo do paper de mobilidade adaptado):**

```
input:  current_context C, persona P, lookback K
1. retrieve last K BehaviorEvents of P via graph traversal, ordered temporal
2. for each event, fetch (Context, Decision, Outcome, Values_expressed)
3. concatenate as ordered chain: [(c1,d1,o1,v1), ..., (ck,dk,ok,vk)]
4. inject into LLM prompt as "preference history"
5. LLM predicts next decision conditioned on chain + new context C
output: predicted_decision, expressed_values, confidence
```

A diferença vs. corpus_search (vetorial puro) é que **a ordem importa** e **o grafo permite filtrar por tipo de decisão**, valor expresso, ou contexto similar.

### Estágio 5 — Response Generation Engine (extensão)

**Três modos correspondentes a TwinVoice:**

- **Modo A — Discriminative (MCQ):** input = pergunta + 4 opções; output = letra escolhida + justificativa. Útil para gates rápidos e baratos. Usa retrieval simples (corpus_search top-k).
- **Modo B — Generative-Open:** existente em `chat_with_twin.py`. Mantém T=0.3, decline gracioso, ferramenta corpus_search. Adicionar: hook de preference chain quando `decision_type` for inferível da pergunta.
- **Modo C — Behavior Chain Prediction:** input = persona + history + scenario; output = sequência de N comportamentos preditos. Loop iterativo (BehaviorChain-style):

```
for step in 1..N:
    history += latest_predicted_event
    next_event = LLM(persona_profile, personality, history, scenario_at_step)
    if confidence(next_event) < threshold: break
yield history
```

### Estágio 6 — Multi-dimensional Evaluator (novo, expansão)

**Matriz 3 × 6 = 18 células avaliativas** (TwinVoice):

|                | Opinion Consistency | Memory Recall | Logical Reasoning | Lexical Fidelity | Persona Tone | Syntactic Style |
|---|---|---|---|---|---|---|
| **Social**         | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Interpersonal**  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Narrative**      | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

**Layers (alinhados ao `eval_twin.py` existente):**

| Layer | Métrica | Aplicabilidade | Custo |
|---|---|---|---|
| L1 (existente) | Cosseno Voyage | Opinion, Memory | barato |
| L2 (TODO no repo) | Stylometry — n-gram overlap, type-token ratio, sentence-length distribution, perplexity ratio do twin vs corpus | Lexical Fidelity, Syntactic Style | médio |
| L3 (TODO) | LLM-as-judge pairwise (Claude Opus rubric) — compara resposta do twin vs. quote real held-out | Tone, Logic, Memory | caro (orçar) |

**Output:** vetor de 18 scores + 3 agregações por dimensão + 1 agregação geral. **Nunca** colapsar para 1 número antes do gate — o agregado esconde falhas direcionais (twin pode acertar em Social mas falhar em Narrative; tratar separado).

**Tarefas (TwinVoice):**
- **Discriminative:** acurácia em MCQ (top-1 e top-2).
- **Generative-Ranking:** N respostas → judge ranqueia → MRR.
- **Generative-Scoring:** rubric 1-5 em (opinion, logic, style) similarity.

### Estágio 7 — Gating + Production Decision

**Estados:**
- `shadow` — twin existe, responde em sandbox, não exposto a usuário
- `beta` — exposto a usuários internos com banner ("twin sintético, em validação")
- `production` — exposto externamente

**Promoção entre estados requer gates POR DIMENSÃO** (não agregado):

| Estado → | Gate por dimensão | Auditoria humana |
|---|---|---|
| shadow → beta | L1 p70 ≥ 0.72 (arquétipo) ou 0.75 (público) **em todas as 3 dimensões** | 5 amostras revisadas por persona |
| beta → production | L2 + L3 com score ≥ 4/5 em **Tone** e **Opinion** específico | 20 amostras revisadas + decision-log entry |

**Por que gates separados?** Porque o twin de **Rita McGrath**, por exemplo, pode ser ótimo em Social (LinkedIn-style) mas fraco em Narrative (role-play em cenários hipotéticos). Bloquear a Narrative sem matar o Social é a granularidade certa.

---

## 5. Mapeamento de ownership pelos times autorizados

> O usuário autorizou explicitamente: **engineering, ai-engineering, product, design**. Atribuição abaixo conforme atribuições típicas dos times no repo.

### AI Engineering team (`teams/ai-engineering/`)

**Owner principal das partes de modelagem.**

| Estágio | Entregável | Persona owner provável |
|---|---|---|
| 2 | `rag/twins/extract_personality.py` + adição ao `schema.py` | @hamel (eval mindset) |
| 3 | `rag/twins/extract_behavior_chain.py` | @swyx (latent space, embedding-aware) |
| 4 | Decisão Graph DB + adapter `rag/twins/preference_chain.py` | (alinhar com `_meta/RAG-GRAPHRAG-EVALUATION.md`) |
| 6 | Layer 2 stylometry + Layer 3 LLM-as-judge | @hamel + @eugene-yan |
| 7 | Calibração de gates (qual threshold por dimensão) | AI Eng team coletivo, war-room |

### Engineering team (`teams/main/` ou tech-leadership)

**Owner principal de infra, schema, CI/CD.**

| Estágio | Entregável |
|---|---|
| 3 | Migração Supabase: tabela `behavior_chains` (event log + RLS) |
| 4 | Setup Apache AGE (extensão Postgres no projeto Supabase) |
| 6 | Pipeline CI: rodar L1+L2+L3 em PR de novo twin spec → publicar score na PR comment |
| 7 | API `GET /twins/<slug>/eval` no `rag/server.py` (MCP tool) — expõe matriz 3×6 + history |

### Product team (`teams/product-discovery/` + main)

**Owner principal de roadmap, casos de uso, gating policy.**

| Decisão | Pergunta a responder |
|---|---|
| Qual a primeira persona alvo da Fase 1? | Recomendado: arquétipo (sem questão de privacidade) — usar `bauducco-scaramussa` que já tem corpus, ou um arquétipo brasileiro do `BRAZILIAN_ARCHETYPES.md` |
| Qual capacidade priorizar? | Tradeoff: Memory Recall (mais útil pra discovery) vs. Persona Tone (mais útil pra co-creation) |
| Quando promover de beta → production? | Definir SLA: 95% das amostras passam em rubric ≥ 4/5? Aceitar 90%? |
| Política de consentimento | `authorization: public_figure | archetype_synthetic` já existe. Para `synthetic_real_person` (não público) precisamos de processo de consent — Product define |

### Design team (`teams/design-ux/`)

**Owner principal de UX para humans-in-the-loop.**

| Entregável | Justificativa |
|---|---|
| UI de revisão humana em `webapp/` (revisor vê resposta do twin + quote real + score 1-5 por dimensão) | Layer 3 LLM-as-judge precisa de calibração com humano periodicamente |
| Banner / disclosure quando twin é sintético | Compliance + transparência (paper "Whose Personae?" arxiv 2512.00461 alerta para riscos de transparência) |
| Dashboard de matriz 3×6 por twin | Stakeholders precisam ver onde o twin é forte/fraco antes de invocar |
| Fluxo de "ask the twin" com gate visual | Se twin está shadow, UI não permite uso externo; se beta, mostra disclosure |

---

## 6. Estrutura de arquivos proposta

```
rag/twins/
├── BEHAVIORAL-SIMULATION-ENGINE.md   ← este doc
├── schema.py                          ← extender com PersonalityProfile, BehaviorEvent
├── extract_personality.py             ← NOVO (Estágio 2)
├── extract_behavior_chain.py          ← NOVO (Estágio 3)
├── preference_chain.py                ← NOVO (Estágio 4)
├── eval_twin.py                       ← extender Layers 2 e 3
├── eval_multidim.py                   ← NOVO (matriz 3×6 do TwinVoice)
├── benchmark/
│   ├── (existente)
│   └── twinvoice_tasks.py             ← NOVO (3 modos: Discriminative/Gen-Rank/Gen-Score)
└── persons/
    └── <slug>.yaml                    ← schema permanece; novos campos lidos por extract_*

product/supabase/migrations/
└── NNN_behavior_chains.sql            ← NOVO

webapp/src/app/twins/
└── (rotas de revisão humana, dashboard 3×6, disclosure)
```

---

## 7. Roadmap em fases

### Fase 0 — Decisão (1 semana, antes de qualquer código)

- [ ] Product define **persona-piloto** e **caso de uso primário** (discovery? co-creation? VOC sintético?)
- [ ] AI Engineering valida **Apache AGE vs alternativas** lendo `_meta/RAG-GRAPHRAG-EVALUATION.md`
- [ ] Design produz **wireframes** das 3 telas (revisão humana, dashboard 3×6, disclosure)
- [ ] War-room cross-team aprova ou ajusta este doc

### Fase 1 — MVP single-persona (2-3 semanas)

- [ ] Estágio 2: `PersonalityProfile` + extrator + calibração com 5 personas
- [ ] Estágio 3: `BehaviorEvent` + extrator + tabela Supabase
- [ ] Estágio 6: Layer 2 stylometry implementado + Layer 3 LLM-as-judge implementado
- [ ] Avaliar matriz 3×6 em **1 persona** (a piloto da Fase 0)
- [ ] Critério de saída da fase: matriz 3×6 publicada com scores; pelo menos 1 dimensão com gate L1 atendido

### Fase 2 — Preference Chain + Multi-modo (3-4 semanas)

- [ ] Estágio 4: Apache AGE setup + `preference_chain.py`
- [ ] Estágio 5: Modo A (Discriminative) + Modo C (Behavior Chain Prediction)
- [ ] Eval da matriz 3×6 em 5 personas
- [ ] Critério de saída: ≥ 3 personas com promoção shadow → beta

### Fase 3 — Multi-agente h-ABM (opcional, 4-6 semanas)

- [ ] Ambiente compartilhado de simulação (N twins interagem)
- [ ] Métrica de emergência: comportamento coletivo vs. dado real (se houver)
- [ ] **Decisão de Product:** isso é um produto vendável ou ferramenta interna de stress-test?

---

## 8. Riscos e questões abertas

### R1 — Acurácia limitada por construção (BehaviorChain)
O paper diz que SOTA falha em comportamento contínuo. **Mitigação:** não vender "twin fiel"; vender **"twin auditável com matriz 3×6"** e usar gates por dimensão. Comunicar a priori que *Narrative* é mais difícil que *Social*.

### R2 — Sinal esparso para Big Five em entrevistas 1ª pessoa
Big Five robusto vem de questionário (NEO-PI-R, BFI-44). Extrair de corpus tem viés (entrevistas tendem a inflar Extraversion e Conscientiousness). **Mitigação:** confidence por dimensão; calibração com 10 personas que tenham score auto-relatado público; considerar dimensões de Schwartz como prioridade (mais expressas verbalmente).

### R3 — Custo de Layer 3 (LLM-as-judge)
Avaliar matriz 3×6 com Claude Opus em 20 amostras × 6 capacidades × 3 dimensões = 360 chamadas/twin. **Mitigação:** pipeline `eval_judge.py` já tem hybrid deterministic-first; rodar L3 só onde L1+L2 dão sinal ambíguo. Orçar custo por persona antes de aprovar promoção.

### R4 — Privacidade / consentimento
`authorization: public_figure | archetype_synthetic` cobre os casos atuais. **Lacuna:** se a Febrain quiser modelar pessoas privadas (ex: cliente da consultoria), falta processo de consent. **Owner:** Product team.

### R5 — Drift do corpus ao longo do tempo
Pessoa pública evolui (Rita McGrath em 2018 ≠ 2026). **Mitigação:** versionar corpus por janela temporal; behavior chain já tem `timestamp`. Reportar "twin de Rita McGrath circa 2024" é mais honesto que "twin de Rita McGrath" sem qualificação.

### R6 — Apache AGE em produção
Adiciona complexidade operacional vs. ficar em Postgres relacional puro. **Alternativa:** se grafo provar overhead alto na Fase 2, fallback é simular preference chain via JSONB array temporal em `behavior_chains` (perde queries graph mas mantém o algoritmo).

### Q1 — A Febrain quer ser benchmark contributor?
TwinVoice expõe leaderboard público. Se rodarmos os personas do repo no benchmark deles e publicarmos, é contribuição científica + marketing. Decisão de Product.

### Q2 — Modo de uso primário: simular ou consultar?
- **Simular** = "o que faria a Rita?" (geração de cenários) — usa Modo C
- **Consultar** = "o que disse a Rita sobre X?" (recuperação faithful) — usa Modo B
A diferença muda o gate (Modo C tolera mais variação criativa). Product decide qual prioriza.

---

## 9. Conexão com regras-mãe da Febrain

| Regra-mãe (CLAUDE.md) | Como o FBSE adere |
|---|---|
| **ZERO dados inventados** | Todo `BehaviorEvent` carrega `source_ref` para chunk do corpus; toda evidência de `PersonalityProfile` é quoted snippet auditável. |
| **Inventariar ferramentas antes de buscar** | Estágio 1 reusa `discover_sources.py` + Firecrawl + transcribe; não cria nova pipeline de ingestão. |
| **Parceiro crítico, não bajulador** | Doc nomeia explicitamente que SOTA falha (Risco R1); não promete "twin fiel"; força gates por dimensão em vez de número agregado. |
| **YouTube via DO runner** | Estágio 1 mantém esse fluxo (já existe). |
| **REPO-MAP atualizado** | Este doc adicionado à seção "RAG modules" do `_meta/REPO-MAP.md` no mesmo PR. |

---

## 10. Próximo passo solicitado

Antes de qualquer linha de código, **war-room de 30min** com 1 representante de cada time autorizado:
- AI Engineering — valida modelo de personality + Graph DB
- Engineering — confirma viabilidade Supabase + AGE + CI
- Product — escolhe persona-piloto + caso de uso
- Design — confirma escopo das 3 telas

**Output do war-room:** decisão go/no-go para Fase 1 + persona piloto definida + critério de saída específico.

---

## Referências (verificadas em 2026-05-05)

1. Tang, Z. et al. (2025). *TwinVoice: A Multi-dimensional Benchmark towards Digital Twins via LLM Persona Simulation.* [arxiv.org/abs/2510.25536](https://arxiv.org/pdf/2510.25536) · [twinvoice.github.io](https://twinvoice.github.io/) · [github.com/TwinVoice/TwinBench](https://github.com/TwinVoice/TwinBench)
2. Li, R. et al. (2025). *How Far are LLMs from Being Our Digital Twins? A Benchmark for Persona-Based Behavior Chain Simulation.* ACL Findings 2025. [aclanthology.org/2025.findings-acl.813](https://aclanthology.org/2025.findings-acl.813/)
3. Anonymous (2025). *Graph RAG as Human Choice Model: Building a Data-Driven Mobility Agent with Preference Chain.* [arxiv.org/abs/2508.16172](https://arxiv.org/pdf/2508.16172)
4. *Humanized Agent-based Models: a Framework.* TechRxiv. [doi.org/10.36227/techrxiv.172349445.53365209](https://www.techrxiv.org/doi/full/10.36227/techrxiv.172349445.53365209/v3) (autores não confirmados nesta sessão — WebFetch retornou 403; título via WebSearch)
5. Repo Febrain: `_meta/RAG-GRAPHRAG-EVALUATION.md` (avaliação interna FalkorDB / AGE / LlamaIndex)
6. Repo Febrain: `rag/twins/eval_twin.py` (Layer 1 cosseno, Hamel war-room 2026)
