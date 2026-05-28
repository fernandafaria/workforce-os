"""
Workforce OS — LangGraph Orchestrator
Stateful agent orchestration for Council, Group, and Ping.

Architecture:
  Council: router → framing → Send[] agents (parallel) → aggregate → format
  Group:   init → loop[Send[] rounds] → consensus → synthesize
  Ping:    fetch vertical KB → generate briefing → format
"""

from typing import List, Dict, Any, Optional, TypedDict, Annotated
import operator
import logging
import asyncio

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.memory import MemorySaver

from ..agents.catalog import AgentCatalog
from ..config import get_settings

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# State Schemas
# ═══════════════════════════════════════════════════════════════════════════

class CouncilState(TypedDict):
    question: str
    context: Optional[str]
    agents: List[Dict[str, Any]]
    twins: List[Dict[str, Any]]
    framed_prompts: List[Dict[str, str]]
    responses: Annotated[List[Dict[str, Any]], operator.add]
    synthesis: str
    error: Optional[str]


class GroupState(TypedDict):
    topic: str
    participants: List[Dict[str, Any]]
    max_rounds: int
    round: int
    discussion: Annotated[List[Dict[str, Any]], operator.add]
    consensus_detected: bool
    consensus: str
    divergences: List[Dict[str, str]]
    turns: List[Dict[str, Any]]
    error: Optional[str]


class PingState(TypedDict):
    sector: Optional[str]
    user_id: Optional[str]
    market: List[str]
    sector_news: List[str]
    alerts: List[str]
    briefing: str
    error: Optional[str]


# ═══════════════════════════════════════════════════════════════════════════
# LLM Call Helper
# ═══════════════════════════════════════════════════════════════════════════

async def _call_llm(
    system_prompt: str, user_message: str, model: Optional[str] = None
) -> str:
    """Call DeepSeek or Anthropic depending on the model id.

    Model id can be a persona's ``model_ref`` (set in PR #6) — orchestrators
    use ``claude-opus-4-7``, specialists use ``deepseek-chat`` — or a twin's
    ``TWIN_MODEL_REF``. We pick the provider from the id, not from a fragile
    fallback chain.
    """
    settings = get_settings()
    model = model or settings.primary_model
    is_anthropic = model.startswith("claude")

    api_key = settings.anthropic_api_key if is_anthropic else settings.deepseek_api_key
    if not api_key:
        # Fall back to the other provider if the preferred one isn't configured
        if is_anthropic and settings.deepseek_api_key:
            is_anthropic = False
            model = "deepseek-chat"
            api_key = settings.deepseek_api_key
        elif (not is_anthropic) and settings.anthropic_api_key:
            is_anthropic = True
            model = "claude-opus-4-7"
            api_key = settings.anthropic_api_key
        else:
            return "[API key not configured]"

    try:
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            if is_anthropic:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": model,
                        "max_tokens": 1024,
                        "system": system_prompt,
                        "messages": [{"role": "user", "content": user_message}],
                    },
                )
                data = resp.json()
                return data["content"][0]["text"]
            else:
                resp = await client.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                        "temperature": 0.7,
                    },
                )
                data = resp.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        log.error(f"LLM call failed: {e}")
        return f"[Erro ao consultar participante: {e}]"


# ═══════════════════════════════════════════════════════════════════════════
# Council Orchestrator (Conselho 1:1)
# ═══════════════════════════════════════════════════════════════════════════

class CouncilOrchestrator:
    """Orchestrates a 1:1 council session with parallel agent execution."""
    
    def __init__(self):
        self.catalog = AgentCatalog()
        self.graph = self._build_graph()
    
    def _build_graph(self) -> CompiledStateGraph:
        builder = StateGraph(CouncilState)
        
        async def framing(state: CouncilState) -> dict:
            """Prepare prompts for each participant — personas + twins.

            Personas use their persona_md as the system prompt; twins use
            the cognitive schema synthesized in Stage 3. Each participant
            carries its preferred model_ref so execute_agents can route
            to the right provider per call.
            """
            framed = []
            question = state["question"]
            context = state.get("context", "")

            user_msg = (
                f'PERGUNTA DO EXECUTIVO:\n\n"{question}"\n\n'
                f'CONTEXTO ADICIONAL:\n{context or "Nenhum contexto adicional."}\n\n'
                f"INSTRUÇÃO: Dê sua recomendação em 2-3 parágrafos, considerando "
                f"sua especialidade. Seja direto, acionável e honesto. Se houver "
                f"riscos, mencione-os explicitamente."
            )

            # Personas
            for agent in state.get("agents", []):
                prompt = agent.get("prompt") or ""
                if not prompt:
                    prompt = (await self.catalog.get_prompt(agent["slug"])) or ""

                framed.append({
                    "participant_id": agent["slug"],
                    "name": agent.get("name", agent["slug"]),
                    "kind": "persona",
                    "system_prompt": prompt,
                    "user_message": user_msg,
                    "model": agent.get("model_ref"),
                    "source": agent.get("source") or f"Persona: {agent['slug']}",
                })

            # Twins — already carry their system_prompt + model_ref from
            # TwinCatalog.load_for_council
            for twin in state.get("twins", []):
                framed.append({
                    "participant_id": twin["twin_id"],
                    "name": twin.get("name", "Twin"),
                    "kind": "twin",
                    "system_prompt": twin["system_prompt"],
                    "user_message": user_msg,
                    "model": twin.get("model_ref"),
                    "source": twin.get("source") or f"Cognitive twin: {twin['twin_id']}",
                })

            return {"framed_prompts": framed}

        async def execute_agents(state: CouncilState) -> dict:
            """Execute all participants in parallel (Send pattern)."""
            prompts = state.get("framed_prompts", [])

            async def call_one(p):
                content = await _call_llm(
                    p["system_prompt"], p["user_message"], model=p.get("model")
                )
                return {
                    "agent": p["participant_id"],
                    "name": p["name"],
                    "kind": p.get("kind", "persona"),
                    "model": p.get("model"),
                    "source": p.get("source"),
                    "content": content,
                }

            results = await asyncio.gather(*[call_one(p) for p in prompts])
            return {"responses": results}
        
        async def synthesize(state: CouncilState) -> dict:
            """Generate executive summary."""
            responses = state.get("responses", [])
            if not responses:
                return {"synthesis": "Não foi possível gerar recomendações."}
            
            summary_prompt = "Você é um sintetizador executivo. Dado as perspectivas abaixo, gere um sumário de 2-3 frases que capture a recomendação principal."
            perspectives_text = "\n\n".join(
                f"[{r['name']}]: {r['content'][:500]}" for r in responses
            )
            
            synthesis = await _call_llm(summary_prompt, perspectives_text)
            return {"synthesis": synthesis}
        
        builder.add_node("framing", framing)
        builder.add_node("execute", execute_agents)
        builder.add_node("synthesize", synthesize)
        
        builder.set_entry_point("framing")
        builder.add_edge("framing", "execute")
        builder.add_edge("execute", "synthesize")
        builder.add_edge("synthesize", END)
        
        return builder.compile(checkpointer=MemorySaver())
    
    async def execute(
        self,
        question: str,
        context: Optional[str] = None,
        agent_slugs: List[str] = None,
        user_id: Optional[str] = None,
        twin_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run a council session with personas and optional cognitive twins.

        If user_id is provided, recent distilled memories for this executive
        are injected into the context so the council is not amnesic across
        sessions.

        If twin_ids is provided, each consultable twin (status in
        eval_passed/production) is loaded as a participant alongside the
        routed personas. Drafts/unsynthesized twins are silently skipped.
        """
        from ..router.central import CentralRouter
        from ..memory.pipeline import MemoryPipeline
        from ..twins.catalog import TwinCatalog

        # 1. Route to agents (skip if caller passed only twins)
        agents = []
        if not (agent_slugs == [] and twin_ids):
            router = CentralRouter()
            agents = await router.route(question, agent_slugs)

        # 1b. Load twin participants
        twins: List[Dict[str, Any]] = []
        if twin_ids:
            twins = await TwinCatalog().load_for_council(twin_ids)

        # 2. Augment context with recent memories of this executive
        augmented_context = context or ""
        if user_id:
            try:
                pipeline = MemoryPipeline()
                memories = await pipeline.search(user_id, question, limit=5)
                if memories:
                    memory_block = "\n".join(
                        f"- [{m.get('memory_type','memory')}] "
                        f"{m.get('title') or m.get('content','')[:120]}"
                        for m in memories[:5]
                    )
                    augmented_context = (
                        (augmented_context + "\n\n" if augmented_context else "")
                        + "DECISÕES E OBSERVAÇÕES PASSADAS DESTE EXECUTIVO "
                        + "(considere ao responder, não repita):\n"
                        + memory_block
                    )
            except Exception as e:
                log.warning(f"Memory injection failed (non-fatal): {e}")

        # 3. Run LangGraph
        initial_state: CouncilState = {
            "question": question,
            "context": augmented_context,
            "agents": agents,
            "twins": twins,
            "framed_prompts": [],
            "responses": [],
            "synthesis": "",
            "error": None,
        }

        result = await self.graph.ainvoke(initial_state)

        # 4. Persist session for future memory injection (fire-and-forget)
        if user_id:
            asyncio.create_task(
                self._persist(user_id, question, agents, twins,
                              result.get("responses", []),
                              result.get("synthesis", ""))
            )

        return {
            "question": question,
            "agents": agents,
            "twins": [{"twin_id": t["twin_id"], "name": t["name"]} for t in twins],
            "responses": result.get("responses", []),
            "synthesis": result.get("synthesis", ""),
        }

    async def _persist(self, user_id: str, question: str,
                       agents: List[Dict[str, Any]],
                       twins: List[Dict[str, Any]],
                       responses: List[Dict[str, Any]],
                       synthesis: str) -> None:
        try:
            from ..memory.pipeline import MemoryPipeline
            pipeline = MemoryPipeline()
            participants = (
                [a["slug"] for a in agents] +
                [f"twin:{t['twin_id']}" for t in twins]
            )
            await pipeline.observe(
                user_id=user_id,
                session_type="council",
                topic=question[:200],
                agents=participants,
                raw_output={"summary": synthesis,
                            "responses": [{"agent": r["agent"],
                                           "kind": r.get("kind", "persona"),
                                           "content": (r.get("content") or "")[:500]}
                                          for r in responses]},
            )
        except Exception as e:
            log.warning(f"Council memory persist failed (non-fatal): {e}")


# ═══════════════════════════════════════════════════════════════════════════
# Group Orchestrator (Debate Multi-Agente)
# ═══════════════════════════════════════════════════════════════════════════

class GroupOrchestrator:
    """Orchestrates multi-agent group debate with rounds."""
    
    def __init__(self):
        self.catalog = AgentCatalog()
        self.graph = self._build_graph()
    
    def _build_graph(self) -> CompiledStateGraph:
        builder = StateGraph(GroupState)
        
        async def init_round(state: GroupState) -> dict:
            """Initialize or advance debate round."""
            current_round = state.get("round", 0) + 1
            
            # Check consensus from previous round
            if current_round > 1:
                discussion = state.get("discussion", [])
                recent = [d for d in discussion if d.get("round") == current_round - 1]
                agree_count = sum(1 for d in recent if "concordo" in d.get("content", "").lower())
                if agree_count >= len(recent) * 0.6:
                    return {"round": current_round, "consensus_detected": True}
            
            return {"round": current_round, "consensus_detected": False}
        
        async def debate_round(state: GroupState) -> dict:
            """Execute one round of parallel debate."""
            topic = state["topic"]
            participants = state.get("participants", [])
            round_num = state.get("round", 1)
            discussion = state.get("discussion", [])
            is_first = round_num == 1
            
            # Build debate context
            context = ""
            if not is_first:
                recent = [d for d in discussion if d.get("round") == round_num - 1]
                context = "\n".join(
                    f"[{d['name']}]: {d['content'][:300]}" for d in recent
                )
            
            async def call_participant(p):
                prompt = p.get("prompt", "")
                if not prompt:
                    prompt = await self.catalog.get_prompt(p["slug"]) or ""
                
                if is_first:
                    msg = f'TÓPICO EM DEBATE: "{topic}"\n\nDê sua opinião inicial. 2 parágrafos.'
                else:
                    msg = f'TÓPICO: "{topic}"\n\nRODADA ANTERIOR:\n{context}\n\nResponda ao que foi dito. Se concordar com alguém, diga "concordo com [nome]". Se discordar, diga "discordo de [nome]".'
                
                content = await _call_llm(prompt, msg)
                return {
                    "agent": p["slug"],
                    "name": p.get("name", p["slug"]),
                    "round": round_num,
                    "content": content,
                }
            
            results = await asyncio.gather(*[call_participant(p) for p in participants])
            
            return {
                "discussion": results,
                "turns": results,
            }
        
        async def synthesize_group(state: GroupState) -> dict:
            """Synthesize group consensus."""
            discussion = state.get("discussion", [])
            
            all_content = "\n\n".join(
                f"[{d['name']} (Round {d.get('round', '?')})]: {d['content'][:400]}"
                for d in discussion
            )
            
            consensus = await _call_llm(
                "Sintetize o consenso deste debate em 2-3 frases. Destaque pontos de acordo e divergências.",
                all_content,
            )
            
            return {"consensus": consensus}
        
        builder.add_node("init", init_round)
        builder.add_node("debate", debate_round)
        builder.add_node("synthesize", synthesize_group)
        
        builder.set_entry_point("init")
        
        # Conditional edge: loop until consensus or max rounds
        def should_continue(state: GroupState) -> str:
            if state.get("consensus_detected"):
                return "synthesize"
            if state.get("round", 0) >= state.get("max_rounds", 5):
                return "synthesize"
            return "debate"
        
        builder.add_conditional_edges("init", should_continue, {
            "debate": "debate",
            "synthesize": "synthesize",
        })
        builder.add_conditional_edges("debate", should_continue, {
            "debate": "debate",
            "synthesize": "synthesize",
        })
        builder.add_edge("synthesize", END)
        
        return builder.compile(checkpointer=MemorySaver())
    
    async def execute(
        self,
        topic: str,
        participant_slugs: List[str] = None,
        max_rounds: int = 5,
    ) -> Dict[str, Any]:
        """Run a group debate."""
        from ..router.central import CentralRouter
        
        # Default participants if none specified
        if not participant_slugs:
            participant_slugs = ["simon-willison", "roger-martin", "elena-verna", 
                                 "andrej-karpathy", "claire-hughes-johnson"]
        
        # Load participant prompts
        catalog = AgentCatalog()
        participants = []
        for slug in participant_slugs:
            prompt = await catalog.get_prompt(slug)
            participants.append({
                "slug": slug,
                "name": slug.replace("-", " ").title(),
                "prompt": prompt,
            })
        
        initial_state: GroupState = {
            "topic": topic,
            "participants": participants,
            "max_rounds": max_rounds,
            "round": 0,
            "discussion": [],
            "consensus_detected": False,
            "consensus": "",
            "divergences": [],
            "turns": [],
            "error": None,
        }
        
        result = await self.graph.ainvoke(initial_state)
        
        return {
            "topic": topic,
            "turns": result.get("turns", []),
            "discussion": result.get("discussion", []),
            "consensus": result.get("consensus", ""),
            "rounds": result.get("round", 0),
            "divergences": result.get("divergences", []),
        }


# ═══════════════════════════════════════════════════════════════════════════
# Ping Orchestrator (Daily Briefing)
# ═══════════════════════════════════════════════════════════════════════════

class PingOrchestrator:
    """Generates daily executive briefings."""
    
    async def execute(
        self,
        sector: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a morning briefing."""
        sector = sector or "Geral"
        
        briefing_prompt = f"""Você é um analista executivo gerando um briefing matinal para o setor: {sector}.

Gere 3 seções:
1. MERCADO (3 itens): movimentos macro que afetam o setor hoje
2. SEU SETOR (3 itens): notícias específicas do setor
3. ALERTA (1-2 itens): riscos ou oportunidades iminentes

Formato: cada item em uma linha, começando com "•". Seja conciso e acionável."""

        response = await _call_llm(briefing_prompt, f"Setor: {sector}")
        
        # Parse response into sections
        lines = response.split("\n")
        market = []
        sector_news = []
        alerts = []
        current = None
        
        for line in lines:
            line = line.strip()
            if "MERCADO" in line.upper():
                current = "market"
            elif "SETOR" in line.upper():
                current = "sector"
            elif "ALERTA" in line.upper():
                current = "alert"
            elif line.startswith("•") and current:
                item = line.replace("•", "").strip()
                if current == "market":
                    market.append(item)
                elif current == "sector":
                    sector_news.append(item)
                elif current == "alert":
                    alerts.append(item)
        
        return {
            "sector": sector,
            "market": market or ["Dados de mercado indisponíveis"],
            "sector_news": sector_news or ["Notícias do setor indisponíveis"],
            "alerts": alerts or ["Nenhum alerta crítico hoje"],
        }
