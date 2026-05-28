"""
Workforce OS — Ritual Runner
Wraps Febrain protocols as LangGraph graphs.
Each protocol SKILL.md defines the interaction pattern.
"""

import os
import yaml
from typing import Dict, Any, List
from pathlib import Path

FEBRAIN_PROTOCOLS = Path(os.path.expanduser("~/code/Febrain/_shared/protocols"))

PROTOCOL_PATTERNS = {
    "war-room": "parallel_fanout",
    "sparring": "thesis_antithesis_synthesis", 
    "board-review": "present_review_revise",
    "pre-mortem": "parallel_pessimistic",
    "deal-review": "multi_agent_gonogo",
    "deep-dive": "single_agent_analysis",
    "retro": "parallel_reflection",
    "standup": "parallel_status",
    "qbr": "parallel_synthesis",
}


class RitualRunner:
    """Executes Febrain protocols as LangGraph graphs."""
    
    def __init__(self):
        self.protocols = self._discover_protocols()
    
    def _discover_protocols(self) -> Dict[str, Path]:
        """Find all protocol SKILL.md files."""
        protocols = {}
        if not FEBRAIN_PROTOCOLS.exists():
            return protocols
        
        for d in FEBRAIN_PROTOCOLS.iterdir():
            if d.is_dir():
                skill_md = d / "SKILL.md"
                if skill_md.exists():
                    protocols[d.name] = skill_md
        
        return protocols
    
    def list_protocols(self) -> List[Dict[str, str]]:
        """List all available protocols."""
        return [
            {
                "id": name,
                "pattern": PROTOCOL_PATTERNS.get(name, "unknown"),
                "path": str(path.relative_to(FEBRAIN_PROTOCOLS.parent.parent)),
            }
            for name, path in self.protocols.items()
        ]
    
    async def execute(self, protocol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a protocol.
        
        Args:
            protocol: Protocol name (war-room, sparring, board-review, etc.)
            context: {topic, agents, user_id, ...}
        """
        if protocol not in self.protocols:
            return {"error": f"Protocol '{protocol}' not found. Available: {list(self.protocols.keys())}"}
        
        skill_path = self.protocols[protocol]
        pattern = PROTOCOL_PATTERNS.get(protocol, "unknown")
        
        # Read the SKILL.md to understand the protocol
        skill_content = skill_path.read_text()
        
        # Dispatch to appropriate graph builder
        if pattern == "parallel_fanout":
            return await self._execute_war_room(context, skill_content)
        elif pattern == "thesis_antithesis_synthesis":
            return await self._execute_sparring(context, skill_content)
        elif pattern == "present_review_revise":
            return await self._execute_board_review(context, skill_content)
        elif pattern == "parallel_pessimistic":
            return await self._execute_pre_mortem(context, skill_content)
        elif pattern == "multi_agent_gonogo":
            return await self._execute_deal_review(context, skill_content)
        else:
            return await self._execute_generic(protocol, context, skill_content)
    
    async def _execute_war_room(self, ctx: dict, skill: str) -> dict:
        """Parallel Fan-Out/Gather + Generator-Critic."""
        from ..orchestrator import GroupOrchestrator
        
        orch = GroupOrchestrator()
        return await orch.execute(
            topic=ctx.get("topic", ""),
            participant_slugs=ctx.get("agents"),
            max_rounds=ctx.get("max_rounds", 3),
        )
    
    async def _execute_sparring(self, ctx: dict, skill: str) -> dict:
        """Thesis → Antithesis → Synthesis with arbitrator."""
        topic = ctx.get("topic", "")
        agents = ctx.get("agents", [])[:2]  # Exactly 2 debaters
        
        from ..agents.catalog import AgentCatalog
        from ..orchestrator import _call_llm
        
        catalog = AgentCatalog()
        
        # Load both debaters
        debaters = []
        for slug in agents:
            prompt = await catalog.get_prompt(slug)
            debaters.append({"slug": slug, "prompt": prompt})
        
        if len(debaters) < 2:
            return {"error": "Sparring requires exactly 2 agents"}
        
        # Thesis
        thesis = await _call_llm(
            debaters[0]["prompt"] or "",
            f"TESE: Defenda esta posição sobre '{topic}'. Seja persuasivo."
        )
        
        # Antithesis
        antithesis = await _call_llm(
            debaters[1]["prompt"] or "",
            f"ANTÍTESE: Discorde da seguinte tese sobre '{topic}':\n{thesis}\n\nSeja rigoroso."
        )
        
        # Synthesis (arbitrator)
        synthesis = await _call_llm(
            "Você é um árbitro executivo. Sintetize o debate em uma recomendação final.",
            f"TÓPICO: {topic}\n\nTESE:\n{thesis}\n\nANTÍTESE:\n{antithesis}\n\nSÍNTESE:"
        )
        
        return {
            "protocol": "sparring",
            "topic": topic,
            "thesis": thesis,
            "antithesis": antithesis,
            "synthesis": synthesis,
        }
    
    async def _execute_board_review(self, ctx: dict, skill: str) -> dict:
        """Exec presents → Board reviews → Revised output."""
        topic = ctx.get("topic", "")
        agents = ctx.get("agents", [])[:4]
        
        from ..orchestrator import CouncilOrchestrator
        
        orch = CouncilOrchestrator()
        result = await orch.execute(
            question=f"BOARD REVIEW: {topic}",
            context=ctx.get("context", ""),
            agent_slugs=agents,
        )
        
        result["protocol"] = "board-review"
        return result
    
    async def _execute_pre_mortem(self, ctx: dict, skill: str) -> dict:
        """Parallel pessimistic analysis → Risk map."""
        topic = ctx.get("topic", "")
        agents = ctx.get("agents", [])[:5]
        
        from ..orchestrator import CouncilOrchestrator
        
        orch = CouncilOrchestrator()
        result = await orch.execute(
            question=f"PRE-MORTEM: Estamos em 2027 e '{topic}' fracassou. Por quê?",
            agent_slugs=agents,
        )
        
        result["protocol"] = "pre-mortem"
        return result
    
    async def _execute_deal_review(self, ctx: dict, skill: str) -> dict:
        """Multi-agent assessment → Go/No-Go."""
        topic = ctx.get("topic", "")
        agents = ctx.get("agents", [])[:5]
        
        from ..orchestrator import CouncilOrchestrator
        
        orch = CouncilOrchestrator()
        result = await orch.execute(
            question=f"DEAL REVIEW: {topic} — Go or No-Go?",
            agent_slugs=agents,
        )
        
        result["protocol"] = "deal-review"
        return result
    
    async def _execute_generic(self, protocol: str, ctx: dict, skill: str) -> dict:
        """Generic execution for unknown patterns."""
        from ..orchestrator import CouncilOrchestrator
        
        orch = CouncilOrchestrator()
        return await orch.execute(
            question=ctx.get("topic", ""),
            agent_slugs=ctx.get("agents"),
        )


# Singleton
_runner = None

def get_ritual_runner() -> 'RitualOrchestrator':
    global _runner
    if not _runner:
        _runner = RitualOrchestrator()
    return _runner


class RitualOrchestrator:
    """Public API matching main.py expectations."""
    
    def __init__(self):
        self._runner = RitualRunner()
    
    def list_rituals(self) -> list:
        return self._runner.list_protocols()
    
    def get_protocol(self, slug: str) -> str | None:
        if slug not in self._runner.protocols:
            return None
        return self._runner.protocols[slug].read_text()
    
    async def run_ritual(self, slug: str, topic: str, context: str = None, agents: list = None):
        return await self._runner.execute(slug, {
            "topic": topic,
            "context": context,
            "agents": agents,
        })
