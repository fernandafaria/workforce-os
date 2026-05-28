"""
Workforce OS — API Gateway (FastAPI)
Production endpoints for Second Brain skin.

Deploy: Railway
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import logging
import json
import asyncio

from .config import get_settings
from .auth import get_user_id

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
    twins: Optional[List[str]] = None
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
async def council(req: CouncilRequest, user_id: str = Depends(get_user_id)):
    """Conselho 1:1 — CEO pergunta, sistema seleciona e orquestra especialistas.

    Optional ``twins`` é a lista de twin_ids (UUIDs) de cognitive twins que
    devem participar junto com as personas selecionadas pelo router.
    """
    from .orchestrator import CouncilOrchestrator
    from .formatter.hierarchical import HierarchicalFormatter

    orch = CouncilOrchestrator()
    result = await orch.execute(
        req.question, req.context, req.agents,
        user_id=user_id, twin_ids=req.twins,
    )

    formatter = HierarchicalFormatter()
    formatted = await formatter.format_council(
        req.question,
        result["responses"],
        result.get("synthesis", ""),
    )
    # Surface twin participants in the final payload for the UI
    formatted["twins"] = result.get("twins", [])
    return formatted


@app.post("/council/stream")
async def council_stream(req: CouncilRequest, user_id: str = Depends(get_user_id)):
    """Conselho 1:1 com SSE streaming."""
    from .orchestrator import CouncilOrchestrator
    from .formatter.hierarchical import HierarchicalFormatter
    
    async def event_stream():
        orch = CouncilOrchestrator()
        result = await orch.execute(
            req.question, req.context, req.agents,
            user_id=user_id, twin_ids=req.twins,
        )

        formatter = HierarchicalFormatter()
        formatted = await formatter.format_council(
            req.question,
            result["responses"],
            result.get("synthesis", ""),
        )
        formatted["twins"] = result.get("twins", [])

        yield f"data: {json.dumps(formatted)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/group")
async def group(req: GroupRequest, user_id: str = Depends(get_user_id)):
    """Grupo debate — múltiplos agentes debatem em rounds."""
    from .orchestrator import GroupOrchestrator
    from .formatter.hierarchical import HierarchicalFormatter
    
    orch = GroupOrchestrator()
    result = await orch.execute(req.topic, req.participants, req.max_rounds)
    
    formatter = HierarchicalFormatter()
    formatted = await formatter.format_group(req.topic, result)
    
    return formatted


@app.post("/group/stream")
async def group_stream(req: GroupRequest, user_id: str = Depends(get_user_id)):
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
async def ping(sector: Optional[str] = None, user_id: str = Depends(get_user_id)):
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
async def store_memory(req: MemoryRequest, user_id: str = Depends(get_user_id)):
    """Armazena uma decisão/observação na memória."""
    from .memory.store import MemoryStore
    store = MemoryStore()
    return await store.add(req.user_id, req.observation, req.category)


@app.get("/memories/{user_id}")
async def get_memories(user_id: str, limit: int = 20, auth_user_id: str = Depends(get_user_id)):
    # Validate user can only access their own memories
    if auth_user_id != user_id:
        raise HTTPException(403, "Cannot access another user's memories")
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
async def run_ritual(slug: str, topic: str, context: Optional[str] = None, agents: Optional[List[str]] = None, user_id: str = Depends(get_user_id)):
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
    session_type: str,
    topic: str,
    agents: Optional[List[str]] = None,
    user_id: str = Depends(get_user_id),
):
    """Fase 1: Salva observação bruta na memória (observational_memory)."""
    from .memory.pipeline import MemoryPipeline
    pipeline = MemoryPipeline()
    return await pipeline.observe(user_id, session_type, topic, agents or [], {})


@app.post("/memories/pipeline/distill")
async def memory_distill(
    session_content: str,
    session_type: str = "council",
    dry_run: bool = False,
    user_id: str = Depends(get_user_id),
):
    """Fase 2: Extrai decisões, riscos, ações e perguntas da sessão (distill-memory protocol)."""
    from .memory.pipeline import MemoryPipeline
    pipeline = MemoryPipeline()
    return await pipeline.distill(user_id, session_content, session_type, dry_run)


@app.post("/memories/pipeline/embed")
async def memory_embed(user_id: str = Depends(get_user_id), limit: int = 50):
    """Fase 3: Gera embeddings Voyage para memórias não-indexadas."""
    from .memory.pipeline import MemoryPipeline
    pipeline = MemoryPipeline()
    return await pipeline.embed_memories(user_id, limit)


@app.get("/memories/search")
async def memory_search(
    query: str,
    memory_type: Optional[str] = None,
    limit: int = 10,
    user_id: str = Depends(get_user_id),
):
    """Busca semântica em memórias (pgvector + Voyage)."""
    from .memory.pipeline import MemoryPipeline
    pipeline = MemoryPipeline()
    results = await pipeline.search(user_id, query, memory_type, limit)
    return {"user_id": user_id, "query": query, "results": results}


@app.post("/memories/pipeline/full")
async def memory_full_pipeline(
    session_type: str,
    topic: str,
    session_content: str,
    agents: Optional[List[str]] = None,
    dry_run: bool = False,
    user_id: str = Depends(get_user_id),
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


# ═══════════════════════════════════════════════════════════════════════════
# Twins — cognitive twins of real people (catalog + creation pipeline)
# ═══════════════════════════════════════════════════════════════════════════

from .twins.catalog import TwinCatalog
from .twins.pipeline import TwinPipeline

_twin_catalog = TwinCatalog()
_twin_pipeline = TwinPipeline()


@app.get("/twins")
async def list_twins(
    twin_kind: Optional[str] = None,
    status: Optional[str] = None,
    include_drafts: bool = False,
    limit: int = 100,
):
    """Catálogo de twins (cognitive twins de pessoas reais).

    Por padrão retorna só os published. include_drafts=true mostra
    manifestos em desenvolvimento.
    """
    twins = await _twin_catalog.list_twins(
        twin_kind=twin_kind,
        status=status,
        include_drafts=include_drafts,
        limit=limit,
    )
    return {"twins": twins, "total": len(twins)}


@app.get("/twins/{twin_id}")
async def get_twin(twin_id: str):
    """Detalhe completo de um twin + status do pipeline."""
    twin = await _twin_catalog.get_twin(twin_id)
    if not twin:
        raise HTTPException(404, f"Twin '{twin_id}' not found")
    return twin


@app.get("/twins/{twin_id}/status")
async def twin_status(twin_id: str):
    """Status do pipeline: chunks ingeridos, sintetizado, eval, etc."""
    return await _twin_catalog.get_status(twin_id)


@app.post("/twins/{twin_id}/ingest")
async def twin_ingest(
    twin_id: str,
    max_sources: Optional[int] = None,
    force: bool = False,
    user_id: str = Depends(get_user_id),
):
    """Stage 2 — Ingere fontes URL do twin (crawl + chunk + Voyage embed)."""
    return await _twin_pipeline.ingest(twin_id, max_sources=max_sources, force=force)


@app.post("/twins/{twin_id}/synthesize")
async def twin_synthesize(twin_id: str, user_id: str = Depends(get_user_id)):
    """Stage 3 — Gera schema cognitivo via Claude Opus a partir do corpus."""
    return await _twin_pipeline.synthesize(twin_id)


@app.post("/twins/{twin_id}/interview")
async def twin_interview(
    twin_id: str,
    num_questions: Optional[int] = None,
    session_label: Optional[str] = None,
    user_id: str = Depends(get_user_id),
):
    """Stage 4 — Gera uma sessão de entrevista de N turnos com o twin."""
    return await _twin_pipeline.interview(
        twin_id, num_questions=num_questions, session_label=session_label
    )


@app.post("/twins/{twin_id}/eval")
async def twin_eval(
    twin_id: str,
    num_probes: Optional[int] = None,
    threshold: Optional[float] = None,
    user_id: str = Depends(get_user_id),
):
    """Stage 5 — Avalia o twin contra chunks holdout (similaridade Voyage)."""
    return await _twin_pipeline.eval(
        twin_id, num_probes=num_probes, threshold=threshold
    )


@app.post("/twins/{twin_id}/publish")
async def twin_publish(twin_id: str, user_id: str = Depends(get_user_id)):
    """Stage 6 — Promove twin para status='eval_passed' se último eval passou."""
    return await _twin_pipeline.publish(twin_id)


# ═══════════════════════════════════════════════════════════════════════════
# Dynamic Agents — spawn-on-demand to fill expertise gaps
# ═══════════════════════════════════════════════════════════════════════════

from .dynamic_agents.catalog import DynamicAgentsCatalog
from .dynamic_agents.spawner import AgentSpawner

_dyn_catalog = DynamicAgentsCatalog()
_dyn_spawner = AgentSpawner()


class SpawnRequest(BaseModel):
    question: str
    expertise_gap: str
    context: Optional[str] = None
    parent_team_slug: Optional[str] = None
    parent_persona_slugs: Optional[List[str]] = None
    ttl_hours: Optional[int] = None
    max_uses: Optional[int] = None


@app.post("/agents/dynamic/spawn")
async def dynamic_agent_spawn(req: SpawnRequest, user_id: str = Depends(get_user_id)):
    """Cria um agente temporário para fechar uma lacuna de expertise no Council."""
    return await _dyn_spawner.spawn(
        question=req.question,
        expertise_gap=req.expertise_gap,
        context=req.context,
        user_id=user_id,
        parent_team_slug=req.parent_team_slug,
        parent_persona_slugs=req.parent_persona_slugs,
        ttl_hours=req.ttl_hours,
        max_uses=req.max_uses,
    )


@app.get("/agents/dynamic/active")
async def dynamic_agent_active(
    limit: int = 50,
    all_users: bool = False,
    user_id: str = Depends(get_user_id),
):
    """Agentes dinâmicos ativos (não expirados, não dissolvidos)."""
    scope = None if all_users else user_id
    rows = await _dyn_catalog.list_active(user_id=scope, limit=limit)
    return {"agents": rows, "total": len(rows)}


@app.get("/agents/dynamic/{agent_id}")
async def dynamic_agent_get(agent_id: str, user_id: str = Depends(get_user_id)):
    row = await _dyn_catalog.get(agent_id)
    if not row:
        raise HTTPException(404, f"dynamic agent '{agent_id}' not found")
    return row


@app.post("/agents/dynamic/{agent_id}/dissolve")
async def dynamic_agent_dissolve(
    agent_id: str, reason: str = "manual", user_id: str = Depends(get_user_id)
):
    return await _dyn_catalog.dissolve(agent_id, reason=reason)


@app.post("/agents/dynamic/dissolve-expired")
async def dynamic_agent_bulk_dissolve(user_id: str = Depends(get_user_id)):
    """Dissolve em massa os agentes que passaram do TTL. Cron-friendly."""
    return await _dyn_catalog.dissolve_expired()


# ═══════════════════════════════════════════════════════════════════════════
# Persona Lifecycle — eval, promote, deprecate, version snapshots
# ═══════════════════════════════════════════════════════════════════════════

from .lifecycle.personas import PersonaLifecycle

_persona_lifecycle = PersonaLifecycle()


class PersonaDeprecateRequest(BaseModel):
    reason: str
    supersedes_persona_slug: Optional[str] = None


@app.post("/personas/{slug}/eval")
async def persona_eval(
    slug: str,
    num_questions: Optional[int] = None,
    threshold: Optional[float] = None,
    create_baseline_if_missing: bool = True,
    user_id: str = Depends(get_user_id),
):
    """Roda eval na persona — gera (ou usa) baseline + judge Opus."""
    return await _persona_lifecycle.eval_persona(
        slug,
        num_questions=num_questions,
        threshold=threshold,
        create_baseline_if_missing=create_baseline_if_missing,
    )


@app.get("/personas/{slug}/eval/latest")
async def persona_eval_latest(slug: str, user_id: str = Depends(get_user_id)):
    """Último agent_eval_run pra essa persona."""
    run = await _persona_lifecycle.last_eval_run(slug)
    if not run:
        raise HTTPException(404, f"no eval runs for '{slug}'")
    return run


@app.post("/personas/{slug}/promote")
async def persona_promote(
    slug: str,
    threshold: float = 0.65,
    user_id: str = Depends(get_user_id),
):
    """Promove para lifecycle_stage='promoted' se último eval passou."""
    return await _persona_lifecycle.promote(slug, threshold=threshold)


@app.post("/personas/{slug}/deprecate")
async def persona_deprecate(
    slug: str,
    req: PersonaDeprecateRequest,
    user_id: str = Depends(get_user_id),
):
    """Marca persona como deprecada; opcionalmente registra quem a substitui."""
    return await _persona_lifecycle.deprecate(
        slug,
        reason=req.reason,
        supersedes_persona_slug=req.supersedes_persona_slug,
    )


@app.post("/personas/{slug}/snapshot")
async def persona_snapshot(slug: str, user_id: str = Depends(get_user_id)):
    """Snapshot do persona_md atual em persona_versions (audit trail)."""
    return await _persona_lifecycle.snapshot_version(slug)
