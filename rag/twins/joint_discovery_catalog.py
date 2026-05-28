"""
Canonical arch-mkt joint-discovery catalog (Lote A — 15 twins).

Source: company/SyntheticPerson/syntheticperson-ai/46-ASPASIA-IZA-ROADMAP-ORCHESTRATION.md §4
Research goals and openers are copied from that doc — do not invent alternatives.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    slug: str
    research_goal: str
    opener: str
    priority: int  # 0=P0, 1=P1, 2=P2


ARCH_MKT_CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        slug="arch-mkt-orquestrador-insights",
        research_goal="Quando synthetic research entra vs campo real; audit trail mínimo",
        opener="Conta da última vez que você levou um insight pro comitê — o que estava no slide?",
        priority=0,
    ),
    CatalogEntry(
        slug="arch-mkt-cultura-cmo-legado",
        research_goal='Objeções de CMO a "persona sintética"; brand vs performance',
        opener="Conta da última campanha que você quase não aprovou — o que te travou?",
        priority=0,
    ),
    CatalogEntry(
        slug="arch-mkt-fronteira-ai-martech",
        research_goal="Expectativa de integração e custo; vs ChatGPT in-house",
        opener="Conta da última vez que testou IA pra pesquisa — o que funcionou e o que você descartou?",
        priority=0,
    ),
    CatalogEntry(
        slug="arch-mkt-evidencia-varejo",
        research_goal="TTFI e ciclo semanal; A/B de claim",
        opener="Conta da última reunião de campanha onde faltou dado — o que você improvisou?",
        priority=1,
    ),
    CatalogEntry(
        slug="arch-mkt-evidencia-cpg-global",
        research_goal="Calibração IBGE/PNAD; multinational vs BR",
        opener="Conta da última vez que distorceu segmentação por pressa.",
        priority=1,
    ),
    CatalogEntry(
        slug="arch-mkt-performance-digital",
        research_goal="Mensagem A/B vs entrevista; orçamento de mídia",
        opener="Conta do último teste de criativo que mudou o plano de mídia.",
        priority=1,
    ),
    CatalogEntry(
        slug="arch-mkt-guardiao-privacy",
        research_goal="LGPD, PII, o que faria não confiar",
        opener="Conta da última vez que bloqueou um fornecedor de dados — por quê?",
        priority=1,
    ),
    CatalogEntry(
        slug="arch-mkt-evidencia-consultor",
        research_goal="Vocabulário Insights/Lab; objeções de governança (cluster consultor)",
        opener="Conta da última vez que um cliente questionou a metodologia — o que você respondeu?",
        priority=2,
    ),
    CatalogEntry(
        slug="arch-mkt-performance-trade",
        research_goal="Vocabulário Insights/Lab; objeções de governança (cluster trade)",
        opener="Conta da última negociação com varejo onde dados de shopper mudaram o acordo.",
        priority=2,
    ),
    CatalogEntry(
        slug="arch-mkt-performance-rgm",
        research_goal="Vocabulário Insights/Lab; objeções de governança (cluster RGM)",
        opener="Conta da última vez que pricing/promo dependeu de um número que você não confiava.",
        priority=2,
    ),
    CatalogEntry(
        slug="arch-mkt-cultura-brand-agency",
        research_goal="Vocabulário Insights/Lab; objeções de governança (cluster agency)",
        opener="Conta da última vez que criativo e dados brigaram na mesma reunião.",
        priority=2,
    ),
    CatalogEntry(
        slug="arch-mkt-cultura-antropologo",
        research_goal="Vocabulário Insights/Lab; objeções de governança (cluster antropólogo)",
        opener="Conta da última vez que cultura e quant entraram em conflito no mesmo projeto.",
        priority=2,
    ),
    CatalogEntry(
        slug="arch-mkt-orquestrador-consultor",
        research_goal="Vocabulário Insights/Lab; objeções de governança (cluster orquestrador consultor)",
        opener="Conta da última vez que você traduziu insight técnico pra C-level.",
        priority=2,
    ),
    CatalogEntry(
        slug="arch-mkt-guardiao-brand-safety",
        research_goal="Vocabulário Insights/Lab; objeções de governança (cluster brand safety)",
        opener="Conta da última vez que quase pausou uma campanha por risco de marca.",
        priority=2,
    ),
    CatalogEntry(
        slug="arch-mkt-fronteira-foresight",
        research_goal="Vocabulário Insights/Lab; objeções de governança (cluster foresight)",
        opener="Conta da última vez que um cenário de futuro entrou num plano real.",
        priority=2,
    ),
)

assert len(ARCH_MKT_CATALOG) == 15, f"expected 15 arch-mkt slugs, got {len(ARCH_MKT_CATALOG)}"
