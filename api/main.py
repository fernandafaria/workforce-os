"""
Workforce OS — API Gateway (FastAPI)
Production endpoints for Second Brain skin.

Deploy: Railway
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import logging
import json
import asyncio

from .config import get_settings

log = logging.getLogger(__name__)

app = FastAPI(
    title="Workforce OS — Second Brain API",
    version="0.1.0",
    description="Motor do Workforce OS. Conselho executivo 24h para tomadores de decisão.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════════════════
# Models
# ═══════════════════════════════════════════════════════════════════════════

class CouncilRequest(BaseModel):
    question: str
    context: Optional[str] = None
    agents: Optional[List[str]] = None
    stream: bool = False

class GroupRequest(BaseModel):
    topic: str
    participants: Optional[List[str]] = None
    max_rounds: int = 5
    stream: bool = False

class PingRequest(BaseModel):
    sector: Optional[str] = None
    user_id: Optional[str] = None

class MemoryRequest(BaseModel):
    user_id: str
    observation: str
    category: str = "decision"

# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    from .agents.catalog import AgentCatalog
    catalog = AgentCatalog()
    count = await catalog.count()
    return {
        "status": "ok",
        "service": "Workforce OS — Second Brain API",
        "agents": count,
        "verticals": 7,
    }


@app.post("/council")
async def council(req: CouncilRequest):
    """Conselho 1:1 — CEO pergunta, sistema seleciona e orquestra especialistas."""
    from .orchestrator import CouncilOrchestrator
    from .formatter.hierarchical import HierarchicalFormatter
    
    orch = CouncilOrchestrator()
    result = await orch.execute(req.question, req.context, req.agents)
    
    formatter = HierarchicalFormatter()
    formatted = await formatter.format_council(
        req.question,
        result["responses"],
        result.get("synthesis", ""),
    )
    
    return formatted


@app.post("/council/stream")
async def council_stream(req: CouncilRequest):
    """Conselho 1:1 com SSE streaming."""
    from .orchestrator import CouncilOrchestrator
    from .formatter.hierarchical import HierarchicalFormatter
    
    async def event_stream():
        orch = CouncilOrchestrator()
        result = await orch.execute(req.question, req.context, req.agents)
        
        formatter = HierarchicalFormatter()
        formatted = await formatter.format_council(
            req.question,
            result["responses"],
            result.get("synthesis", ""),
        )
        
        yield f"data: {json.dumps(formatted)}\n\n"
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/group")
async def group(req: GroupRequest):
    """Grupo debate — múltiplos agentes debatem em rounds."""
    from .orchestrator import GroupOrchestrator
    from .formatter.hierarchical import HierarchicalFormatter
    
    orch = GroupOrchestrator()
    result = await orch.execute(req.topic, req.participants, req.max_rounds)
    
    formatter = HierarchicalFormatter()
    formatted = await formatter.format_group(req.topic, result)
    
    return formatted


@app.post("/group/stream")
async def group_stream(req: GroupRequest):
    """Grupo debate com SSE streaming."""
    from .orchestrator import GroupOrchestrator
    from .formatter.hierarchical import HierarchicalFormatter
    
    async def event_stream():
        orch = GroupOrchestrator()
        result = await orch.execute(req.topic, req.participants, req.max_rounds)
        
        formatter = HierarchicalFormatter()
        formatted = await formatter.format_group(req.topic, result)
        
        yield f"data: {json.dumps(formatted)}\n\n"
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/ping")
async def ping(sector: Optional[str] = None, user_id: Optional[str] = None):
    """Briefing diário."""
    from .orchestrator import PingOrchestrator
    from .formatter.hierarchical import HierarchicalFormatter
    
    orch = PingOrchestrator()
    result = await orch.execute(sector, user_id)
    
    formatter = HierarchicalFormatter()
    return await formatter.format_ping(result)


@app.get("/personas")
async def list_personas(team: Optional[str] = None, search: Optional[str] = None):
    """Catálogo de agentes disponíveis."""
    from .agents.catalog import AgentCatalog
    catalog = AgentCatalog()
    
    if search:
        results = await catalog.search(search, team)
        return {"personas": results, "total": len(results)}
    
    personas = await catalog.list_all(team)
    return {"personas": personas, "total": len(personas)}


@app.get("/personas/{slug}")
async def get_persona(slug: str):
    """Detalhes de um agente."""
    from .agents.catalog import AgentCatalog
    catalog = AgentCatalog()
    
    prompt = await catalog.get_prompt(slug)
    if not prompt:
        raise HTTPException(404, f"Agent '{slug}' not found")
    
    return {"slug": slug, "prompt": prompt, "length": len(prompt)}


@app.get("/domains")
async def list_domains():
    """Domínios de conhecimento disponíveis para routing."""
    from .router.central import CentralRouter
    router = CentralRouter()
    return {"domains": router.get_domains()}


@app.post("/memories")
async def store_memory(req: MemoryRequest):
    """Armazena uma decisão/observação na memória."""
    from .memory.store import MemoryStore
    store = MemoryStore()
    return await store.add(req.user_id, req.observation, req.category)


@app.get("/memories/{user_id}")
async def get_memories(user_id: str, limit: int = 20):
    """Recupera memórias de um usuário."""
    from .memory.store import MemoryStore
    store = MemoryStore()
    memories = await store.get_user_memories(user_id, limit)
    return {"user_id": user_id, "memories": memories}


# ═══════════════════════════════════════════════════════════════════════════
# Agentes — Criação de agentes autônomos
# ═══════════════════════════════════════════════════════════════════════════

from .agents.creator import router as agent_router
app.include_router(agent_router)


# ═══════════════════════════════════════════════════════════════════════════
# Rituais — Protocolos Febrain
# ═══════════════════════════════════════════════════════════════════════════

from .rituals.runner import RitualOrchestrator as _RitualOrch
_ritual_orch = _RitualOrch()


@app.get("/rituals")
async def list_rituals():
    """Lista todos os rituais disponíveis (protocolos Febrain)."""
    return {"rituals": _ritual_orch.list_rituals()}


@app.get("/rituals/{slug}")
async def get_ritual(slug: str):
    """Detalhes de um ritual específico (SKILL.md)."""
    protocol = _ritual_orch.get_protocol(slug)
    if not protocol:
        raise HTTPException(404, f"Ritual '{slug}' não encontrado")
    return {"slug": slug, "protocol_length": len(protocol), "protocol": protocol[:5000]}


@app.post("/rituals/{slug}/run")
async def run_ritual(slug: str, topic: str, context: Optional[str] = None, agents: Optional[List[str]] = None):
    """Executa um ritual (Board Review, Deep Dive, War Room, etc)."""
    result = await _ritual_orch.run_ritual(slug, topic, context, agents)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Memory Pipeline — Observação → Destilação → Embedding → Busca
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/memories/pipeline/observe")
async def memory_observe(
    user_id: str,
    session_type: str,
    topic: str,
    agents: Optional[List[str]] = None,
):
    """Fase 1: Salva observação bruta na memória (observational_memory)."""
    from .memory.pipeline import MemoryPipeline
    pipeline = MemoryPipeline()
    return await pipeline.observe(user_id, session_type, topic, agents or [], {})


@app.post("/memories/pipeline/distill")
async def memory_distill(
    user_id: str,
    session_content: str,
    session_type: str = "council",
    dry_run: bool = False,
):
    """Fase 2: Extrai decisões, riscos, ações e perguntas da sessão (distill-memory protocol)."""
    from .memory.pipeline import MemoryPipeline
    pipeline = MemoryPipeline()
    return await pipeline.distill(user_id, session_content, session_type, dry_run)


@app.post("/memories/pipeline/embed")
async def memory_embed(user_id: str, limit: int = 50):
    """Fase 3: Gera embeddings Voyage para memórias não-indexadas."""
    from .memory.pipeline import MemoryPipeline
    pipeline = MemoryPipeline()
    return await pipeline.embed_memories(user_id, limit)


@app.get("/memories/search")
async def memory_search(
    user_id: str,
    query: str,
    memory_type: Optional[str] = None,
    limit: int = 10,
):
    """Busca semântica em memórias (pgvector + Voyage)."""
    from .memory.pipeline import MemoryPipeline
    pipeline = MemoryPipeline()
    results = await pipeline.search(user_id, query, memory_type, limit)
    return {"user_id": user_id, "query": query, "results": results}


@app.post("/memories/pipeline/full")
async def memory_full_pipeline(
    user_id: str,
    session_type: str,
    topic: str,
    session_content: str,
    agents: Optional[List[str]] = None,
    dry_run: bool = False,
):
    """Pipeline completo: observa → destila → gera embeddings."""
    from .memory.pipeline import MemoryPipeline
    pipeline = MemoryPipeline()
    return await pipeline.run_full_pipeline(
        user_id, session_type, topic, agents or [], session_content, dry_run
    )


# ═══════════════════════════════════════════════════════════════════════════
# MCP Server (FastMCP) — montado como sub-app
# ═══════════════════════════════════════════════════════════════════════════

from .mcp_server import mcp

mcp_app = mcp.http_app(path="/mcp")
app.mount("/mcp", mcp_app)
