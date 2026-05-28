# `rag/twins/shared/` — corpus compartilhado de contexto situacional

Esta pasta contém **corpus de referência** consultado durante entrevistas com arquétipos populacionais, **não** specs de twins.

## Diferença vs. `rag/twins/persons/`

| | `persons/` | `shared/` |
|---|---|---|
| **O que é** | Twin individual (pessoa real ou arquétipo) | Pano de fundo factual sobre o Brasil-real |
| **Quem consulta** | O próprio twin via `corpus_search` (vivência) | Interviewer + archetype como contexto situacional |
| **Tipo de afirmação** | "Eu vivi isso" / "comigo é assim" | "No Brasil de 2026, X% das pessoas..." |
| **Regra LGPD** | Composto ou autorizado | Pesquisa pública agregada |

## Arquivos

- `pop-brasileira-2026.yaml` — catálogo de URLs (entrevistas com institutos de pesquisa: Quaest, AtlasIntel, Datafolha, Ipsos-Ipec, IPEA, FGV IBRE, IBGE, Cedeplar, Locomotiva). Janela: ~out/2025 a abr/2026, com algumas exceções clássicas marcadas no spec. Filename stem == YAML `id`, conforme convenção em `persons/`.
- `populacao-brasileira-2026-briefing.md` — síntese 1-2 páginas dos achados-chave, injetada no system prompt de `interview_archetype.py`.

## Pipeline

```
pop-brasileira-2026.yaml                (URLs verificadas via WebSearch)
        │
        ▼
DO runner + Webshare proxy              (captions YouTube + Firecrawl artigos)
        │
        ▼
SQLite chunks + embeddings              (mesmo schema de persons/)
        │
        ▼
Briefing sintetizado via Opus           (markdown digest)
        │
        ▼
interview_archetype.py prompts          (injeção como contexto situacional)
```

## Indexação via dispatch (file trigger)

O workflow `twins-run.yml` aceita o campo opcional `persons_dir:` no dispatch — basta apontar pra `rag/twins/shared` pra que `run_all.py` descubra specs aqui.

```yaml
# rag/twins/.dispatch/YYYY-MM-DD-NNN-pop-brasileira-2026-dryrun.yml
slug: pop-brasileira-2026
persons_dir: rag/twins/shared
mode: dry-run
```

Pra rodar localmente sem GH Actions (validação de URLs, sem custo):

```bash
python3 -m rag.twins.run_all \
  --persons-dir rag/twins/shared \
  --only pop-brasileira-2026 \
  --dry-run
```

Full mode (custo Whisper/Anthropic/Voyage) só quando briefing precisar de drill-down de chunks — hoje o briefing manual cobre o caso de uso.

## Briefing — fluxo atual vs. futuro

**Hoje:** o briefing (`populacao-brasileira-2026-briefing.md`) é sintetizado **à mão** a partir de WebSearches verificadas, citando institutos. É carregado pelo `interview_archetype.py` via `_load_situational_briefing()` e injetado nos system prompts.

**Futuro:** quando os chunks indexados estiverem disponíveis (após `run_all.py` rodar), o briefing pode ser regenerado via Opus a partir dos chunks (mais fidelidade, menos risco de drift). Por enquanto, o briefing manual cobre o caso de uso "contexto situacional" sem depender do pipeline.

## Regra ZERO dados inventados

Conforme `CLAUDE.md`:
- Toda URL no spec veio de WebSearch real (Google indexado = evidência de existência)
- Validação final de YouTube acontece na pipeline (DO runner), não no sandbox
- Quotes e estatísticas no briefing devem vir dos chunks indexados, não de memória do modelo
- O briefing atual cita instituições e datas verificadas; estatísticas precisam ser checadas contra fonte original antes de re-uso fora deste contexto
