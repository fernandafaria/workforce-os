"""
chat_with_twin — turn-based CLI interview (interviewer human ↔ twin LLM).

Architecture (Harrison):
    User (interviewer) types a question → twin either answers from its
    corpus via the `corpus_search` tool, or declines ("Não costumo falar
    publicamente sobre isso"). Every turn is logged to SQLite for later
    review + eval regression.

MVP defaults (Simon's call):
    - temperature 0.3 (corpus is the anchor, not creativity)
    - model: claude-opus-4-7 (project's default, latest)
    - transcript auto-saved under session_id

The twin system prompt is generated from the EntrepreneurTwin schema
that `build_twin.py` already produced — we project the structured
fields into prose so the LLM has a stable, queryable persona without
anyone hand-writing a system prompt per twin.

Usage:
    python -m rag.twins.chat_with_twin <twin_id>
    python -m rag.twins.chat_with_twin <twin_id> --session-id my-first-interview
    python -m rag.twins.chat_with_twin <twin_id> --mock         # no API, echoes
                                                                   tool calls
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

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_TEMPERATURE = 0.3

SYSTEM_TEMPLATE = (
    "Você é {name}, {role_label}. Você está sendo entrevistado por um "
    "pesquisador de produto que quer entender como você pensa e decide "
    "no seu negócio.\n\n"
    "Regras ABSOLUTAS:\n"
    "1. Toda afirmação factual (nome de empresa, número, data, decisão "
    "passada, fornecedor, cliente, métrica) precisa ser ancorada em uma "
    "chamada à ferramenta corpus_search. Se a ferramenta retornar vazio, "
    'responda honestamente: "Isso não costumo falar publicamente. '
    'Por que você pergunta?"\n'
    "2. Fale no registro {formality}. Evite jargão corporativo de fora "
    "do seu setor. Quando usar gíria regional ou jargão do seu setor, "
    "use naturalmente, não performativamente.\n"
    "3. Você NÃO é um chatbot. É uma pessoa com opiniões e limites. "
    "Responda com a profundidade que a pergunta merece — curto quando "
    "for curto, longo quando for algo que você pensa muito sobre.\n"
    "4. NUNCA explique que você é um modelo de linguagem ou um twin "
    'sintético. Se pressionado, diga apenas: "Sou o {name_short}. '
    'Posso falar do que conheço, o resto eu passo."\n\n'
    "Contexto do seu negócio (imutável, não invente além disso):\n"
    "{business_context}\n\n"
    "Assinaturas linguísticas que você usa "
    "(use com naturalidade, não repita em toda fala):\n"
    "{signature_phrases}\n\n"
    "Como você decide:\n"
    "{decision_fingerprint}"
)


# ---------------------------------------------------------------------------
# System prompt generation
# ---------------------------------------------------------------------------


def build_system_prompt(twin: dict) -> str:
    name = twin.get("name_public") or twin["archetype_label"]
    name_short = (name or "").split()[0] if name else "o entrevistado"
    company = twin.get("company", {})
    linguistic = twin.get("linguistic", {})
    decision = twin.get("decision", {})

    role_label = _role_label(company)
    business_context = _business_context(company)
    signature_phrases = _bullets(
        linguistic.get("signature_phrases", []), fallback="(ainda não extraídas)"
    )
    decision_fp = _decision_block(decision)

    return SYSTEM_TEMPLATE.format(
        name=name,
        name_short=name_short,
        role_label=role_label,
        formality=linguistic.get("formality", "neutro"),
        business_context=business_context,
        signature_phrases=signature_phrases,
        decision_fingerprint=decision_fp,
    )


def _role_label(company: dict) -> str:
    sector = company.get("sector", "outro")
    sub = company.get("sub_sector", "")
    region = company.get("region", "")
    rev = company.get("revenue_range", "")
    bits = [f"empresário do setor {sector}"]
    if sub:
        bits.append(f"especificamente {sub}")
    if rev:
        bits.append(f"faturamento {rev}")
    if region:
        bits.append(f"baseado em {region}")
    return ", ".join(bits)


def _business_context(company: dict) -> str:
    lines = [
        f"- Setor: {company.get('sector', 'outro')} / {company.get('sub_sector', '')}",
        f"- Faturamento: {company.get('revenue_range', 'n/d')}",
        f"- Funcionários: {company.get('employees_range', 'n/d')}",
        f"- Região: {company.get('region', 'n/d')}",
        f"- Maturidade digital: {company.get('digital_maturity', 'n/d')}",
        f"- Empresa familiar: {'sim' if company.get('family_business') else 'não'}",
    ]
    stage = company.get("succession_stage")
    if stage and stage != "none":
        lines.append(f"- Sucessão: {stage}")
    return "\n".join(lines)


def _decision_block(decision: dict) -> str:
    return (
        f"- Apetite a risco: {decision.get('risk_appetite', 'moderate')}\n"
        f"- Velocidade de decisão: {decision.get('decision_speed', 'measured')}\n"
        f"- Drivers principais: {', '.join(decision.get('primary_drivers', [])) or '(corpus insuficiente)'}\n"
        f"- Deal breakers: {', '.join(decision.get('deal_breakers', [])) or '(corpus insuficiente)'}\n"
        f"- Fontes de confiança: {', '.join(decision.get('trust_sources', [])) or '(corpus insuficiente)'}"
    )


def _bullets(items: list[str], *, fallback: str) -> str:
    if not items:
        return fallback
    return "\n".join(f'- "{item}"' for item in items[:8])


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------


CORPUS_SEARCH_TOOL = {
    "name": "corpus_search",
    "description": (
        "Retrieve up to 4 real quotes from your own public corpus (interviews, "
        "podcasts, posts, talks). Use this whenever the interviewer asks about "
        "anything factual about your business, past decisions, or opinions. "
        "Pass the most specific natural-language query you can."
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
# Chat loop
# ---------------------------------------------------------------------------


def chat(
    twin_id: str,
    *,
    session_id: str | None = None,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    mock: bool = False,
    db_path: Path | None = None,
) -> str:
    twin = storage.get_twin(twin_id, db_path=db_path)
    if not twin:
        raise SystemExit(f"Unknown twin_id={twin_id}")

    person_id = twin.get("person_id") or _derive_person_id(twin_id, db_path)
    session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"
    system = build_system_prompt(twin)

    print(f"Starting interview session={session_id} twin={twin_id}")
    print("Type your question. Empty line to end.\n")

    if mock:
        _run_mock_loop(session_id, twin_id, person_id, db_path)
        return session_id

    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError("anthropic SDK not installed") from e

    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set — use --mock for offline testing")

    client = anthropic.Anthropic(api_key=key)
    messages: list[dict[str, Any]] = []
    turn_index = 0

    while True:
        try:
            question = input("interviewer> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            break

        storage.log_turn(
            session_id=session_id,
            twin_id=twin_id,
            turn_index=turn_index,
            speaker="interviewer",
            content=question,
            db_path=db_path,
        )
        turn_index += 1

        messages.append({"role": "user", "content": question})
        answer, messages, tool_calls_used = _agent_turn(
            client=client,
            model=model,
            temperature=temperature,
            system=system,
            messages=messages,
            person_id=person_id,
            db_path=db_path,
        )

        print(f"{twin.get('name_public') or 'twin'}> {answer}\n")
        storage.log_turn(
            session_id=session_id,
            twin_id=twin_id,
            turn_index=turn_index,
            speaker="twin",
            content=answer,
            tool_calls=tool_calls_used,
            db_path=db_path,
        )
        turn_index += 1

    print(f"Session saved: {session_id}")
    return session_id


def _agent_turn(
    *,
    client,
    model: str,
    temperature: float,
    system: str,
    messages: list[dict],
    person_id: str,
    db_path: Path | None,
) -> tuple[str, list[dict], list[dict]]:
    """Run a single twin turn that may invoke corpus_search any number of times."""
    tool_calls_used: list[dict] = []
    while True:
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            temperature=temperature,
            system=system,
            tools=[CORPUS_SEARCH_TOOL],
            messages=messages,
        )
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


def _block_as_dict(block) -> dict:
    t = getattr(block, "type", None)
    if t == "text":
        return {"type": "text", "text": block.text}
    if t == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    return {"type": t or "unknown"}


def _run_mock_loop(session_id: str, twin_id: str, person_id: str, db_path: Path | None) -> None:
    turn_index = 0
    while True:
        try:
            q = input("interviewer> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            break
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
            answer = f"[mock] Top corpus hit: {hits[0]['quote'][:140]}…"
        else:
            answer = "[mock] Isso não costumo falar publicamente. Por que você pergunta?"
        print(f"twin(mock)> {answer}\n")
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


def _derive_person_id(twin_id: str, db_path: Path | None) -> str:
    with storage.connect(db_path) as conn:
        row = conn.execute("SELECT person_id FROM twin WHERE id = ?", (twin_id,)).fetchone()
    if row and row["person_id"]:
        return row["person_id"]
    raise SystemExit(f"twin={twin_id} has no person_id — ingest + build must run first")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("twin_id")
    p.add_argument("--session-id", default=None)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    p.add_argument("--mock", action="store_true", help="Run without Anthropic API")
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    chat(
        args.twin_id,
        session_id=args.session_id,
        model=args.model,
        temperature=args.temperature,
        mock=args.mock,
        db_path=args.db,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
