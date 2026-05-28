"""
Workforce OS — FastMCP Server
The canonical interface for agents, knowledge, and orchestration.

Built on FastMCP (25.3k stars, Prefect) — the standard MCP framework.
Exposes tools, resources, and prompts for both Second Brain and Workforce skins.
"""

from fastmcp import FastMCP
from typing import Optional, List, Dict, Any

mcp = FastMCP("Workforce OS — Second Brain")

# ═══════════════════════════════════════════════════════════════════════════
# TOOLS — Agentes
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool
async def get_agent_prompt(slug: str) -> str:
    """Retorna o SOUL completo de um agente Febrain (system prompt + knowledge base)."""
    from .agents.catalog import AgentCatalog
    catalog = AgentCatalog()
    prompt = await catalog.get_prompt(slug)
    if not prompt:
        return f"Agent '{slug}' not found."
    return prompt


@mcp.tool
async def match_agents(query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """
    Busca semântica de agentes por embedding similarity + domain rules.
    Usado pelo Router Central para selecionar especialistas.
    """
    from .agents.catalog import AgentCatalog
    catalog = AgentCatalog()
    return await catalog.match(query, top_k)


@mcp.tool
async def list_agents(team: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista todos os agentes disponíveis, opcionalmente filtrados por time."""
    from .agents.catalog import AgentCatalog
    catalog = AgentCatalog()
    return await catalog.list_all(team)


# ═══════════════════════════════════════════════════════════════════════════
# TOOLS — Conhecimento
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool
async def search_knowledge(
    query: str,
    persona_slug: Optional[str] = None,
    vertical: Optional[str] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    RAG: busca na knowledge base (verticais setoriais + contexto BR + KBs de agentes).
    Usa pgvector + Voyage embeddings.
    """
    from .knowledge.retriever import KnowledgeRetriever
    retriever = KnowledgeRetriever()
    return await retriever.search(query, persona_slug, vertical, top_k)


@mcp.tool
async def get_vertical_context(vertical: str) -> str:
    """Retorna a knowledge base completa de um setor (indústria, varejo, saúde...)."""
    import os
    base = os.path.expanduser("~/code/Febrain/_shared/knowledge/verticais")
    path = os.path.join(base, f"{vertical}.md")
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return f"Vertical '{vertical}' not found. Available: industria, varejo, saude, tecnologia, agro, servicos, financas"


# ═══════════════════════════════════════════════════════════════════════════
# TOOLS — Orquestração
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool
async def run_council(
    question: str,
    agent_slugs: Optional[List[str]] = None,
    context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executa uma sessão de Conselho 1:1.
    LangGraph: router → framing → Send[] agentes paralelos → aggregate → format.
    """
    from .orchestrator import CouncilOrchestrator
    orch = CouncilOrchestrator()
    return await orch.execute(question, context, agent_slugs)


@mcp.tool
async def run_group(
    topic: str,
    participant_slugs: Optional[List[str]] = None,
    max_rounds: int = 5,
) -> Dict[str, Any]:
    """
    Executa debate em Grupo multi-agente.
    LangGraph: init → loop[Send[] rounds paralelos] → consensus → synthesize.
    """
    from .orchestrator import GroupOrchestrator
    orch = GroupOrchestrator()
    return await orch.execute(topic, participant_slugs, max_rounds)


@mcp.tool
async def run_ping(sector: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Gera briefing diário para o setor/executivo."""
    from .orchestrator import PingOrchestrator
    orch = PingOrchestrator()
    return await orch.execute(sector, user_id)


# ═══════════════════════════════════════════════════════════════════════════
# TOOLS — Memória
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool
async def store_memory(
    user_id: str,
    observation: str,
    category: str = "decision",
) -> Dict[str, Any]:
    """Armazena uma observação/decision na memória longitudinal (Supabase)."""
    from .memory.store import MemoryStore
    store = MemoryStore()
    return await store.add(user_id, observation, category)


@mcp.tool
async def get_memories(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Recupera memórias (decisões, observações) de um usuário."""
    from .memory.store import MemoryStore
    store = MemoryStore()
    return await store.get_user_memories(user_id, limit)


# ═══════════════════════════════════════════════════════════════════════════
# RESOURCES
# ═══════════════════════════════════════════════════════════════════════════

@mcp.resource("knowledge://verticals/{vertical}")
async def vertical_resource(vertical: str) -> str:
    """Knowledge base de um setor vertical."""
    return await get_vertical_context(vertical)


@mcp.resource("agent://{slug}")
async def agent_resource(slug: str) -> str:
    """SOUL completo de um agente."""
    return await get_agent_prompt(slug)


# ═══════════════════════════════════════════════════════════════════════════
# PROMPTS
# ═══════════════════════════════════════════════════════════════════════════

@mcp.prompt
async def council_prompt(question: str) -> str:
    """Template de prompt para sessão de Conselho."""
    return f"""PERGUNTA DO EXECUTIVO: "{question}"

INSTRUÇÃO: Dê sua recomendação em 2-3 parágrafos, considerando sua especialidade.
Seja direto, acionável e honesto. Se houver riscos, mencione-os explicitamente."""


@mcp.prompt
async def group_prompt(topic: str, round_num: int = 1) -> str:
    """Template de prompt para debate em Grupo."""
    if round_num == 1:
        return f'TÓPICO EM DEBATE: "{topic}"\n\nDê sua opinião inicial. 2 parágrafos.'
    return f'TÓPICO: "{topic}"\n\nROUND {round_num}: Responda ao que foi dito. Se concordar, diga "concordo com [nome]". Se discordar, diga "discordo de [nome]".'
