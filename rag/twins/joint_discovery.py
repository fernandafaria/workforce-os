"""
joint_discovery — Aspasia + Iza paired interview on a twin.

Runs agent-vs-agent interview (`interview_archetype`), then:
  • Aspasia: discovery brief (themes, contradictions, JTBD, evidence tier)
  • Iza: surface/restraint pass (UI implications, two-product smell)
  • Iza (optional): multimodal critique when `artifact_paths` are images

Callable from CLI, POST /api/twins/joint-discovery, and MCP `run_joint_discovery`.

Usage:
    python -m rag.twins.joint_discovery arch-mkt-orquestrador-insights \\
        --research-goal "Quando synthetic research entra vs campo" \\
        --mock
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rag.skills_loader import invoke_skill, load_skill
from rag.twins import storage
from rag.twins.interview_archetype import interview, resolve_twin_id
from rag.twins.interview_profile import InterviewProfile, detect_interview_profile, load_person_spec

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


@dataclass
class AspasiaPhaseResult:
    session_id: str
    twin_id: str
    person_id: str
    interview_profile: str
    research_goal: str
    transcript_md: str
    aspasia_brief_md: str
    evidence_tier: str = "exploratory"
    limitations: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IzaPhaseResult:
    iza_surface_md: str
    iza_multimodal_md: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class JointDiscoveryResult:
    session_id: str
    twin_id: str
    person_id: str
    interview_profile: str
    research_goal: str
    transcript_md: str
    aspasia_brief_md: str
    iza_surface_md: str
    iza_multimodal_md: str | None = None
    evidence_tier: str = "exploratory"
    limitations: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def merge(cls, aspasia: AspasiaPhaseResult, iza: IzaPhaseResult) -> JointDiscoveryResult:
        meta = {**aspasia.metadata, **iza.metadata}
        return cls(
            session_id=aspasia.session_id,
            twin_id=aspasia.twin_id,
            person_id=aspasia.person_id,
            interview_profile=aspasia.interview_profile,
            research_goal=aspasia.research_goal,
            transcript_md=aspasia.transcript_md,
            aspasia_brief_md=aspasia.aspasia_brief_md,
            iza_surface_md=iza.iza_surface_md,
            iza_multimodal_md=iza.iza_multimodal_md,
            evidence_tier=aspasia.evidence_tier,
            limitations=aspasia.limitations,
            metadata=meta,
        )


def _format_transcript(session_id: str, *, db_path: Path | None) -> str:
    turns = storage.transcript(session_id, db_path=db_path)
    lines: list[str] = [f"# Transcript `{session_id}`\n"]
    for row in turns:
        speaker = row.get("speaker", "?")
        content = (row.get("content") or "").strip()
        label = "Entrevistador" if speaker == "interviewer" else "Entrevistado"
        lines.append(f"**{label}:** {content}\n")
    return "\n".join(lines)


def _evidence_tier_for_goal(research_goal: str, profile: InterviewProfile) -> tuple[str, list[str]]:
    """Map research goal to synthetic evidence tier + honest limitations."""
    goal_l = research_goal.lower()
    limitations: list[str] = [
        "Entrevista sintética ≠ campo — triangule com design partners ou pesquisa real antes de decisão de alto custo.",
    ]
    if any(w in goal_l for w in ("wtp", "willingness", "preço", "pricing", "budget", "orçamento")):
        return (
            "directional_only",
            limitations
            + [
                "WTP e orçamento exigem campo ou experimento — output sintético é sinal direcional apenas.",
            ],
        )
    if any(w in goal_l for w in ("launch", "go-live", "comprar", "contrato", "procurement")):
        return (
            "directional_only",
            limitations
            + [
                "Decisão de compra/launch não pode repousar só neste brief.",
            ],
        )
    if profile is InterviewProfile.BUYER_PROFESSIONAL:
        limitations.append(
            "Corpus dev-seed usa notas do YAML — FULL build no DO runner aumenta profundidade."
        )
    return "exploratory", limitations


def _aspasia_brief(
    client,
    *,
    transcript_md: str,
    research_goal: str,
    person_id: str,
    evidence_tier: str,
    limitations: list[str],
    model: str,
) -> str:
    skill = load_skill("aspasia/joint-discovery")
    user_input = dedent(
        f"""
        ## Objetivo de pesquisa
        {research_goal}

        ## Twin / entrevistado
        person_id: {person_id}

        ## Tier de evidência permitido para recomendações
        {evidence_tier}

        ## Limitações explícitas (não suavizar — repetir no brief)
        {chr(10).join(f"- {x}" for x in limitations)}

        ## Transcript
        {transcript_md}

        Produza o discovery brief no formato da skill. Português. Markdown.
        """
    ).strip()
    return invoke_skill(client, skill, user_input, model=model, max_tokens=4096)


def _iza_surface(
    client,
    *,
    transcript_md: str,
    aspasia_brief_md: str,
    research_goal: str,
    model: str,
) -> str:
    skill = load_skill("iza/joint-discovery")
    user_input = dedent(
        f"""
        ## Objetivo
        {research_goal}

        ## Brief Aspasia (negócio)
        {aspasia_brief_md}

        ## Transcript (trechos de produto/UX)
        {transcript_md}

        Observação Iza: implicações de superfície, mode picker (Insights vs Lab),
        feature creep, "dois produtos". Não redesenhar telas — restraint + intent.
        Português. Markdown.
        """
    ).strip()
    return invoke_skill(client, skill, user_input, model=model, max_tokens=3072)


def _read_image_block(path: Path) -> dict | None:
    if path.suffix.lower() not in _IMAGE_SUFFIXES:
        return None
    if not path.is_file():
        log.warning("artifact not found: %s", path)
        return None
    media = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    if path.suffix.lower() == ".webp":
        media = "image/webp"
    if path.suffix.lower() == ".gif":
        media = "image/gif"
    data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media, "data": data},
    }


def _iza_multimodal(
    client,
    *,
    artifact_paths: list[Path],
    aspasia_brief_md: str,
    iza_surface_md: str,
    model: str,
) -> str | None:
    """Optional vision pass — product/UX tone in static UI, not video emotion."""
    images = []
    for p in artifact_paths:
        block = _read_image_block(p.resolve())
        if block:
            images.append(block)
    if not images:
        return None

    skill = load_skill("iza/taste-judge")
    system = skill.prompt_md or skill.skill_md
    user_content: list[dict] = [
        {
            "type": "text",
            "text": dedent(
                f"""
                Contexto da entrevista sintética (não julgue o transcript como UI):

                ## Brief Aspasia
                {aspasia_brief_md[:6000]}

                ## Observações Iza (superfície)
                {iza_surface_md[:4000]}

                Julgue os anexos: o participante descreveria isto como um workspace
                ou dois produtos? 3 cortes cirúrgicos. Veredito PROUD | WORK_TO_DO |
                SHOULDNT_SHIP. Profundidade = produto/UX, não tom em vídeo.
                """
            ).strip(),
        },
        *images,
    ]
    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return "\n\n".join(parts).strip()


def _anthropic_client():
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError("anthropic SDK required — use --mock offline") from e
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=key)


def run_interview_and_aspasia(
    slug_or_id: str,
    *,
    research_goal: str,
    opener: str | None = None,
    turns: int = 8,
    mock: bool = False,
    db_path: Path | None = None,
    model: str = DEFAULT_MODEL,
    session_id: str | None = None,
) -> AspasiaPhaseResult:
    """Phase 1: synthetic interview + Aspasia discovery brief."""
    twin_id = resolve_twin_id(slug_or_id, db_path=db_path, auto_seed=True)
    twin = storage.get_twin(twin_id, db_path=db_path)
    if not twin:
        raise SystemExit(f"twin missing after resolve: {twin_id}")
    person_id = twin.get("person_id") or slug_or_id
    spec = load_person_spec(person_id)
    profile = detect_interview_profile(person_id, spec=spec)
    evidence_tier, limitations = _evidence_tier_for_goal(research_goal, profile)

    sid = interview(
        slug_or_id,
        research_goal=research_goal,
        opener=opener,
        turns=turns,
        session_id=session_id,
        mock=mock,
        db_path=db_path,
        auto_seed=True,
    )
    transcript_md = _format_transcript(sid, db_path=db_path)

    if mock:
        aspasia_brief_md = (
            "[mock] Discovery brief — rode sem --mock com ANTHROPIC_API_KEY "
            "para invocar aspasia/joint-discovery."
        )
    else:
        client = _anthropic_client()
        aspasia_brief_md = _aspasia_brief(
            client,
            transcript_md=transcript_md,
            research_goal=research_goal,
            person_id=person_id,
            evidence_tier=evidence_tier,
            limitations=limitations,
            model=model,
        )

    return AspasiaPhaseResult(
        session_id=sid,
        twin_id=twin_id,
        person_id=person_id,
        interview_profile=profile.value,
        research_goal=research_goal,
        transcript_md=transcript_md,
        aspasia_brief_md=aspasia_brief_md,
        evidence_tier=evidence_tier,
        limitations=limitations,
        metadata={"mock": mock, "turns": turns, "phase": "aspasia"},
    )


def run_iza_pass(
    aspasia: AspasiaPhaseResult,
    *,
    mock: bool = False,
    db_path: Path | None = None,
    artifact_paths: list[Path] | None = None,
    model: str = DEFAULT_MODEL,
) -> IzaPhaseResult:
    """Phase 2: Iza surface (+ optional multimodal) on completed Aspasia output."""
    if mock:
        return IzaPhaseResult(
            iza_surface_md="[mock] Surface pass — iza/joint-discovery.",
            metadata={"mock": True, "phase": "iza"},
        )

    client = _anthropic_client()
    iza_surface_md = _iza_surface(
        client,
        transcript_md=aspasia.transcript_md,
        aspasia_brief_md=aspasia.aspasia_brief_md,
        research_goal=aspasia.research_goal,
        model=model,
    )
    iza_multimodal_md: str | None = None
    if artifact_paths:
        iza_multimodal_md = _iza_multimodal(
            client,
            artifact_paths=artifact_paths,
            aspasia_brief_md=aspasia.aspasia_brief_md,
            iza_surface_md=iza_surface_md,
            model=model,
        )
    return IzaPhaseResult(
        iza_surface_md=iza_surface_md,
        iza_multimodal_md=iza_multimodal_md,
        metadata={"mock": False, "phase": "iza"},
    )


def run_iza_pass_from_row(
    *,
    session_id: str,
    slug: str,
    research_goal: str,
    aspasia_brief_md: str,
    interview_profile: str,
    evidence_tier: str,
    limitations: list[str] | None = None,
    twin_id: str = "",
    person_id: str = "",
    mock: bool = False,
    db_path: Path | None = None,
    artifact_paths: list[Path] | None = None,
    model: str = DEFAULT_MODEL,
) -> IzaPhaseResult:
    """Phase 2 when Aspasia ran earlier — reload transcript from storage."""
    transcript_md = _format_transcript(session_id, db_path=db_path)
    aspasia = AspasiaPhaseResult(
        session_id=session_id,
        twin_id=twin_id,
        person_id=person_id or slug,
        interview_profile=interview_profile,
        research_goal=research_goal,
        transcript_md=transcript_md,
        aspasia_brief_md=aspasia_brief_md,
        evidence_tier=evidence_tier,
        limitations=limitations or [],
        metadata={"phase": "iza", "resumed": True},
    )
    return run_iza_pass(
        aspasia,
        mock=mock,
        db_path=db_path,
        artifact_paths=artifact_paths,
        model=model,
    )


def run_joint_discovery(
    slug_or_id: str,
    *,
    research_goal: str,
    opener: str | None = None,
    turns: int = 8,
    mock: bool = False,
    db_path: Path | None = None,
    artifact_paths: list[Path] | None = None,
    model: str = DEFAULT_MODEL,
    session_id: str | None = None,
) -> JointDiscoveryResult:
    aspasia = run_interview_and_aspasia(
        slug_or_id,
        research_goal=research_goal,
        opener=opener,
        turns=turns,
        mock=mock,
        db_path=db_path,
        model=model,
        session_id=session_id,
    )
    iza = run_iza_pass(
        aspasia,
        mock=mock,
        db_path=db_path,
        artifact_paths=artifact_paths,
        model=model,
    )
    return JointDiscoveryResult.merge(aspasia, iza)


def render_markdown(result: JointDiscoveryResult) -> str:
    parts = [
        f"# Joint discovery — `{result.person_id}`\n",
        f"**Profile:** {result.interview_profile}  ",
        f"**Evidence tier:** {result.evidence_tier}  ",
        f"**Session:** `{result.session_id}`\n",
        "## Limitações\n",
        *[f"- {x}" for x in result.limitations],
        "\n## Aspasia — discovery brief\n",
        result.aspasia_brief_md,
        "\n## Iza — superfície e restrição\n",
        result.iza_surface_md,
    ]
    if result.iza_multimodal_md:
        parts.extend(["\n## Iza — multimodal (artefatos)\n", result.iza_multimodal_md])
    parts.extend(["\n## Transcript\n", result.transcript_md])
    return "\n".join(parts)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("slug", help="person_id / YAML slug")
    p.add_argument("--research-goal", required=True)
    p.add_argument("--opener", default=None)
    p.add_argument("--turns", type=int, default=8)
    p.add_argument("--mock", action="store_true")
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--artifact",
        action="append",
        default=[],
        help="Image path for Iza multimodal pass (repeatable)",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    artifacts = [Path(a) for a in args.artifact]
    result = run_joint_discovery(
        args.slug,
        research_goal=args.research_goal,
        opener=args.opener,
        turns=args.turns,
        mock=args.mock,
        db_path=args.db,
        artifact_paths=artifacts or None,
    )
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
