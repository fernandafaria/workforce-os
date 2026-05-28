"""
build_twin — extract a structured Twin from a person's corpus (kind-aware).

Approach (Jason + Simon): give Claude the full corpus (or a sampled head +
tail of it) and ask it to emit a tool-use call whose input conforms to the
concrete Twin schema. Tool-use gives us JSON-schema validation for free
and is the Anthropic-SDK-native way to do structured output without a
third-party structured-output library.

Kind dispatch (D-AIE-001, war-room 2026-04-23):
    - If `rag/twins/persons/<person_id>.yaml` declares `twin_kind: operator`,
      use the operator tool schema + prompt and instantiate `OperatorTwin`.
    - Otherwise (missing spec, or `twin_kind: entrepreneur`, or legacy),
      use the entrepreneur path unchanged.

The operator path extracts `operator` (team_role, domains, responsibilities,
frameworks, communication_style) from corpus. When the spec seeds those
fields from a persona markdown (via `scripts/persona_to_twin_spec.py`),
the seed is passed to the model as context so the extraction can enrich
rather than re-guess.

We split temperature by field type (Jason's stance, which Claire
ratified):
    factual fields (company/operator, corpus)   → temp 0.1
    linguistic/decision                          → temp 0.5
    (no free-form "reflection" fields in v1 — added only if v2 needs them)

For MVP we run a single pass at temp 0.3 — good enough when the corpus
anchors the extraction. Multi-pass structured sampling is listed as a
Phase 2 upgrade in the README roadmap.

Usage:
    python -m rag.twins.build_twin <person_id>
    python -m rag.twins.build_twin <person_id> --dry-run       # prints the
                                                                 prompt only
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from rag.twins import storage
from rag.twins.schema import (
    CompanyContext,
    CorpusProvenance,
    DecisionFingerprint,
    EntrepreneurTwin,
    LinguisticProfile,
    OperatorProfile,
    OperatorTwin,
    passes_production_gate,
)

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-4-7"
MAX_CORPUS_CHARS = 120_000  # ~30k tokens — fits Opus context with headroom

REPO_ROOT = Path(__file__).resolve().parents[2]
SPECS_DIR = REPO_ROOT / "rag" / "twins" / "persons"


# ---------------------------------------------------------------------------
# Shared sub-schemas (linguistic + decision — kind-agnostic)
# ---------------------------------------------------------------------------


_LINGUISTIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "formality": {
            "type": "string",
            "enum": ["muito_informal", "informal", "neutro", "formal"],
        },
        "regional_markers": {"type": "array", "items": {"type": "string"}},
        "signature_phrases": {"type": "array", "items": {"type": "string"}},
        "jargon_sector": {"type": "array", "items": {"type": "string"}},
        "avoids": {"type": "array", "items": {"type": "string"}},
        "avg_sentence_length": {"type": "integer"},
    },
}

_DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "risk_appetite": {
            "type": "string",
            "enum": ["conservative", "moderate", "aggressive"],
        },
        "decision_speed": {
            "type": "string",
            "enum": ["slow_deliberate", "measured", "fast"],
        },
        "primary_drivers": {"type": "array", "items": {"type": "string"}},
        "deal_breakers": {"type": "array", "items": {"type": "string"}},
        "trust_sources": {"type": "array", "items": {"type": "string"}},
    },
}


# ---------------------------------------------------------------------------
# Entrepreneur tool schema + prompt (unchanged from v1)
# ---------------------------------------------------------------------------


ENTREPRENEUR_TOOL_SCHEMA: dict[str, Any] = {
    "name": "emit_entrepreneur_twin",
    "description": (
        "Emit the structured profile of a real entrepreneur, strictly grounded "
        "in the provided corpus. Do not invent facts: if the corpus does not "
        "support a field, leave list fields empty and use the conservative "
        "default for enums. Arrays should contain short strings (1-6 words each)."
    ),
    "input_schema": {
        "type": "object",
        "required": ["archetype_label", "company", "linguistic", "decision"],
        "properties": {
            "archetype_label": {
                "type": "string",
                "description": (
                    "Short human-readable label, e.g. 'Distribuidor SP 50M sucessão-em-curso'."
                ),
            },
            "company": {
                "type": "object",
                "required": [
                    "sector",
                    "sub_sector",
                    "revenue_range",
                    "employees_range",
                    "region",
                    "digital_maturity",
                    "family_business",
                ],
                "properties": {
                    "sector": {
                        "type": "string",
                        "enum": [
                            "distribuicao",
                            "clinicas",
                            "manufatura",
                            "varejo_fisico",
                            "advocacia",
                            "construcao",
                            "agronegocio",
                            "servicos_b2b",
                            "outro",
                        ],
                    },
                    "sub_sector": {"type": "string"},
                    "revenue_range": {
                        "type": "string",
                        "enum": ["1-10M", "10-50M", "50-200M", "200M+"],
                    },
                    "employees_range": {
                        "type": "string",
                        "enum": ["1-50", "50-200", "200-1000", "1000+"],
                    },
                    "region": {"type": "string"},
                    "digital_maturity": {
                        "type": "string",
                        "enum": ["legacy", "basic_erp", "some_saas", "digital_native"],
                    },
                    "family_business": {"type": "boolean"},
                    "succession_stage": {
                        "type": ["string", "null"],
                        "enum": [None, "none", "planning", "in_progress", "completed"],
                    },
                },
            },
            "linguistic": _LINGUISTIC_SCHEMA,
            "decision": _DECISION_SCHEMA,
        },
    },
}


ENTREPRENEUR_SYSTEM_PROMPT = """  # noqa: E501
You are extracting a structured profile of a real entrepreneur from a
corpus of their public statements (interviews, podcasts, talks, LinkedIn posts).

Rules:
1. Ground every claim in the corpus. If the corpus does not support a field,
   use the conservative default (empty list, null for optional fields, moderate
   for risk_appetite, measured for decision_speed).
2. Do NOT invent biographical facts. If the sector is unclear, emit "outro".
3. signature_phrases must be verbatim short phrases (≤ 8 words) that appear
   in the corpus. If you cannot find 3+ real signatures, emit fewer.
4. deal_breakers and primary_drivers should be things the person said they
   value or reject, not things you inferred from industry stereotypes.
5. Output MUST be a single tool call to emit_entrepreneur_twin."""


# ---------------------------------------------------------------------------
# Operator tool schema + prompt (D-AIE-001)
# ---------------------------------------------------------------------------


OPERATOR_TOOL_SCHEMA: dict[str, Any] = {
    "name": "emit_operator_twin",
    "description": (
        "Emit the structured profile of a Febrain operator — a public figure "
        "who performs a team role (e.g. Eugene Yan as Chief Applied ML). "
        "Strictly ground linguistic + decision fields in the provided corpus. "
        "For operator fields (team_role, domains, responsibilities, frameworks, "
        "communication_style), prefer the SEED block when provided; augment "
        "from corpus only when it reveals specifics missing from the seed. "
        "Arrays should contain short strings (1-6 words each)."
    ),
    "input_schema": {
        "type": "object",
        "required": ["archetype_label", "operator", "linguistic", "decision"],
        "properties": {
            "archetype_label": {
                "type": "string",
                "description": (
                    "Short human-readable label, e.g. "
                    "'Operator — Chief Applied ML & RecSys Strategist (ai-engineering)'."
                ),
            },
            "operator": {
                "type": "object",
                "required": [
                    "team_role",
                    "home_team",
                    "serves",
                    "domains",
                    "responsibilities",
                    "frameworks",
                    "communication_style",
                ],
                "properties": {
                    "team_role": {"type": "string"},
                    "home_team": {"type": "string"},
                    "serves": {"type": "array", "items": {"type": "string"}},
                    "domains": {"type": "array", "items": {"type": "string"}},
                    "responsibilities": {"type": "array", "items": {"type": "string"}},
                    "frameworks": {"type": "array", "items": {"type": "string"}},
                    "communication_style": {"type": "string"},
                },
            },
            "linguistic": _LINGUISTIC_SCHEMA,
            "decision": _DECISION_SCHEMA,
        },
    },
}


OPERATOR_SYSTEM_PROMPT = """You are extracting a structured profile of a Febrain operator — a real
public figure modeled as a team role inside a synthetic organization
(e.g. Eugene Yan as "Chief Applied ML & RecSys Strategist" in the
ai-engineering team).

Rules:
1. Ground every linguistic + decision claim in the corpus. If the corpus
   does not support a field, use the conservative default (empty list,
   moderate for risk_appetite, measured for decision_speed).
2. Operator fields (team_role, home_team, serves, domains, responsibilities,
   frameworks, communication_style) are typically seeded from the Febrain
   persona markdown — when a SEED block is supplied below, treat it as
   ground truth and only extend items you can support from corpus.
3. signature_phrases must be verbatim short phrases (≤ 8 words) that appear
   in the corpus.
4. primary_drivers, deal_breakers, trust_sources must be things the person
   actually said in the corpus — not industry stereotypes.
5. Output MUST be a single tool call to emit_operator_twin."""


# ---------------------------------------------------------------------------
# Corpus assembly
# ---------------------------------------------------------------------------


def _assemble_corpus(chunks: list[dict], max_chars: int = MAX_CORPUS_CHARS) -> str:
    """Concatenate the highest-quality chunks up to max_chars.

    We don't stuff randomly — Shreya's rubric already marked quality, so
    we prefer high-quality chunks. When the corpus exceeds max_chars we
    take the top-N by quality, then sort chronologically so the model
    sees temporal context.
    """
    sorted_by_quality = sorted(chunks, key=lambda c: c.get("quality_score") or 0.0, reverse=True)
    picked: list[dict] = []
    running = 0
    for c in sorted_by_quality:
        text_len = len(c["text"])
        if running + text_len > max_chars:
            continue
        picked.append(c)
        running += text_len

    picked.sort(key=lambda c: c.get("source_date") or "", reverse=False)

    parts: list[str] = []
    for c in picked:
        header = (
            f"[{c['source_type']}"
            + (f" | {c['source_date']}" if c.get("source_date") else "")
            + (f" | {c['source_url']}" if c.get("source_url") else "")
            + "]"
        )
        parts.append(f"{header}\n{c['text']}")
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Spec loading (kind detection + operator seed)
# ---------------------------------------------------------------------------


def load_spec(person_id: str) -> dict | None:
    """Return the persons/<person_id>.yaml spec as a dict, or None if missing.

    Used to detect `twin_kind` and pull the operator seed (fields pre-filled
    by `scripts/persona_to_twin_spec.py`). Missing spec or missing yaml
    module is non-fatal — we fall back to entrepreneur with empty seed.
    """
    path = SPECS_DIR / f"{person_id}.yaml"
    if not path.exists():
        return None
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        log.warning("pyyaml not installed; cannot read spec %s — defaulting to entrepreneur", path)
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        log.warning("spec parse error path=%s err=%s", path, e)
        return None


def _format_operator_seed(seed: dict | None) -> str:
    """Render the operator seed as a prompt-friendly block, or empty string."""
    if not seed:
        return ""
    bullets: list[str] = []
    for key in (
        "team_role",
        "home_team",
        "serves",
        "domains",
        "responsibilities",
        "frameworks",
        "communication_style",
    ):
        val = seed.get(key)
        if not val:
            continue
        if isinstance(val, list):
            bullets.append(f"- {key}: {val}")
        else:
            bullets.append(f"- {key}: {val!r}")
    if not bullets:
        return ""
    return "SEED (from Febrain persona markdown — treat as ground truth):\n" + "\n".join(bullets)


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------


def _extract_structured(
    corpus_text: str,
    *,
    tool_schema: dict[str, Any],
    system_prompt: str,
    user_message: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    from rag.twins.llm_extract import extract_structured
    from rag.twins.load_repo_env import load_repo_env

    load_repo_env()
    return extract_structured(
        corpus_text,
        tool_schema=tool_schema,
        system_prompt=system_prompt,
        user_message=user_message,
        model=model if model != DEFAULT_MODEL else None,
        temperature=temperature,
        max_tokens=max_tokens,
    )


# ---------------------------------------------------------------------------
# Public build function (kind-aware dispatcher)
# ---------------------------------------------------------------------------


def build(
    person_id: str,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.3,
    dry_run: bool = False,
    db_path: Path | None = None,
) -> EntrepreneurTwin | OperatorTwin:
    person = storage.get_person(person_id, db_path=db_path)
    if not person:
        raise SystemExit(f"Unknown person_id={person_id}. Run ingest_person first.")

    chunks = storage.list_chunks(person_id, include_holdout=False, db_path=db_path)
    if not chunks:
        raise SystemExit(f"No corpus chunks for person_id={person_id}. Run ingest_person first.")

    corpus_text = _assemble_corpus(chunks)
    log.info("built corpus person=%s chunks=%d chars=%d", person_id, len(chunks), len(corpus_text))

    spec = load_spec(person_id)
    kind = (spec or {}).get("twin_kind", "entrepreneur")
    log.info("build kind=%s person=%s", kind, person_id)

    stats = storage.corpus_stats(person_id, db_path=db_path)

    if kind == "operator":
        seed = (spec or {}).get("operator") or {}
        twin = _build_operator(
            person=person,
            person_id=person_id,
            corpus_text=corpus_text,
            chunks=chunks,
            stats=stats,
            seed=seed,
            model=model,
            temperature=temperature,
            dry_run=dry_run,
        )
    elif kind == "entrepreneur":
        twin = _build_entrepreneur(
            person=person,
            person_id=person_id,
            corpus_text=corpus_text,
            chunks=chunks,
            stats=stats,
            model=model,
            temperature=temperature,
            dry_run=dry_run,
        )
    else:
        raise SystemExit(f"spec twin_kind={kind!r} unknown; expected 'entrepreneur' or 'operator'")

    if dry_run:
        return twin

    twin_dict = twin.model_dump()
    twin_dict["person_id"] = person_id
    storage.upsert_twin(twin_dict, db_path=db_path)

    # Archetype twins (population clusters) run against a softer holdout
    # threshold because corpus is aggregated ethnography + 3rd-person
    # journalism (no 1st-person authoritative source).
    archetype_threshold = 0.72 if person.get("authorization") == "archetype_synthetic" else 0.75
    passed, reasons = passes_production_gate(twin, holdout_threshold=archetype_threshold)
    log.info(
        "twin built id=%s kind=%s status=%s gate_passed=%s gate_reasons=%s",
        twin.id,
        kind,
        twin.status,
        passed,
        reasons,
    )
    return twin


def _build_entrepreneur(
    *,
    person: dict,
    person_id: str,
    corpus_text: str,
    chunks: list[dict],
    stats: dict,
    model: str,
    temperature: float,
    dry_run: bool,
) -> EntrepreneurTwin:
    user_message = "Here is the corpus. Emit emit_entrepreneur_twin with your extraction."

    if dry_run:
        print(f"# dry run (entrepreneur) — would send {len(corpus_text)} chars to {model}")
        print(f"# system: {ENTREPRENEUR_SYSTEM_PROMPT[:160]}...")
        print(f"# tool: {ENTREPRENEUR_TOOL_SCHEMA['name']}")
        print(f"# chunks_used: {len(chunks)}")
        print(f"# preview (first 400 chars):\n{corpus_text[:400]}")
        return _stub_entrepreneur(person, stats)

    extracted = _extract_structured(
        corpus_text,
        tool_schema=ENTREPRENEUR_TOOL_SCHEMA,
        system_prompt=ENTREPRENEUR_SYSTEM_PROMPT,
        user_message=user_message,
        model=model,
        temperature=temperature,
    )

    # Opus occasionally omits required fields when corpus is ambiguous;
    # fall back to empty substructures rather than crash the build. The
    # downstream gate already flags missing company data.
    return EntrepreneurTwin(
        id=str(uuid.uuid4()),
        name_public=person.get("name_public"),
        archetype_label=extracted.get("archetype_label") or person["archetype_label"],
        is_composite=False,  # built from a single person's corpus
        company=CompanyContext(**(extracted.get("company") or {})),
        linguistic=LinguisticProfile(**(extracted.get("linguistic") or {})),
        decision=DecisionFingerprint(**(extracted.get("decision") or {})),
        corpus=CorpusProvenance(**stats, quality_score=_avg_quality(chunks)),
        eval_scores={},
        last_updated=datetime.date.today(),
        status="draft",
    )


def _build_operator(
    *,
    person: dict,
    person_id: str,
    corpus_text: str,
    chunks: list[dict],
    stats: dict,
    seed: dict,
    model: str,
    temperature: float,
    dry_run: bool,
) -> OperatorTwin:
    seed_block = _format_operator_seed(seed)
    user_message = (
        seed_block + "\n\n" if seed_block else ""
    ) + "Here is the corpus. Emit emit_operator_twin with your extraction."

    if dry_run:
        print(f"# dry run (operator) — would send {len(corpus_text)} chars to {model}")
        print(f"# system: {OPERATOR_SYSTEM_PROMPT[:160]}...")
        print(f"# tool: {OPERATOR_TOOL_SCHEMA['name']}")
        print(f"# chunks_used: {len(chunks)}")
        print(f"# seed keys: {sorted(seed.keys())}")
        print(f"# preview (first 400 chars):\n{corpus_text[:400]}")
        return _stub_operator(person, stats, seed)

    extracted = _extract_structured(
        corpus_text,
        tool_schema=OPERATOR_TOOL_SCHEMA,
        system_prompt=OPERATOR_SYSTEM_PROMPT,
        user_message=user_message,
        model=model,
        temperature=temperature,
    )

    # Operator fields: prefer extracted, fall back to seed when the model
    # leaves a list empty or a string blank — the seed came from curated
    # persona markdown, so it's the reliable baseline.
    operator_data = extracted.get("operator") or {}
    if not isinstance(operator_data, dict):
        operator_data = {}
    merged_operator = _merge_operator(operator_data, seed)

    return OperatorTwin(
        id=str(uuid.uuid4()),
        name_public=person.get("name_public"),
        archetype_label=extracted.get("archetype_label") or person["archetype_label"],
        is_composite=False,
        operator=OperatorProfile(**merged_operator),
        linguistic=LinguisticProfile(**(extracted.get("linguistic") or {})),
        decision=DecisionFingerprint(**(extracted.get("decision") or {})),
        corpus=CorpusProvenance(**stats, quality_score=_avg_quality(chunks)),
        eval_scores={},
        last_updated=datetime.date.today(),
        status="draft",
    )


def _merge_operator(extracted: dict, seed: dict) -> dict:
    """Merge LLM-extracted operator fields with the seed, preferring extracted.

    Lists: if the model returns an empty list, fall back to seed. Strings:
    if the model returns blank, fall back to seed. Never let corpus
    emptiness wipe out curated persona data.
    """
    out: dict[str, Any] = {}
    for key in (
        "team_role",
        "home_team",
        "serves",
        "domains",
        "responsibilities",
        "frameworks",
        "communication_style",
    ):
        ext = extracted.get(key)
        seed_val = seed.get(key)
        if isinstance(ext, list):
            out[key] = ext if ext else (seed_val or [])
        elif isinstance(ext, str):
            out[key] = ext if ext.strip() else (seed_val or "")
        else:
            out[key] = seed_val or (
                "" if key in {"team_role", "home_team", "communication_style"} else []
            )
    return out


def _stub_entrepreneur(person: dict, stats: dict) -> EntrepreneurTwin:
    return EntrepreneurTwin(
        id="dry-run",
        name_public=person.get("name_public"),
        archetype_label=person["archetype_label"],
        company=CompanyContext(
            sector="outro",
            sub_sector="unknown",
            revenue_range="1-10M",
            employees_range="1-50",
            region="unknown",
            digital_maturity="legacy",
            family_business=False,
        ),
        linguistic=LinguisticProfile(),
        decision=DecisionFingerprint(),
        corpus=CorpusProvenance(**stats),
        eval_scores={},
    )


def _stub_operator(person: dict, stats: dict, seed: dict) -> OperatorTwin:
    return OperatorTwin(
        id="dry-run",
        name_public=person.get("name_public"),
        archetype_label=person["archetype_label"],
        operator=OperatorProfile(**_merge_operator({}, seed)),
        linguistic=LinguisticProfile(),
        decision=DecisionFingerprint(),
        corpus=CorpusProvenance(**stats),
        eval_scores={},
    )


def _avg_quality(chunks: list[dict]) -> float:
    scores = [c.get("quality_score") or 0.0 for c in chunks]
    return sum(scores) / len(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("person_id")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--temperature", type=float, default=0.3)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    twin = build(
        args.person_id,
        model=args.model,
        temperature=args.temperature,
        dry_run=args.dry_run,
        db_path=args.db,
    )
    if not args.dry_run:
        print(json.dumps(twin.model_dump(), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
