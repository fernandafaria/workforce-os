"""
eval_twin — Hamel's MVP eval harness (Layer 1: holdout cosine).

For each held-out corpus chunk we:
  1. Synthesize a discovery-style question that could have elicited the
     held-out quote ("what would you ask the person so that their reply
     lines up with this quote?").
  2. Ask the twin to answer that question.
  3. Compute cosine similarity between the twin's answer embedding and
     the held-out quote embedding (both via Voyage — same vector space as
     storage embeddings, no cross-space noise).
  4. Report pass/fail against the layer-1 threshold: p70 of similarity
     ≥ 0.75 (Hamel's war-room number).

Layers 2 (stylometry) and 3 (LLM-as-judge pairwise) are scaffolded as
TODO hooks — implemented in Phase 2 before production gating is enabled.

Usage:
    python -m rag.twins.eval_twin <twin_id>
    python -m rag.twins.eval_twin <twin_id> --mock  # pure-arithmetic run,
                                                     # skips API calls
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

from rag.twins import corpus_search, storage
from rag.twins.reliability import compute_reliability, flatten_for_eval_scores
from rag.twins.schema import OperatorTwin, parse_twin, passes_production_gate

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-4-7"
LAYER1_THRESHOLD = 0.75
# Population archetype corpora are aggregated (ethnography + 3rd-person
# journalism, no single authoritative 1st-person source), so holdout
# cosine plateaus 2-3 pts lower than public-figure twins without the
# twin being worse for discovery. Use 0.72 when the underlying person
# spec sets `authorization: archetype_synthetic`.
LAYER1_THRESHOLD_ARCHETYPE = 0.72
LAYER1_PERCENTILE = 70  # p70 of cosine ≥ threshold
MAX_HOLDOUT = 20  # cap cost of the sweep
# Throttle between holdout iterations. Each iteration does ~5 Anthropic
# calls (_synthesize_question + up to 4 tool-use rounds in _ask_twin)
# each with a ~3k-token system prompt → ~15k input tokens per iter.
# Default org rate limit is 30k TPM for claude-opus-4-7, so we need at
# least 30s between iterations to stay comfortably under the limit.
HOLDOUT_THROTTLE_SEC = 30.0


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class HoldoutExample:
    chunk_id: str
    source_type: str
    source_date: str | None
    quote: str
    synthesized_question: str | None = None
    twin_answer: str | None = None
    cosine: float | None = None


@dataclass
class EvalReport:
    twin_id: str
    harness: str
    examples: list[HoldoutExample] = field(default_factory=list)
    summary: dict[str, float] = field(default_factory=dict)
    passed: bool | None = None
    notes: str = ""

    def to_json(self) -> dict:
        return {
            "twin_id": self.twin_id,
            "harness": self.harness,
            "passed": self.passed,
            "summary": self.summary,
            "notes": self.notes,
            "examples": [
                {
                    "chunk_id": e.chunk_id,
                    "source_type": e.source_type,
                    "source_date": e.source_date,
                    "quote_preview": (e.quote or "")[:160],
                    "question": e.synthesized_question,
                    "answer_preview": (e.twin_answer or "")[:160],
                    "cosine": e.cosine,
                }
                for e in self.examples
            ],
        }


# ---------------------------------------------------------------------------
# Question synthesis + twin answer
# ---------------------------------------------------------------------------


def _supports_temperature(model: str) -> bool:
    """Opus 4.x / Sonnet 4.6 removed the temperature parameter."""
    return not (model.startswith("claude-opus-4") or model.startswith("claude-sonnet-4-6"))


def _synthesize_question(quote: str, *, model: str, client) -> str:
    """Ask Claude to produce a discovery-style question for which `quote`
    would be a plausible answer. Temperature 0 — we want the question
    anchored in the quote, not creative (skipped for Opus 4.x which no
    longer accepts the param)."""
    kwargs: dict = {
        "model": model,
        "max_tokens": 200,
        "system": (
            "You write product-discovery questions. Given a quote from an "
            "interview, output the single open-ended question (in Portuguese, "
            "under 20 words) that an interviewer could have asked to elicit "
            "something very close to that quote. Output ONLY the question."
        ),
        "messages": [{"role": "user", "content": f"Quote:\n{quote}"}],
    }
    if _supports_temperature(model):
        kwargs["temperature"] = 0
    resp = client.messages.create(**kwargs)
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            return block.text.strip().strip('"')
    return ""


def _ask_twin(
    question: str,
    *,
    person_id: str,
    system_prompt: str,
    model: str,
    client,
    db_path: Path | None,
) -> str:
    """Single-turn twin reply, with the same corpus_search tool available
    as during live chat (consistency — evals measure the system we ship)."""
    from rag.twins.chat_with_twin import CORPUS_SEARCH_TOOL

    messages: list[dict] = [{"role": "user", "content": question}]
    for _ in range(4):  # bounded tool-use loop
        kwargs: dict = {
            "model": model,
            "max_tokens": 512,
            "system": system_prompt,
            "tools": [CORPUS_SEARCH_TOOL],
            "messages": messages,
        }
        if _supports_temperature(model):
            kwargs["temperature"] = 0.3
        resp = client.messages.create(**kwargs)
        messages.append(
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": b.text}
                    if getattr(b, "type", None) == "text"
                    else {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
                    for b in resp.content
                    if getattr(b, "type", None) in {"text", "tool_use"}
                ],
            }
        )
        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if resp.stop_reason != "tool_use" or not tool_uses:
            return "\n\n".join(
                b.text for b in resp.content if getattr(b, "type", None) == "text"
            ).strip()

        tool_results = []
        for tu in tool_uses:
            q = tu.input.get("query", "") if isinstance(tu.input, dict) else ""
            k = tu.input.get("k", 4) if isinstance(tu.input, dict) else 4
            hits = corpus_search.search(person_id, q, k=k, db_path=db_path)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(hits, ensure_ascii=False),
                }
            )
        messages.append({"role": "user", "content": tool_results})
    return ""


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _embed(text: str) -> list[float] | None:
    try:
        from rag.voyage_embeddings import generate_query_embedding, is_available
    except ImportError:
        return None
    if not is_available():
        return None
    return generate_query_embedding(text)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def run_holdout_cosine(
    twin_id: str,
    *,
    model: str = DEFAULT_MODEL,
    max_examples: int = MAX_HOLDOUT,
    mock: bool = False,
    db_path: Path | None = None,
) -> EvalReport:
    twin_dict = storage.get_twin(twin_id, db_path=db_path)
    if not twin_dict:
        raise SystemExit(f"Unknown twin_id={twin_id}")

    with storage.connect(db_path) as conn:
        row = conn.execute("SELECT person_id FROM twin WHERE id = ?", (twin_id,)).fetchone()
    if not row or not row["person_id"]:
        raise SystemExit(f"twin={twin_id} missing person_id in DB")
    person_id = row["person_id"]

    all_chunks = storage.list_chunks(person_id, include_holdout=True, db_path=db_path)
    holdouts = [c for c in all_chunks if c.get("holdout")]
    if not holdouts:
        raise SystemExit(
            f"No holdout chunks for person={person_id} — "
            "re-run ingest with --holdout-ratio > 0 or call storage.mark_holdout()"
        )

    holdouts = holdouts[:max_examples]
    report = EvalReport(twin_id=twin_id, harness="holdout_cosine")

    if mock:
        for c in holdouts:
            report.examples.append(
                HoldoutExample(
                    chunk_id=c["id"],
                    source_type=c["source_type"],
                    source_date=c.get("source_date"),
                    quote=c["text"],
                    synthesized_question="(mock) Fale sobre isso.",
                    twin_answer=c["text"],  # trivially identical → cosine 1.0
                    cosine=1.0,
                )
            )
        mock_person = storage.get_person(person_id, db_path=db_path) or {}
        return _finalize(
            report,
            twin_dict,
            authorization=mock_person.get("authorization", "pending"),
            db_path=db_path,
        )

    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError("anthropic SDK not installed") from e
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set — use --mock for offline testing")
    client = anthropic.Anthropic(api_key=key)

    from rag.twins.chat_with_twin import build_system_prompt

    system_prompt = build_system_prompt(twin_dict)

    import time

    # The build step just consumed ~30k tokens (full corpus to extract
    # structured twin) and we're already sitting on the TPM ceiling.
    # Wait the full minute before calling Anthropic again.
    log.info("cooling down 65s after build before eval starts")
    time.sleep(65)
    for i, c in enumerate(holdouts):
        if i > 0:
            # Stay under Anthropic org rate limit (30k input TPM for Opus
            # 4.x). Each iter ~15k input tokens, so 30s gap is safe.
            log.info(
                "throttle sleep %.1fs before holdout %d/%d",
                HOLDOUT_THROTTLE_SEC,
                i + 1,
                len(holdouts),
            )
            time.sleep(HOLDOUT_THROTTLE_SEC)
        question = _synthesize_question(c["text"], model=model, client=client)
        answer = _ask_twin(
            question,
            person_id=person_id,
            system_prompt=system_prompt,
            model=model,
            client=client,
            db_path=db_path,
        )

        quote_emb = _embed(c["text"])
        answer_emb = _embed(answer) if answer else None
        cos = _cosine(quote_emb or [], answer_emb or []) if quote_emb and answer_emb else 0.0

        report.examples.append(
            HoldoutExample(
                chunk_id=c["id"],
                source_type=c["source_type"],
                source_date=c.get("source_date"),
                quote=c["text"],
                synthesized_question=question,
                twin_answer=answer,
                cosine=cos,
            )
        )
        log.info("holdout eval chunk=%s cosine=%.3f", c["id"][:8], cos)

    person = storage.get_person(person_id, db_path=db_path) or {}
    return _finalize(
        report,
        twin_dict,
        authorization=person.get("authorization", "pending"),
        db_path=db_path,
    )


def _threshold_for(authorization: str) -> float:
    return (
        LAYER1_THRESHOLD_ARCHETYPE if authorization == "archetype_synthetic" else LAYER1_THRESHOLD
    )


def _finalize(
    report: EvalReport,
    twin_dict: dict,
    *,
    authorization: str = "pending",
    db_path: Path | None,
) -> EvalReport:
    threshold = _threshold_for(authorization)
    cos_values = [e.cosine for e in report.examples if e.cosine is not None]
    if cos_values:
        report.summary = {
            "n": float(len(cos_values)),
            "mean": statistics.fmean(cos_values),
            "median": statistics.median(cos_values),
            "p70": _percentile(cos_values, LAYER1_PERCENTILE),
            "p30_low": _percentile(cos_values, 30),
            "hit_rate_075": sum(1 for v in cos_values if v >= LAYER1_THRESHOLD) / len(cos_values),
            "threshold": threshold,
        }
        report.passed = report.summary["p70"] >= threshold
    else:
        report.summary = {}
        report.passed = False
        report.notes = "no cosine values computed (embedding disabled?)"

    # Persist scores back to the twin
    scores = twin_dict.get("eval_scores") or {}
    scores["holdout_cosine_p70"] = report.summary.get("p70", 0.0)
    scores["holdout_cosine_mean"] = report.summary.get("mean", 0.0)
    scores["holdout_cosine_n"] = report.summary.get("n", 0.0)

    # Kind-aware: operator twins get an additional domain-coherence signal
    # (Hamel's "domains coerentes c/ corpus" — war-room 2026-04-23).
    # Informational for now; future gate may require >=0.5 coverage.
    twin_obj = parse_twin(twin_dict)
    if isinstance(twin_obj, OperatorTwin):
        coverage = _operator_domain_coverage(twin_obj, twin_dict, db_path=db_path)
        scores["operator_domain_coverage"] = coverage
        report.summary["operator_domain_coverage"] = coverage
        log.info(
            "operator domain coverage twin=%s coverage=%.2f domains=%d",
            report.twin_id,
            coverage,
            len(twin_obj.operator.domains),
        )

    twin_dict["eval_scores"] = scores

    # Compute the unified reliability score from the fresh eval signals
    # plus corpus/schema state. Flat sub-scores go into eval_scores (so
    # existing dict[str, float] consumers keep working), and the full
    # breakdown — tier, gates, signals — is attached as a top-level
    # `reliability` field for richer consumers (webapp, registry).
    reliability = compute_reliability(twin_dict, authorization=authorization)
    scores.update(flatten_for_eval_scores(reliability))
    twin_dict["eval_scores"] = scores
    twin_dict["reliability"] = reliability.to_json()
    report.summary.update(flatten_for_eval_scores(reliability))
    report.summary["reliability_tier"] = reliability.tier

    if report.passed:
        twin_dict["status"] = _upgrade_status(twin_dict.get("status", "draft"))
    storage.upsert_twin(twin_dict, db_path=db_path)

    storage.log_eval(
        twin_id=report.twin_id,
        harness=report.harness,
        scores=report.summary,
        passed=report.passed,
        notes=report.notes,
        db_path=db_path,
    )

    # Cross-check the full production gate (corpus shape + eval score).
    # twin_obj was parsed earlier via parse_twin (kind-aware routing
    # through the twin_kind discriminator). Pass holdout_threshold so
    # archetype_synthetic twins use the softer 0.72 gate.
    full_ok, reasons = passes_production_gate(twin_obj, holdout_threshold=threshold)
    report.notes = "production gate: " + ("PASS" if full_ok else "FAIL — " + "; ".join(reasons))
    return report


def _operator_domain_coverage(
    twin: OperatorTwin,
    twin_dict: dict,
    *,
    db_path: Path | None,
) -> float:
    """Fraction of declared domains that find at least one textual hit in corpus.

    Cheap coherence check: if an operator claims `domains=[applied-ml, recsys]`
    but the corpus never mentions those topics, the twin is misaligned with its
    corpus (likely seeded from persona markdown without matching RAG sources).

    A domain matches a chunk when any whitespace-delimited fragment of the
    domain (split on hyphens / underscores) appears as a substring in the
    chunk text (case-insensitive). This is a weak signal by design — we
    don't want to false-negative when corpus uses synonyms. Used as an
    informational score; production-gating lives in schema.passes_production_gate.

    Returns 0.0 when there are no declared domains (fail-safe — caller
    handles the 0-domain case via schema gate).
    """
    domains = [d for d in twin.operator.domains if d]
    if not domains:
        return 0.0

    # Look up person_id for the twin so we can scan its corpus.
    with storage.connect(db_path) as conn:
        row = conn.execute("SELECT person_id FROM twin WHERE id = ?", (twin.id,)).fetchone()
    if not row or not row["person_id"]:
        return 0.0
    chunks = storage.list_chunks(row["person_id"], include_holdout=True, db_path=db_path)
    if not chunks:
        return 0.0

    corpus_lower = "\n".join((c.get("text") or "").lower() for c in chunks)
    hits = 0
    for domain in domains:
        fragments = [f for f in domain.lower().replace("_", "-").split("-") if len(f) >= 3]
        if not fragments:
            continue
        if any(frag in corpus_lower for frag in fragments):
            hits += 1
    return hits / len(domains)


def _upgrade_status(current: str) -> str:
    if current in {"draft", "eval_passed"}:
        return "eval_passed"
    return current


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (percentile / 100)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("twin_id")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--max-examples", type=int, default=MAX_HOLDOUT)
    p.add_argument("--mock", action="store_true", help="Skip API; trivial arithmetic")
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    report = run_holdout_cosine(
        args.twin_id,
        model=args.model,
        max_examples=args.max_examples,
        mock=args.mock,
        db_path=args.db,
    )
    print(json.dumps(report.to_json(), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
