"""
executive_ai_fluency_cohort — 200-cell matrix for exec AI fluency / FOMO discovery.

20 archetype bases × 10 regional/company slices = 200 unique person_ids.

Slug pattern: arch-exec-ai-{archetype_id}-{slice_id}

See company/SyntheticPerson/syntheticperson-ai/47-EXEC-AI-FLUENCY-PSYCHOGRAPHY.md
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecSlice:
    slice_id: str
    label: str
    regiao: str
    company_context: str


@dataclass(frozen=True)
class ExecArchetypeBase:
    archetype_id: str
    label: str
    role_typical: str
    tension: str
    vocabulary: str
    opener: str
    research_goal: str


@dataclass(frozen=True)
class ExecCohortCell:
    person_id: str
    archetype_id: str
    slice_id: str
    label: str
    role_typical: str
    regiao: str
    company_context: str
    tension: str
    vocabulary: str
    opener: str
    research_goal: str
    lote: str  # A = P0 bases, B = matrix expansion
    priority: str  # P0 | P1 | P2


SLICES: tuple[ExecSlice, ...] = (
    ExecSlice("sp-cap-listada", "SP capital — empresa listada mid-cap", "SP capital", "listada B3 mid-cap"),
    ExecSlice("sp-cap-scaleup", "SP capital — scale-up Série B+", "SP capital", "scale-up série B+"),
    ExecSlice("sp-int-familia", "SP interior — empresa familiar", "SP interior", "empresa familiar multi-geração"),
    ExecSlice("rj-servicos", "RJ capital — serviços/financeiro", "RJ capital", "serviços e financeiro"),
    ExecSlice("rj-multinacional", "RJ capital — subsidiária multinacional", "RJ capital", "multinacional matriz EUA/EU"),
    ExecSlice("sul-industria", "Sul — indústria", "Sul", "indústria manufatureira"),
    ExecSlice("sul-tech", "Sul — tech B2B", "Sul", "tech B2B SaaS"),
    ExecSlice("ne-varejo", "NE capital — varejo/consumo", "NE capital", "varejo e consumo"),
    ExecSlice("co-agro", "Centro-Oeste — agro", "Centro-Oeste", "agronegócio"),
    ExecSlice("norte-estatal", "Norte/centro público — estatal ou regulado", "Norte/DF", "estatal ou setor altamente regulado"),
)

ARCHETYPE_BASES: tuple[ExecArchetypeBase, ...] = (
    ExecArchetypeBase(
        "travada-chatgpt",
        "Executiva travada — só ChatGPT/Claude como pesquisa",
        "CEO / diretoria geral",
        "Síndrome de atraso; vergonha; não sabe por onde começar",
        "prompt, ChatGPT, Claude, pesquisa, travada, não tenho tempo, Google avançado",
        "Conta da última vez que você abriu o ChatGPT ou Claude no trabalho — o que você estava tentando resolver?",
        "Como um executivo passa do uso chat-only para confiança prática em IA — barreiras reais, não desejos.",
    ),
    ExecArchetypeBase(
        "fomo-demo-comprador",
        "Executivo com FOMO pós-demo — quer comprar fluência/resultado",
        "CEO / presidente",
        "Viu especialistas/análises (ex. Febrain) e quer o mesmo; urgência",
        "demo, especialistas, time de IA, comprar, ficar para trás, resultado",
        "Conta da última vez que você viu uma demo de IA ou time de especialistas e pensou 'preciso disso' — o que apareceu?",
        "O que converteu na demo vs o que ainda trava a compra ou adoção no dia a dia.",
    ),
    ExecArchetypeBase(
        "cfo-cetico-roi",
        "CFO cético — ROI e risco antes de fluência",
        "CFO",
        "Bloqueia investimento sem métrica; medo de projeto eterno",
        "ROI, payback, risco, compliance, budget, business case",
        "Conta da última vez que você segurou budget de IA ou consultoria — o que faltou para aprovar?",
        "Critérios de aprovação de CFO para ferramentas/agentes de IA no Brasil.",
    ),
    ExecArchetypeBase(
        "ceo-familia-legado",
        "CEO empresa familiar — legado vs modernização",
        "CEO",
        "Pressão de sucessão e modernização sem perder identidade",
        "família, sucessão, legado, modernizar, conselho, geração",
        "Conta da última reunião de família ou conselho onde IA ou digital apareceu — o que foi dito?",
        "Como CEO de empresa familiar equilibra legado e pressão por IA.",
    ),
    ExecArchetypeBase(
        "cto-visionario-frustrado",
        "CTO/CIO visionário — time executivo não acompanha",
        "CTO / CIO",
        "Visão técnica vs adoção da diretoria",
        "stack, agente, integração, legado, shadow IT, governança",
        "Conta da última vez que você propôs um piloto de IA e a diretoria freou — o que aconteceu?",
        "Gap entre visão de CTO e fluência do restante da C-suite.",
    ),
    ExecArchetypeBase(
        "chro-upskilling-generico",
        "CHRO — treinamento genérico vs fluência real",
        "CHRO / VP Pessoas",
        "LMS e curso online não mudam comportamento executivo",
        "upskilling, LMS, cultura, liderança, capacitação, NPS interno",
        "Conta do último programa de capacitação em IA que você rodou — o que mediram depois?",
        "O que CHRO considera fluência real vs checklist de treinamento.",
    ),
    ExecArchetypeBase(
        "board-pergunta-estrategia",
        "Conselheiro / board — pergunta estratégia de IA",
        "Board / conselheiro",
        "Pressiona CEO sem operar ferramentas",
        "estratégia, governança, risco reputacional, agenda do conselho",
        "Conta da última pergunta sobre IA que você fez (ou ouviu) em conselho — qual foi?",
        "O que board exige para considerar empresa 'preparada' em IA.",
    ),
    ExecArchetypeBase(
        "cmo-delega-junior",
        "CMO — delega IA para júnior/analista",
        "CMO",
        "Dependência do 'jovem que entende'; medo de parecer perdido",
        "delegar, agência, MarTech, meu time, não sou técnica",
        "Conta da última vez que você pediu para alguém do time 'fazer no ChatGPT' — qual era a entrega?",
        "Como CMO lida com fluência própria vs delegação.",
    ),
    ExecArchetypeBase(
        "coo-medo-automacao",
        "COO — quer automação com medo de erro operacional",
        "COO",
        "Medo de processo quebrado; piloto eterno",
        "processo, SLA, operação, automação, erro, rollback",
        "Conta do último piloto de automação ou IA em operação — onde parou?",
        "Barreiras de COO para escalar automação/agentes.",
    ),
    ExecArchetypeBase(
        "founder-scaleup-impostor",
        "Founder scale-up — impostor técnico",
        "Founder / CEO scale-up",
        "Fundou negócio; IA parece domínio dos filhos do time",
        "fundador, cap table, investor, produto, não sou dev",
        "Conta da última vez que um investidor ou cliente perguntou sobre IA e você improvisou — o que disse?",
        "Como founder mantém credibilidade sem fluência técnica profunda.",
    ),
    ExecArchetypeBase(
        "multinacional-glocal",
        "Executivo BR em multinacional — policy global",
        "Diretor geral BR / VP regional",
        "HQ manda ferramenta; execução local trava",
        "global, HQ, policy, ferramenta aprovada, Brasil local",
        "Conta da última vez que uma ferramenta global de IA chegou e o time BR não adotou — por quê?",
        "Tensão glocal em adoção de IA corporativa.",
    ),
    ExecArchetypeBase(
        "estatal-guardiao",
        "Executivo estatal/regulado — compliance extremo",
        "Diretor estatal / regulado",
        "Medo de auditoria e vazamento",
        "licitação, transparência, auditoria, LGPD, soberania",
        "Conta da última vez que um projeto de IA foi barrado internamente — qual foi o argumento?",
        "Limites percebidos de IA em setor público/regulado.",
    ),
    ExecArchetypeBase(
        "early-adopter-irritado",
        "Early adopter executivo — irritado com colegas",
        "Diretor inovação / CDO",
        "Sabe mais que pares; frustrado com lentidão",
        "já uso, agente, n8n, cursor, por que ainda não, frustração",
        "Conta da última vez que você tentou ensinar um par e desistiu — o que não colou?",
        "Dinâmica de early adopter isolado na C-suite.",
    ),
    ExecArchetypeBase(
        "conselheiro-independente",
        "Conselheiro independente — influencia sem operar",
        "Conselheiro",
        "Recomenda vendors e cursos; não usa ferramentas",
        "conselho, advisory, benchmark, networking, case",
        "Conta da última recomendação que você fez a um CEO sobre IA — baseada em quê?",
        "Como conselheiros moldam compra de fluência vs ferramenta.",
    ),
    ExecArchetypeBase(
        "juridico-bloqueador",
        "Diretor jurídico — bloqueia por risco",
        "General Counsel",
        "Contrato, IP, responsabilidade, dados",
        "contrato, responsabilidade, IP, dados sensíveis, parecer",
        "Conta do último parecer que travou um piloto de IA — qual cláusula pesou?",
        "Objeções jurídicas recorrentes a agentes e LLMs corporativos.",
    ),
    ExecArchetypeBase(
        "head-inovacao-sem-budget",
        "Head inovação — mandato sem budget",
        "Head inovação / digital",
        "Slides de transformação; sem linha de compra",
        "inovação, lab, POC, sem budget, sponsor",
        "Conta do último POC que morreu faltando sponsor — onde travou?",
        "Como heads de inovação vendem fluência internamente sem budget.",
    ),
    ExecArchetypeBase(
        "vp-vendas-crm-ia",
        "VP vendas — CRM e IA tática",
        "VP comercial",
        "Quer produtividade em pipeline; cético a hype",
        "CRM, pipeline, forecast, SDR, copilot vendas",
        "Conta da última ferramenta de IA em vendas que o time testou — ficou ou saiu?",
        "Adoção de IA em revenue sem virar gimmick.",
    ),
    ExecArchetypeBase(
        "supply-chain-piloto",
        "Diretor supply chain — piloto pontual",
        "Diretor supply / logística",
        "Piloto em forecast; resto manual",
        "previsão, estoque, logística, ERP, piloto",
        "Conta do último piloto em supply que saiu do Excel — o que quebrou?",
        "Fluência operacional em IA na cadeia.",
    ),
    ExecArchetypeBase(
        "rh-talent-ai",
        "VP RH — talent e IA em recrutamento",
        "VP RH / talent",
        "IA em triagem; medo de viés",
        "recrutamento, triagem, viés, people analytics",
        "Conta da última vez que IA entrou no processo seletivo — o que o jurídico pediu?",
        "Limites e ganhos de IA em RH executivo.",
    ),
    ExecArchetypeBase(
        "presidente-associacao",
        "Presidente associação setorial — voz do setor",
        "Presidente entidade",
        "Representa indústria; não compra mas influencia",
        "setor, associados, benchmark, evento, pauta",
        "Conta da última pauta de IA que você levou para associados — qual foi a reação?",
        "Influência de líderes setoriais na narrativa de fluência.",
    ),
)

# P0: first 12 archetype bases × SP cap listada only (12 cells)
P0_ARCHETYPE_IDS: frozenset[str] = frozenset(
    a.archetype_id for a in ARCHETYPE_BASES[:12]
)
P0_SLICE_ID = "sp-cap-listada"


def person_id_for(archetype_id: str, slice_id: str) -> str:
    return f"arch-exec-ai-{archetype_id}-{slice_id}"


def _priority_for(archetype_id: str, slice_id: str) -> tuple[str, str]:
    if archetype_id in P0_ARCHETYPE_IDS and slice_id == P0_SLICE_ID:
        return "A", "P0"
    if archetype_id in P0_ARCHETYPE_IDS:
        return "B", "P1"
    return "B", "P2"


def build_cohort_matrix() -> tuple[ExecCohortCell, ...]:
    cells: list[ExecCohortCell] = []
    for base in ARCHETYPE_BASES:
        for sl in SLICES:
            lote, priority = _priority_for(base.archetype_id, sl.slice_id)
            pid = person_id_for(base.archetype_id, sl.slice_id)
            cells.append(
                ExecCohortCell(
                    person_id=pid,
                    archetype_id=base.archetype_id,
                    slice_id=sl.slice_id,
                    label=f"{base.label} — {sl.label}",
                    role_typical=base.role_typical,
                    regiao=sl.regiao,
                    company_context=sl.company_context,
                    tension=base.tension,
                    vocabulary=base.vocabulary,
                    opener=base.opener,
                    research_goal=base.research_goal,
                    lote=lote,
                    priority=priority,
                )
            )
    if len(cells) != 200:
        raise RuntimeError(f"expected 200 cohort cells, got {len(cells)}")
    return tuple(cells)


COHORT_MATRIX: tuple[ExecCohortCell, ...] = build_cohort_matrix()


def cells_for_priority(priority: str) -> list[ExecCohortCell]:
    pri = priority.upper()
    if pri == "P0":
        return [c for c in COHORT_MATRIX if c.priority == "P0"]
    if pri == "P1":
        return [c for c in COHORT_MATRIX if c.priority == "P1"]
    if pri == "P2":
        return [c for c in COHORT_MATRIX if c.priority == "P2"]
    if pri in ("ALL", "P0,P1", "P0+P1", "P0,P1,P2"):
        return list(COHORT_MATRIX)
    raise ValueError(f"Unknown priority {priority!r}; use P0, P1, P2, or ALL")


def archetype_base(archetype_id: str) -> ExecArchetypeBase:
    for a in ARCHETYPE_BASES:
        if a.archetype_id == archetype_id:
            return a
    raise KeyError(archetype_id)
