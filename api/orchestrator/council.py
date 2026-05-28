"""
Workforce OS — Council Orchestrator (LangGraph)
Conselho 1:1: CEO pergunta, sistema seleciona e orquestra especialistas.

LangGraph flow:
  Router → Framing → Send[] agents (parallel) → Aggregate → Check
"""

from typing import Optional, List, Dict, Any
import logging
import asyncio

from ..router.central import CentralRouter
from ..agents.catalog import AgentCatalog
from ..config import get_settings

log = logging.getLogger(__name__)


class CouncilOrchestrator:
    """Orchestrates a 1:1 council session with multiple specialists."""

    def __init__(self):
        self.settings = get_settings()
        self.catalog = AgentCatalog()
        self.router = CentralRouter()

    async def execute(
        self,
        question: str,
        context: Optional[str] = None,
        agent_slugs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute a council session.

        Args:
            question: CEO's question
            context: Optional business context
            agent_slugs: Optional explicit agent selection (skips routing)

        Returns:
            Dict with responses, synthesis, and metadata
        """
        # 1. Route: select best agents
        if agent_slugs:
            agents = await self.router.route(question, explicit_agents=agent_slugs)
        else:
            agents = await self.router.route(question, top_k=self.settings.max_agents_per_council)

        if not agents:
            return {"error": "No agents could be selected", "responses": [], "synthesis": ""}

        log.info(f"Council: '{question[:60]}...' → {len(agents)} agents")

        # 2. Frame prompts
        prompts = self._frame_prompts(question, context, agents)

        # 3. Execute agents in parallel (Send[] pattern)
        responses = await self._execute_agents(agents, prompts)

        # 4. Aggregate & synthesize
        synthesis = self._synthesize(question, responses)

        # 5. Persist to memory (fire-and-forget)
        asyncio.create_task(self._persist_to_memory(question, agents, responses, synthesis))

        return {
            "question": question,
            "agents_count": len(agents),
            "agents": [
                {"slug": a["slug"], "name": a.get("name", a["slug"]), "score": a.get("score", 0.5)}
                for a in agents
            ],
            "responses": responses,
            "synthesis": synthesis,
        }

    def _frame_prompts(
        self,
        question: str,
        context: Optional[str],
        agents: List[Dict[str, Any]],
    ) -> Dict[str, str]:
        """Create per-agent prompts for the council session."""
        prompts = {}
        for agent in agents:
            slug = agent["slug"]
            name = agent.get("name", slug)
            context_block = f"\nCONTEXTO ADICIONAL:\n{context}\n" if context else ""

            prompts[slug] = (
                f"Você é {name}, um especialista em sua área.\n\n"
                f"O CEO da empresa tem a seguinte pergunta:\n\n"
                f"\"{question}\"\n"
                f"{context_block}\n"
                f"INSTRUÇÕES:\n"
                f"1. Responda em 2-3 parágrafos, sendo direto e acionável.\n"
                f"2. Se houver riscos, mencione-os explicitamente.\n"
                f"3. Se discordar da premissa da pergunta, diga por quê.\n"
                f"4. Recomende um próximo passo concreto se possível.\n"
            )

        return prompts

    async def _execute_agents(
        self,
        agents: List[Dict[str, Any]],
        prompts: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """Execute all agents in parallel (Send[] pattern)."""
        async def call_one(agent: Dict[str, Any]) -> Dict[str, Any]:
            slug = agent["slug"]
            name = agent.get("name", slug)
            prompt_text = prompts.get(slug, "")
            persona = agent.get("prompt") or await self.catalog.get_prompt(slug)

            try:
                response = await self._llm_call(persona, prompt_text)
                return {
                    "agent": slug,
                    "name": name,
                    "content": response,
                    "source": f"Persona: {slug}",
                }
            except Exception as e:
                log.error(f"Agent {slug} failed: {e}")
                return {
                    "agent": slug,
                    "name": name,
                    "content": f"[Erro ao consultar {name}: {e}]",
                    "source": "error",
                }

        tasks = [call_one(a) for a in agents]
        return await asyncio.gather(*tasks)

    async def _llm_call(self, system_prompt: str, user_message: str) -> str:
        """Call DeepSeek V4 Pro for agent response."""
        if not self.settings.deepseek_api_key:
            return "[LLM não configurado — resposta stub]"

        import httpx
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                resp = await client.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": (system_prompt or "")[:3000]},
                            {"role": "user", "content": user_message[:6000]},
                        ],
                        "temperature": 0.7,
                        "max_tokens": 1000,
                    },
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[Erro LLM: {e}]"

    def _synthesize(
        self,
        question: str,
        responses: List[Dict[str, Any]],
    ) -> str:
        """Create a quick synthesis from agent responses."""
        valid = [r for r in responses if "error" not in r.get("content", "").lower()[:20]]
        if not valid:
            return "Não foi possível obter análise dos especialistas."

        names = [r.get("name", r["agent"]) for r in valid]
        return (
            f"Conselho reunido para: \"{question}\"\n\n"
            f"**{len(valid)} especialistas consultados:** {', '.join(names)}\n\n"
            f"Cada especialista forneceu sua perspectiva. "
            f"Veja as análises individuais abaixo para tomar sua decisão."
        )

    async def _persist_to_memory(
        self,
        question: str,
        agents: List[Dict[str, Any]],
        responses: List[Dict[str, Any]],
        synthesis: str,
    ) -> None:
        """Fire-and-forget: persist council session to memory."""
        try:
            from ..memory.pipeline import MemoryPipeline
            pipeline = MemoryPipeline()
            session_content = json.dumps({
                "question": question,
                "agents": [a["slug"] for a in agents],
                "responses": [
                    {"agent": r["agent"], "content": r["content"][:500]}
                    for r in responses
                ],
                "synthesis": synthesis,
            })
            await pipeline.observe(
                user_id="anonymous",
                session_type="council",
                topic=question[:200],
                agents=[a["slug"] for a in agents],
                raw_output={"summary": synthesis},
            )
        except Exception as e:
            log.warning(f"Memory persist failed (non-fatal): {e}")


# For backwards compat
import json
