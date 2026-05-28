"""
Workforce OS — Group Orchestrator (LangGraph)
Grupo debate: multi-agent rounds with consensus building.

LangGraph flow:
  Init → Loop[Send[] agents parallel] → Consensus → Synthesize
"""

from typing import Optional, List, Dict, Any
import logging
import asyncio

from ..router.central import CentralRouter
from ..agents.catalog import AgentCatalog
from ..config import get_settings

log = logging.getLogger(__name__)


class GroupOrchestrator:
    """Orchestrates multi-agent group debates with rounds."""

    def __init__(self):
        self.settings = get_settings()
        self.catalog = AgentCatalog()
        self.router = CentralRouter()

    async def execute(
        self,
        topic: str,
        participant_slugs: Optional[List[str]] = None,
        max_rounds: int = 3,
    ) -> Dict[str, Any]:
        """Execute a group debate.

        Args:
            topic: Debate topic
            participant_slugs: Optional explicit participant selection
            max_rounds: Maximum debate rounds (default 3)

        Returns:
            Dict with turns, consensus, and divergences
        """
        # 1. Select participants
        if participant_slugs:
            agents = await self.router.route(topic, explicit_agents=participant_slugs)
        else:
            agents = await self.router.route(topic, top_k=5)

        if len(agents) < 2:
            return {"error": "Need at least 2 participants", "turns": [], "consensus": ""}

        log.info(f"Group: '{topic[:60]}...' → {len(agents)} participants, {max_rounds} rounds")

        # 2. Run rounds
        all_turns = []
        for round_num in range(1, max_rounds + 1):
            round_prompts = self._frame_round_prompts(topic, agents, round_num, all_turns)
            round_responses = await self._execute_agents(agents, round_prompts)

            for resp in round_responses:
                all_turns.append({
                    "round": round_num,
                    "agent": resp["agent"],
                    "name": resp.get("name", resp["agent"]),
                    "content": resp["content"],
                })

            # Check for consensus
            if self._consensus_reached(round_responses):
                log.info(f"Consensus reached at round {round_num}")
                break

        # 3. Extract consensus and divergences
        consensus = self._extract_consensus(all_turns)
        divergences = self._extract_divergences(all_turns)

        return {
            "topic": topic,
            "participants": [a["slug"] for a in agents],
            "rounds": max(1, max((t["round"] for t in all_turns), default=1)),
            "total_rounds": max(1, max((t["round"] for t in all_turns), default=1)),
            "turns": all_turns,
            "consensus": consensus,
            "divergences": divergences,
        }

    def _frame_round_prompts(
        self,
        topic: str,
        agents: List[Dict[str, Any]],
        round_num: int,
        previous_turns: List[Dict[str, Any]],
    ) -> Dict[str, str]:
        """Create round-specific prompts for each agent."""
        prompts = {}
        for agent in agents:
            slug = agent["slug"]
            name = agent.get("name", slug)

            if round_num == 1:
                prompts[slug] = (
                    f"TÓPICO EM DEBATE: \"{topic}\"\n\n"
                    f"Você é {name}. Dê sua opinião inicial em 2 parágrafos.\n"
                    f"Seja claro sobre sua posição e os principais argumentos."
                )
            else:
                # Include previous turns for context
                prev_summary = "\n".join(
                    f"[Round {t['round']}] {t['name']}: {t['content'][:200]}..."
                    for t in previous_turns[-4:]  # Last 4 turns
                )
                prompts[slug] = (
                    f"TÓPICO EM DEBATE: \"{topic}\"\n\n"
                    f"ROUND {round_num}. Você é {name}.\n\n"
                    f"DEBATE ATÉ AGORA:\n{prev_summary}\n\n"
                    f"Responda ao que foi dito pelos outros participantes.\n"
                    f"Se concordar com alguém, diga 'concordo com [nome]'.\n"
                    f"Se discordar, diga 'discordo de [nome]' e explique por quê."
                )

        return prompts

    async def _execute_agents(
        self,
        agents: List[Dict[str, Any]],
        prompts: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """Execute agents in parallel for one round."""
        async def call_one(agent: Dict[str, Any]) -> Dict[str, Any]:
            slug = agent["slug"]
            name = agent.get("name", slug)
            prompt_text = prompts.get(slug, "")
            persona = agent.get("prompt") or await self.catalog.get_prompt(slug)

            try:
                response = await self._llm_call(persona, prompt_text)
                return {"agent": slug, "name": name, "content": response}
            except Exception as e:
                log.error(f"Group agent {slug} failed: {e}")
                return {"agent": slug, "name": name, "content": f"[Erro: {e}]"}

        tasks = [call_one(a) for a in agents]
        return await asyncio.gather(*tasks)

    async def _llm_call(self, system_prompt: str, user_message: str) -> str:
        """Call DeepSeek for agent response."""
        if not self.settings.deepseek_api_key:
            return "[LLM não configurado]"

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
                        "max_tokens": 800,
                    },
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[Erro LLM: {e}]"

    def _consensus_reached(self, responses: List[Dict[str, Any]]) -> bool:
        """Check if consensus has been reached (simple heuristic)."""
        agree_count = 0
        for r in responses:
            content = r.get("content", "").lower()
            if "concordo" in content and "discordo" not in content:
                agree_count += 1

        return agree_count >= len(responses) * 0.6 and agree_count >= 2

    def _extract_consensus(self, turns: List[Dict[str, Any]]) -> str:
        """Extract consensus from final round turns."""
        latest_round = max((t["round"] for t in turns), default=0)
        final_turns = [t for t in turns if t["round"] == latest_round]

        agree_count = sum(
            1 for t in final_turns
            if "concordo" in t.get("content", "").lower()
        )

        if agree_count >= len(final_turns) * 0.6:
            return (
                f"Consenso alcançado após {latest_round} round(s). "
                f"{agree_count}/{len(final_turns)} participantes convergiram."
            )
        return f"Sem consenso claro após {latest_round} round(s). Veja as posições divergentes abaixo."

    def _extract_divergences(self, turns: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Extract points of divergence from debate turns."""
        divergences = []
        for t in turns:
            content = t.get("content", "")
            if "discordo" in content.lower():
                divergences.append({
                    "agent": t.get("name", t["agent"]),
                    "point": content[:200],
                })
        return divergences[:5]  # Max 5 divergences
