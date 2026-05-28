"""
Workforce OS — Ping Orchestrator
Briefing diário: market scan, sector news, alerts.

Target: Tomador de decisão que começa o dia.
"""

from typing import Optional, List, Dict, Any
import logging
import asyncio

from ..agents.catalog import AgentCatalog
from ..config import get_settings

log = logging.getLogger(__name__)

# Sector → domain mapping for routing
SECTOR_DOMAINS = {
    "tecnologia": ["tech", "ai", "saas"],
    "varejo": ["sales", "marketing", "operations"],
    "industria": ["operations", "finance", "strategy"],
    "saude": ["compliance", "product", "operations"],
    "financas": ["finance", "risk", "compliance"],
    "agro": ["operations", "strategy", "industry"],
    "servicos": ["sales", "marketing", "people"],
}


class PingOrchestrator:
    """Generates daily briefings for executives."""

    def __init__(self):
        self.settings = get_settings()
        self.catalog = AgentCatalog()

    async def execute(
        self,
        sector: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a daily briefing.

        Returns:
            Dict with market items, sector news, and alerts.
        """
        sector = sector or "tecnologia"
        log.info(f"Ping: generating briefing for sector={sector}")

        # Get market overview (general)
        market = await self._get_market_overview()

        # Get sector-specific news
        sector_news = await self._get_sector_news(sector)

        # Get alerts (risks, urgent items)
        alerts = await self._get_alerts(sector, user_id)

        return {
            "sector": sector,
            "market": market,
            "sector_news": sector_news,
            "alerts": alerts,
            "generated_at": str(asyncio.get_event_loop().time()),
        }

    async def _get_market_overview(self) -> List[str]:
        """Get general market highlights."""
        # In production: fetch from knowledge retriever or external APIs
        return [
            "Índices futuros: S&P +0.3%, Nasdaq +0.5% (pré-mercado)",
            "Dólar: R$5.72 (-0.8% vs ontem)",
            "Petróleo Brent: $78.40/barril (estável)",
            "Cripto: BTC $68.2k (+2.1% 24h)",
        ]

    async def _get_sector_news(self, sector: str) -> List[str]:
        """Get sector-specific news items."""
        # In production: RAG search from Febrain knowledge verticais
        general_items = {
            "tecnologia": [
                "OpenAI anuncia GPT-5 com reasoning avançado — benchmark +40%",
                "Regulamentação de IA na UE entra em vigor próxima semana",
                "Mercado de SaaS cresce 18% YoY no Brasil (ABES)",
            ],
            "varejo": [
                "E-commerce Brasil: +12% no trimestre (ABComm)",
                "Magazine Luiza anuncia novo marketplace B2B",
                "Tendência: social commerce domina 30% das vendas online",
            ],
            "financas": [
                "Selic mantida em 10.50% — Copom sinaliza pausa",
                "Open Finance atinge 40M de consentimentos ativos",
                "Fintechs captam R$2.1B no Q1 2026",
            ],
        }

        items = general_items.get(sector, [f"Setor '{sector}': sem dados específicos disponíveis."])

        # Try to get more specific data from Febrain knowledge base
        try:
            from ..knowledge.retriever import KnowledgeRetriever
            retriever = KnowledgeRetriever()
            results = await retriever.search(f"notícias recentes setor {sector}", vertical=sector, top_k=3)
            if results:
                items.extend([r.get("content", "")[:200] for r in results])
        except Exception:
            pass

        return items

    async def _get_alerts(self, sector: str, user_id: Optional[str]) -> List[str]:
        """Get alerts, risks, urgent items for the user's sector."""
        alerts = [
            f"⚠️ Novo marco regulatório para {sector} — consulta pública até 15/jun",
        ]

        # Check user's recent memories for pending decisions/risks
        if user_id:
            try:
                from ..memory.store import MemoryStore
                store = MemoryStore()
                memories = await store.get_user_memories(user_id, limit=5)
                for m in memories:
                    obs = m.get("observation", "")
                    if any(w in obs.lower() for w in ["risco", "urgente", "prazo"]):
                        alerts.append(f"📋 Sua memória: {obs[:150]}...")
            except Exception:
                pass

        return alerts
