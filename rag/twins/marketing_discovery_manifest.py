"""
marketing_discovery_manifest — Lote A/B cohort specs for Insights/Lab discovery.

Canonical goals/openers from
company/SyntheticPerson/syntheticperson-ai/46-ASPASIA-IZA-ROADMAP-ORCHESTRATION.md §4.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketingInterviewSpec:
    person_id: str
    lote: str  # A | B
    priority: str  # P0 | P1 | P2 | T1 | T2
    research_goal: str
    opener: str


# Lote A — P0 (run first)
LOTE_A_P0: tuple[MarketingInterviewSpec, ...] = (
    MarketingInterviewSpec(
        person_id="arch-mkt-orquestrador-insights",
        lote="A",
        priority="P0",
        research_goal=(
            "Quando synthetic research entra vs campo real; audit trail mínimo"
        ),
        opener=(
            "Conta da última vez que você levou um insight pro comitê — o que estava no slide?"
        ),
    ),
    MarketingInterviewSpec(
        person_id="arch-mkt-cultura-cmo-legado",
        lote="A",
        priority="P0",
        research_goal=(
            'Objeções de CMO a "persona sintética"; brand vs performance'
        ),
        opener=(
            "Conta da última campanha que você quase não aprovou — o que te travou?"
        ),
    ),
    MarketingInterviewSpec(
        person_id="arch-mkt-fronteira-ai-martech",
        lote="A",
        priority="P0",
        research_goal=(
            "Expectativa de integração e custo; vs ChatGPT in-house"
        ),
        opener=(
            "Conta da última vez que testou IA pra pesquisa — o que funcionou e o que você descartou?"
        ),
    ),
)

LOTE_A_P1: tuple[MarketingInterviewSpec, ...] = (
    MarketingInterviewSpec(
        person_id="arch-mkt-evidencia-varejo",
        lote="A",
        priority="P1",
        research_goal="TTFI e ciclo semanal; A/B de claim",
        opener="Conta da última reunião de campanha onde faltou dado — o que você improvisou?",
    ),
    MarketingInterviewSpec(
        person_id="arch-mkt-evidencia-cpg-global",
        lote="A",
        priority="P1",
        research_goal="Calibração IBGE/PNAD; multinational vs BR",
        opener="Conta da última vez que distorceu segmentação por pressa.",
    ),
    MarketingInterviewSpec(
        person_id="arch-mkt-performance-digital",
        lote="A",
        priority="P1",
        research_goal="Mensagem A/B vs entrevista; orçamento de mídia",
        opener="Conta do último teste de criativo que mudou o plano de mídia.",
    ),
    MarketingInterviewSpec(
        person_id="arch-mkt-guardiao-privacy",
        lote="A",
        priority="P1",
        research_goal="LGPD, PII, o que faria não confiar",
        opener="Conta da última vez que bloqueou um fornecedor de dados — por quê?",
    ),
)

CMO_TIER1: tuple[str, ...] = (
    "daniela-cachich",
    "eduardo-tracanella",
    "juliana-cury",
    "alexia-duffles",
    "karla-felmanas",
    "andre-britto",
    "marcelo-bronze",
    "marcio-carvalho",
    "renata-altenfelder",
    "guilherme-bernardes",
    "tatiana-ponce",
    "cathyelle-schroeder",
)

CMO_TIER2: tuple[str, ...] = (
    "felipe-cohen",
    "renato-camargo",
    "igor-puga",
    "pethra-ferraz",
    "cecilia-bottai-mondino",
    "bernardo-marotta",
    "daniel-machado-campos",
    "analigia-martins",
)

DEFAULT_CMO_RESEARCH_GOAL = (
    "Como um CMO/Head de Marketing no Brasil avalia, compra ou rejeita "
    "ferramentas de pesquisa e simulação — e o que precisa para levar ao board."
)

DEFAULT_CMO_OPENER = (
    "Conta da última vez que você precisou defender um número ou um insight "
    "para o board ou para o CEO — o que estava na mesa?"
)


def all_lote_a_specs() -> list[MarketingInterviewSpec]:
    return [*LOTE_A_P0, *LOTE_A_P1]


def specs_for_priority(priority: str) -> list[MarketingInterviewSpec]:
    pri = priority.upper()
    if pri == "P0":
        return list(LOTE_A_P0)
    if pri == "P1":
        return list(LOTE_A_P1)
    if pri in ("P0,P1", "P0+P1"):
        return all_lote_a_specs()
    raise ValueError(f"Unknown priority {priority!r}; use P0, P1, or P0,P1")


def cmo_slugs(tier: str) -> list[str]:
    t = tier.upper()
    if t == "T1":
        return list(CMO_TIER1)
    if t == "T2":
        return list(CMO_TIER2)
    if t in ("T1,T2", "ALL"):
        return [*CMO_TIER1, *CMO_TIER2]
    raise ValueError(f"Unknown CMO tier {tier!r}; use T1, T2, or T1,T2")
