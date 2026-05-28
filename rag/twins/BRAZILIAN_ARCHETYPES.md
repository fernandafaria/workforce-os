# Arquétipos Populacionais Brasileiros — Roadmap & Runbook

> **O que é**: twins sintéticos de segmentos da população brasileira (não de indivíduos), usados para discovery de produto em escala. LGPD-safe por design (`authorization: archetype_synthetic`).

## Status (2026-04-23)

**Validados (passed Hamel p70 ≥ 0.72):**

| # | Slug | p70 | twin_id |
|---|---|---|---|
| 1 | `arch-c-mae-se-urbano` | 0.744 | confirmado no PR #202/#164 main |
| 16 | `arch-a-clevel-jovem` | 0.745 | `aebe2404-cc31-44e4-99a8-3006f78b4a55` (PR #211) |

**Specs prontos para dispatch (corpus já ingestado no runner):**

| # | Slug | chunks | hold |
|---|---|---|---|
| 20 | `arch-d-desempregada-mae-solo` | 71 | 14 |
| 24 | `arch-d-adolescente-periferia` | 148 | 29 |
| 25 | `arch-c-universitario-primeira-gen` | 543 | 107 |
| 29 | `arch-c-aposentado-inss` | 393 | 78 |
| 15 | `arch-b-pequeno-empresario` | 61 | 13 |

**Cobertura acumulada**: ~64M adultos BR + decisor PJ pequeno/médio (~40% população adulta).

## Gate (Hamel Layer-1)

`passes_production_gate(twin, holdout_threshold=0.72)` para `archetype_synthetic` (vs 0.75 de figura pública). Racional: corpus agregado (ethnografia + 3a-pessoa) plateau 2-3 pts abaixo de figura pública sem piorar para discovery.

Código: `rag/twins/schema.py` + `rag/twins/eval_twin.py` — já live em main.

## Regra inegociável (CLAUDE.md)

**ZERO dados inventados.** Todo URL/quote/stat precisa vir de WebSearch ou fonte verificada. Dispatch 026/027 queimados com YT IDs chutados provaram o custo.

## Os 40 arquétipos planejados

> Pesos populacionais estimados do IBGE PNAD 2022 + Sebrae/Andifes.

### Classe C urbano SE/NE — ~30% adultos
1. ✅ Mãe C, 35-45, SE, filhos adolescentes (~25M)
2. ⏳ CLT operacional C, 25-35, SE, jovem pai
3. ⏳ App worker C, 25-35, SE, informal
4. ⏳ Diarista/cuidadora C/D, 40-55, evangélica
5. ⏳ MEI vendedor C, 30-45, NE
6. ⏳ Funcionário público municipal C, 45-55, NE

### Classe C interior + rural — ~10%
7-9. ⏳ Pequeno agricultor D, funcionária pública interior SP, comerciante bairro MG

### Classe B — ~13%
10-14. ⏳ Jovem profissional B, casal DINK B, mãe retornada B, gerente CLT B, aposentada B
15. ⏳ **Pequeno empresário B, 45-60, sucessão pendente (spec pronto)**

### Classe A — ~3%
16. ✅ C-level jovem A (~400k)
17-19. ⏳ Médico/advogado A, herdeiro 2ª gen A, rentier A

### Classe D/E — ~30%
20. ⏳ **Desempregada mãe solo D/E (spec pronto)**
21-23. ⏳ Informal N, catador E, mãe Bolsa Família D
24. ⏳ **Adolescente periferia D (spec pronto)**

### Jovens — ~15% adultos
25. ⏳ **Universitário primeira-gen C (spec pronto)**
26-28. ⏳ Influenciador aspirante C, trainee B, nini D

### Sêniores — ~18% adultos
29. ⏳ **Aposentado INSS C (spec pronto)**
30-31. ⏳ Viúva idosa D interior, aposentada ativa digital B

### Regionais específicos
32-36. ⏳ Empreendedor agro A/B CO, pequeno produtor rural C MT/PR, ribeirinho N, ambulante turístico NE, indígena urbanizado

### Minorias relevantes
37-40. ⏳ LGBT urbano B/A, imigrante latino SP/SC, PcD, idoso LGBT C

## Playbook para disparar 1 arquétipo

1. **Criar spec** em `rag/twins/persons/arch-<slug>.yaml` seguindo o padrão de `arch-c-mae-se-urbano.yaml`:
   - 3-5 URLs de ethnografia acadêmica (Scielo, PUC, Unisinos)
   - 3-5 URLs de jornalismo longform (Piauí, Agência Pública, Exame, Brazil Journal, InfoMoney)
   - 1-3 URLs Wikipedia (contexto socioeconômico)
   - 2-6 URLs YouTube 1ª pessoa (via captions-api + Webshare proxy no DO runner — NUNCA testar URLs do sandbox Claude Code)
   - **TODAS** via WebSearch verificado — zero inventado

1.1. **Adicionar contexto de dados governamentais BR** — para todo archetype BR, consultar `rag/br_gov_data/` (catálogo unificado de IBGE, BCB, IPEA, Câmara, Senado, TSE, INEP, ANAC, DataSUS, ANVISA, INPE, PNCP e correlatos, alinhado ao [`mcp-brasil`](https://github.com/Mcp-Brasil/mcp-brasil)):

   ```bash
   # Quais domínios casam com este archetype?
   python -m rag.br_gov_data suggest rag/twins/persons/arch-<slug>.yaml

   # Gera bloco markdown injetável com URLs oficiais
   python -m rag.br_gov_data render \
     --persona rag/twins/persons/arch-<slug>.yaml \
     -o rag/twins/persons/arch-<slug>.br_gov_context.md
   ```

   Exemplos:
   - `arch-c-aposentado-inss` → `saude`, `economia`, `geografia-demografia` (DataSUS, Farmácia Popular, INSS, IPCA)
   - `arch-a-empreendedor-agro` → `meio-ambiente`, `empresas-tributario`, `geografia-demografia` (INPE PRODES, IBAMA, PNCP)
   - `arch-b-pequeno-empresario` → `empresas-tributario`, `transparencia`, `economia` (PNCP, Simples Nacional, SICONFI)

   URLs do bloco gerado podem entrar diretamente na lista `sources:` do spec YAML (todas são fontes oficiais e verificáveis — segue a regra-mãe ZERO inventado).

2. **Commit + push** para branch `claude/*`

3. **Criar dispatch** em `rag/twins/.dispatch/YYYY-MM-DD-NNN-<slug>.yml`:
   ```yaml
   slug: arch-<slug>
   mode: full
   confirm_full_mode: true
   skip_transcribe: false
   ```

4. **Commit + push** — GH Actions fire automaticamente via file trigger

5. **Ler diagnostic no PR comment** — p70 + passed_gate

### Lições aprendidas (cuidados)

- **NÃO fazer batch > 2 archetypes no mesmo dispatch** — timeout 90min estoura com corpus > 300 chunks. Rodar 1-a-1.
- **Orçamento Anthropic**: build + eval de 1 archetype custa ~$5. Conferir saldo antes de dispatch de 5+.
- **Webshare proxy**: YouTube é fetcheado SÓ no DO runner com `HTTPS_PROXY` configurado. Captions-API via proxy preserva 1ª pessoa.
- **Groq Whisper** é o fallback quando caption não existe (`WHISPER_BACKEND=groq`).
- **Dispatch selection bug conhecido**: `ls -t` no workflow pega mtime errado. Fix pendente em PR que troca para `ls | sort | tail` (ordenação lexical).

## Arquitetura pendente

- **Migrar SQLite → Supabase** (`supabase/migrations/074_entrepreneur_twins.sql` — planejado no PR #164 original mas adiado). Libera webapp/chat/agent access aos twins. Fazer antes de escalar pros 33 restantes.
- **Layer 2 (stylometry)** + **Layer 3 (LLM-judge pairwise)** do Hamel — scaffold em `eval_twin.py` TODO.
- **Composição cross-arquétipo** — discovery que precisa de "olhar do aposentado sobre produto X" + "olhar da mãe C sobre produto X" simultaneamente.
