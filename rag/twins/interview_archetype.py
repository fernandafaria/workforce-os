"""
interview_archetype — agent-vs-agent discovery interview PoC.

Two LLM agents talk to each other:

  • interviewer: Teresa Torres-style continuous-discovery interviewer.
    One open question per turn, anchored on past + specific behavior,
    never hypothetical, never leading, never solution-validation. Probes
    for story, trigger, context, who-what-when.

  • archetype: synthetic population twin grounded on real corpus via the
    `corpus_search` tool. Generalized prompt — works for non-entrepreneur
    archetypes ("universitário primeira-gen", "aposentado INSS", "mãe SE
    urbana"), not just `EntrepreneurTwin` business framing that
    `chat_with_twin.py` assumes.

Why split from chat_with_twin.py
    chat_with_twin loops on terminal input from a human interviewer and
    hard-codes "empresário do setor X" framing. For a PoC where we need
    discovery on non-business archetypes without a human in the loop,
    it's cleaner to fork the prompt + replace `input()` with a second
    agent than to retrofit the existing module.

Usage:
    python -m rag.twins.interview_archetype <twin_id> --turns 8 \\
        --research-goal "como decide gastar bolsa-permanência" \\
        --opener "Conta da última vez que você precisou decidir o que fazer com a bolsa do mês."
    python -m rag.twins.interview_archetype arch-mkt-orquestrador-insights --mock
    python -m rag.twins.interview_marketing_buyer <slug>   # buyer profile alias

Profiles (--mode): auto | population | marketing-buyer
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from rag.twins import corpus_search, storage
from rag.twins.interview_profile import (
    ARCHETYPE_BUYER_TEMPLATE,
    ARCHETYPE_EXECUTIVE_AI_TEMPLATE,
    ARCHETYPE_POPULATION_TEMPLATE,
    INTERVIEWER_BUYER_TEMPLATE,
    INTERVIEWER_EXECUTIVE_AI_TEMPLATE,
    INTERVIEWER_POPULATION_TEMPLATE,
    InterviewProfile,
    detect_interview_profile,
    load_person_spec,
)

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_TEMPERATURE_TWIN = 0.3
DEFAULT_TEMPERATURE_INTERVIEWER = 0.5
DEFAULT_TURNS = 8

PERSONS_DIR = Path("rag/twins/persons")
DEFAULT_BRIEFING_PATH = Path("rag/twins/shared/populacao-brasileira-2026-briefing.md")


def _load_situational_briefing(path: Path | None = None) -> str:
    """Load the shared situational-context briefing.

    The briefing anchors interviewer + archetype in Brasil-real (numbers,
    trends, mood) so questions and answers are coherent with the era — it
    is NOT the archetype's personal experience (that comes from
    `corpus_search` against the archetype's own corpus).

    Returns an empty-fallback note if the file is missing so the rest of
    the pipeline keeps working.
    """
    target = path or DEFAULT_BRIEFING_PATH
    try:
        return target.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        log.warning("situational briefing not found at %s — using empty fallback", target)
        return "(sem briefing situacional carregado)"


# ---------------------------------------------------------------------------
# Archetype (interviewee) system prompt — population vs buyer-professional
# ---------------------------------------------------------------------------


def build_archetype_system_prompt(
    twin: dict,
    *,
    spec_notes: str | None = None,
    situational_briefing: str | None = None,
    profile: InterviewProfile | None = None,
) -> str:
    archetype_label = twin.get("archetype_label", "pessoa do arquétipo")
    linguistic = twin.get("linguistic", {}) or {}
    decision = twin.get("decision", {}) or {}

    notes = (spec_notes or "").strip() or "(sem nota adicional — use só o rótulo do arquétipo)"
    briefing = (situational_briefing or _load_situational_briefing()).strip()

    signature_phrases = _bullets(
        linguistic.get("signature_phrases", []),
        fallback="(corpus não extraiu assinaturas ainda — fale neutro)",
    )
    decision_fp = _decision_block(decision)

    person_id = twin.get("person_id") or twin.get("id", "")
    prof = profile or detect_interview_profile(
        person_id, spec=load_person_spec(person_id) if person_id else None
    )
    if prof is InterviewProfile.BUYER_PROFESSIONAL:
        template = ARCHETYPE_BUYER_TEMPLATE
        default_formality = "formal"
    elif prof is InterviewProfile.EXECUTIVE_AI_FLUENCY:
        template = ARCHETYPE_EXECUTIVE_AI_TEMPLATE
        default_formality = "formal"
    else:
        template = ARCHETYPE_POPULATION_TEMPLATE
        default_formality = "informal"

    return template.format(
        archetype_label=archetype_label,
        archetype_notes=notes,
        situational_briefing=briefing,
        formality=linguistic.get("formality", default_formality),
        signature_phrases=signature_phrases,
        decision_fingerprint=decision_fp,
    )


# ---------------------------------------------------------------------------
# Interviewer system prompt — Teresa Torres / buyer-professional variants
# ---------------------------------------------------------------------------


def build_interviewer_system_prompt(
    *,
    research_goal: str,
    archetype_label: str,
    situational_briefing: str | None = None,
    profile: InterviewProfile | None = None,
    person_id: str | None = None,
    interview_guide: str | None = None,
) -> str:
    briefing = (situational_briefing or _load_situational_briefing()).strip()
    prof = profile
    if prof is None and person_id:
        prof = detect_interview_profile(person_id, spec=load_person_spec(person_id))
    if prof is None:
        prof = InterviewProfile.POPULATION
    if prof is InterviewProfile.BUYER_PROFESSIONAL:
        template = INTERVIEWER_BUYER_TEMPLATE
    elif prof is InterviewProfile.EXECUTIVE_AI_FLUENCY:
        template = INTERVIEWER_EXECUTIVE_AI_TEMPLATE
    else:
        template = INTERVIEWER_POPULATION_TEMPLATE
    if prof is InterviewProfile.EXECUTIVE_AI_FLUENCY:
        guide_section = ""
        if interview_guide:
            guide_section = (
                f"ROTEIRO DA ENTREVISTA (siga na ordem; não pule o Bloco 0):\n\n"
                f"{interview_guide.strip()}\n\n"
            )
        return template.format(
            research_goal=research_goal.strip(),
            archetype_label=archetype_label,
            situational_briefing=briefing,
            interview_guide_section=guide_section,
        )
    return template.format(
        research_goal=research_goal.strip(),
        archetype_label=archetype_label,
        situational_briefing=briefing,
    )


# ---------------------------------------------------------------------------
# Tool (only the archetype agent uses it)
# ---------------------------------------------------------------------------


CORPUS_SEARCH_TOOL = {
    "name": "corpus_search",
    "description": (
        "Busca até 4 trechos reais do seu próprio corpus (entrevistas, "
        "depoimentos, reportagens 1ª pessoa). Use SEMPRE que o entrevistador "
        "perguntar algo sobre sua rotina, decisões passadas, pessoas, "
        "lugares ou opiniões concretas. Passe a query mais específica que "
        "conseguir formular em linguagem natural."
    ),
    "input_schema": {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string", "description": "Natural-language search query"},
            "k": {"type": "integer", "minimum": 1, "maximum": 6, "default": 4},
        },
    },
}


# ---------------------------------------------------------------------------
# Agent-vs-agent loop
# ---------------------------------------------------------------------------


END_TOKEN = "[END_INTERVIEW]"


def _resolve_interview_profile(
    person_id: str,
    *,
    spec: dict | None,
    mode_arg: str | None,
) -> InterviewProfile:
    if mode_arg in (None, "", "auto"):
        return detect_interview_profile(person_id, spec=spec)
    if mode_arg in ("marketing-buyer", "marketing_buyer", "buyer", "buyer_professional"):
        return InterviewProfile.BUYER_PROFESSIONAL
    if mode_arg in (
        "executive-ai-fluency",
        "executive_ai_fluency",
        "executive",
        "exec-ai",
    ):
        return InterviewProfile.EXECUTIVE_AI_FLUENCY
    if mode_arg == "population":
        return InterviewProfile.POPULATION
    raise SystemExit(
        f"Unknown --mode {mode_arg!r}; use auto | population | marketing-buyer | "
        "executive-ai-fluency"
    )


def resolve_twin_id(
    slug_or_id: str,
    db_path: Path | None = None,
    *,
    auto_seed: bool = False,
) -> str:
    """Resolve YAML slug (person_id) or twin UUID to canonical twin_id."""
    key = slug_or_id.strip()
    twin = storage.get_twin(key, db_path=db_path)
    if twin:
        return twin["id"]
    by_slug = storage.get_twin_by_slug(key, db_path=db_path)
    if by_slug:
        return by_slug["id"]
    if auto_seed:
        from rag.twins.dev_seed import ensure_twin_ready

        return ensure_twin_ready(key, db_path=db_path)
    raise SystemExit(
        f"No twin for slug_or_id={key!r}. Run ingest+build on DO runner or "
        f"`python -m rag.twins.dev_seed {key}` for local/MCP bootstrap."
    )


def interview(
    twin_id: str,
    *,
    research_goal: str,
    opener: str | None = None,
    turns: int = DEFAULT_TURNS,
    session_id: str | None = None,
    model: str = DEFAULT_MODEL,
    temperature_twin: float = DEFAULT_TEMPERATURE_TWIN,
    temperature_interviewer: float = DEFAULT_TEMPERATURE_INTERVIEWER,
    mock: bool = False,
    db_path: Path | None = None,
    spec_path: Path | None = None,
    auto_seed: bool = True,
    mode: str | None = "auto",
    guide: str | None = None,
) -> str:
    twin_id = resolve_twin_id(twin_id, db_path=db_path, auto_seed=auto_seed)
    twin = storage.get_twin(twin_id, db_path=db_path)
    if not twin:
        raise SystemExit(f"Unknown twin_id={twin_id}")

    person_id = twin.get("person_id") or _derive_person_id(twin_id, db_path)
    spec = load_person_spec(person_id) if person_id else None
    profile = _resolve_interview_profile(person_id, spec=spec, mode_arg=mode)
    if profile is InterviewProfile.BUYER_PROFESSIONAL:
        prefix = "mkt"
    elif profile is InterviewProfile.EXECUTIVE_AI_FLUENCY:
        prefix = "exec-ai"
    else:
        prefix = "arch"
    session_id = session_id or f"{prefix}-interview-{uuid.uuid4().hex[:8]}"

    guide_key = (guide or "").strip().lower()
    interview_guide_text: str | None = None
    mock_question_bank: list[str] | None = None
    if guide_key in ("mom-test", "mom_test", "momtest"):
        from rag.twins.executive_ai_fluency_interview_guide import (
            MOM_TEST_DEFAULT_TURNS,
            MOM_TEST_MOCK_QUESTIONS,
            MOM_TEST_OPENER,
            MOM_TEST_RESEARCH_GOAL,
            load_mom_test_guide_markdown,
        )

        interview_guide_text = load_mom_test_guide_markdown()
        mock_question_bank = list(MOM_TEST_MOCK_QUESTIONS)
        research_goal = MOM_TEST_RESEARCH_GOAL
        if opener is None:
            opener = MOM_TEST_OPENER
        if turns == DEFAULT_TURNS:
            turns = MOM_TEST_DEFAULT_TURNS

    spec_notes = _load_spec_notes(person_id, spec_path)
    situational_briefing = _load_situational_briefing()
    archetype_system = build_archetype_system_prompt(
        twin,
        spec_notes=spec_notes,
        situational_briefing=situational_briefing,
        profile=profile,
    )
    interviewer_system = build_interviewer_system_prompt(
        research_goal=research_goal,
        archetype_label=twin.get("archetype_label", twin_id),
        situational_briefing=situational_briefing,
        profile=profile,
        person_id=person_id,
        interview_guide=interview_guide_text,
    )

    print(f"Starting agent-vs-agent interview session={session_id} twin={twin_id}")
    print(f"Profile: {profile.value}")
    print(f"Goal: {research_goal}")
    print(f"Turns budget: {turns}\n")

    if mock:
        return _run_mock(
            twin=twin,
            twin_id=twin_id,
            person_id=person_id,
            session_id=session_id,
            opener=opener,
            turns=turns,
            db_path=db_path,
            profile=profile,
            question_bank=mock_question_bank,
        )

    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError("anthropic SDK not installed — use --mock for offline") from e

    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set — use --mock for offline testing")

    client = anthropic.Anthropic(api_key=key)

    interviewer_msgs: list[dict[str, Any]] = []
    twin_msgs: list[dict[str, Any]] = []
    turn_index = 0

    next_question = opener
    for round_idx in range(turns):
        if next_question is None:
            next_question = _interviewer_turn(
                client=client,
                model=model,
                temperature=temperature_interviewer,
                system=interviewer_system,
                messages=interviewer_msgs,
            )

        if _is_end(next_question):
            print(f"interviewer> [encerrou em t={round_idx}]")
            break

        print(f"interviewer> {next_question}\n")
        storage.log_turn(
            session_id=session_id,
            twin_id=twin_id,
            turn_index=turn_index,
            speaker="interviewer",
            content=next_question,
            db_path=db_path,
        )
        turn_index += 1
        interviewer_msgs.append({"role": "assistant", "content": next_question})

        twin_msgs.append({"role": "user", "content": next_question})
        twin_answer, twin_msgs, tool_calls_used = _twin_turn(
            client=client,
            model=model,
            temperature=temperature_twin,
            system=archetype_system,
            messages=twin_msgs,
            person_id=person_id,
            db_path=db_path,
        )

        twin_label = twin.get("name_public") or "archetype"
        print(f"{twin_label}> {twin_answer}\n")
        storage.log_turn(
            session_id=session_id,
            twin_id=twin_id,
            turn_index=turn_index,
            speaker="twin",
            content=twin_answer,
            tool_calls=tool_calls_used,
            db_path=db_path,
        )
        turn_index += 1
        interviewer_msgs.append({"role": "user", "content": twin_answer})
        next_question = None  # force interviewer to generate next round

    print(f"\nSession saved: {session_id}")
    return session_id


def _supports_temperature(model: str) -> bool:
    """Opus 4.7 deprecated the `temperature` param (BadRequestError on send).
    Older models still accept it. Strip the param transparently for any
    model whose name starts with claude-opus-4-7-* so callers don't have
    to special-case at every call site.
    """
    return not model.startswith("claude-opus-4-7")


def _interviewer_turn(
    *,
    client,
    model: str,
    temperature: float,
    system: str,
    messages: list[dict],
) -> str:
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": 400,
        "system": system,
        "messages": messages or [{"role": "user", "content": "Comece a entrevista."}],
    }
    if _supports_temperature(model):
        kwargs["temperature"] = temperature
    resp = client.messages.create(**kwargs)
    text_parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return "\n".join(text_parts).strip()


def _twin_turn(
    *,
    client,
    model: str,
    temperature: float,
    system: str,
    messages: list[dict],
    person_id: str,
    db_path: Path | None,
) -> tuple[str, list[dict], list[dict]]:
    """Twin loop that may invoke corpus_search any number of times before answering."""
    tool_calls_used: list[dict] = []
    while True:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": 1024,
            "system": system,
            "tools": [CORPUS_SEARCH_TOOL],
            "messages": messages,
        }
        if _supports_temperature(model):
            kwargs["temperature"] = temperature
        resp = client.messages.create(**kwargs)
        stop = resp.stop_reason
        assistant_content = [_block_as_dict(b) for b in resp.content if getattr(b, "type", None)]
        messages.append({"role": "assistant", "content": assistant_content})

        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if stop != "tool_use" or not tool_uses:
            text_parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
            return "\n\n".join(text_parts).strip(), messages, tool_calls_used

        tool_results: list[dict] = []
        for tu in tool_uses:
            query = tu.input.get("query", "") if isinstance(tu.input, dict) else ""
            k = tu.input.get("k", 4) if isinstance(tu.input, dict) else 4
            results = corpus_search.search(person_id, query, k=k, db_path=db_path)
            tool_calls_used.append({"query": query, "k": k, "n_results": len(results)})
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(results, ensure_ascii=False),
                }
            )
        messages.append({"role": "user", "content": tool_results})


# ---------------------------------------------------------------------------
# Mock loop
# ---------------------------------------------------------------------------


_MOCK_QUESTIONS_POPULATION = [
    "Conta da última vez que você precisou tomar uma decisão grande sobre dinheiro.",
    "E como você chegou nessa decisão? Quem você consultou?",
    "O que veio antes desse momento? Tinha algum gatilho específico?",
    "Como você se sentiu depois?",
    "Tem alguma coisa que eu não te perguntei e que você acha importante eu saber?",
]

_MOCK_QUESTIONS_BUYER = [
    "Conta da última vez que você precisou levar um insight ou estudo para o comitê ou para o board.",
    "O que estava no material que você apresentou — e o que te fizeram questionar?",
    "Como você escolheu (ou descartou) fornecedor ou ferramenta nessa ocasião?",
    "O que faria você não recomendar uma ferramenta nova de pesquisa sintética para um colega?",
    "Tem algo que eu não perguntei e que define como você compra pesquisa hoje?",
]


def _run_mock(
    *,
    twin: dict,
    twin_id: str,
    person_id: str,
    session_id: str,
    opener: str | None,
    turns: int,
    db_path: Path | None,
    profile: InterviewProfile = InterviewProfile.POPULATION,
    question_bank: list[str] | None = None,
) -> str:
    twin_label = twin.get("name_public") or "archetype"
    turn_index = 0
    if question_bank is not None:
        questions = list(question_bank)
    else:
        if profile in (
            InterviewProfile.BUYER_PROFESSIONAL,
            InterviewProfile.EXECUTIVE_AI_FLUENCY,
        ):
            bank = _MOCK_QUESTIONS_BUYER
        else:
            bank = _MOCK_QUESTIONS_POPULATION
        questions = ([opener] if opener else []) + list(bank)
    for q in questions[:turns]:
        print(f"interviewer> {q}\n")
        storage.log_turn(
            session_id=session_id,
            twin_id=twin_id,
            turn_index=turn_index,
            speaker="interviewer",
            content=q,
            db_path=db_path,
        )
        turn_index += 1

        hits = corpus_search.search(person_id, q, k=3, db_path=db_path)
        if hits:
            answer = f"[mock] {hits[0]['quote'][:200]}…"
        else:
            answer = "[mock] Isso eu não sei te dizer agora."
        print(f"{twin_label}(mock)> {answer}\n")
        storage.log_turn(
            session_id=session_id,
            twin_id=twin_id,
            turn_index=turn_index,
            speaker="twin",
            content=answer,
            tool_calls=[{"query": q, "n_results": len(hits)}],
            db_path=db_path,
        )
        turn_index += 1
    print(f"\nSession saved: {session_id}")
    return session_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_end(text: str) -> bool:
    return END_TOKEN in (text or "").strip()


def _block_as_dict(block) -> dict:
    t = getattr(block, "type", None)
    if t == "text":
        return {"type": "text", "text": block.text}
    if t == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return {"type": t or "unknown"}


def _bullets(items: list[str], *, fallback: str) -> str:
    if not items:
        return fallback
    return "\n".join(f'- "{item}"' for item in items[:8])


def _decision_block(decision: dict) -> str:
    return (
        f"- Apetite a risco: {decision.get('risk_appetite', 'moderate')}\n"
        f"- Velocidade de decisão: {decision.get('decision_speed', 'measured')}\n"
        f"- Drivers principais: {', '.join(decision.get('primary_drivers', [])) or '(corpus insuficiente)'}\n"
        f"- Deal breakers: {', '.join(decision.get('deal_breakers', [])) or '(corpus insuficiente)'}\n"
        f"- Fontes de confiança: {', '.join(decision.get('trust_sources', [])) or '(corpus insuficiente)'}"
    )


def _derive_person_id(twin_id: str, db_path: Path | None) -> str:
    with storage.connect(db_path) as conn:
        row = conn.execute("SELECT person_id FROM twin WHERE id = ?", (twin_id,)).fetchone()
    if row and row["person_id"]:
        return row["person_id"]
    raise SystemExit(f"twin={twin_id} has no person_id — ingest + build must run first")


def _load_spec_notes(person_id: str, spec_path: Path | None) -> str | None:
    """Pull `notes:` from the YAML spec if present — richer than schema fields
    for population archetypes whose CompanyContext defaults to placeholders."""
    candidate = spec_path or (PERSONS_DIR / f"{person_id}.yaml")
    if not candidate.exists():
        return None
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        log.debug("PyYAML not installed; skipping spec notes")
        return None
    try:
        data = yaml.safe_load(candidate.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("could not parse %s: %s", candidate, e)
        return None
    if not isinstance(data, dict):
        return None
    notes = data.get("notes")
    return str(notes).strip() if notes else None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "twin_id",
        help="Twin UUID or person slug (e.g. arch-mkt-orquestrador-insights)",
    )
    p.add_argument(
        "--no-auto-seed",
        action="store_true",
        help="Do not bootstrap twins.db from YAML when twin is missing",
    )
    p.add_argument(
        "--research-goal",
        default="entender rotina e decisões cotidianas deste arquétipo",
        help="What the discovery interview is trying to learn.",
    )
    p.add_argument(
        "--opener",
        default=None,
        help="First question the interviewer asks. If omitted, the interviewer agent picks one.",
    )
    p.add_argument("--turns", type=int, default=DEFAULT_TURNS)
    p.add_argument("--session-id", default=None)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--temperature-twin", type=float, default=DEFAULT_TEMPERATURE_TWIN)
    p.add_argument("--temperature-interviewer", type=float, default=DEFAULT_TEMPERATURE_INTERVIEWER)
    p.add_argument("--mock", action="store_true", help="Run without Anthropic API")
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--spec",
        type=Path,
        default=None,
        help="Path to person YAML spec (defaults to rag/twins/persons/<twin_id>.yaml)",
    )
    p.add_argument(
        "--mode",
        default="auto",
        choices=("auto", "population", "marketing-buyer", "executive-ai-fluency"),
        help=(
            "Interview profile: population | buyer_professional (CMO/Insights) | "
            "executive_ai_fluency (C-suite AI fluency / FOMO)."
        ),
    )
    p.add_argument(
        "--guide",
        default=None,
        choices=("mom-test",),
        help="Structured interview script (exec AI: Mom-Test Blocos 0–4, ~24 turns).",
    )
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    interview(
        args.twin_id,
        research_goal=args.research_goal,
        opener=args.opener,
        turns=args.turns,
        session_id=args.session_id,
        model=args.model,
        temperature_twin=args.temperature_twin,
        temperature_interviewer=args.temperature_interviewer,
        mock=args.mock,
        db_path=args.db,
        spec_path=args.spec,
        auto_seed=not args.no_auto_seed,
        mode=args.mode,
        guide=args.guide,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
