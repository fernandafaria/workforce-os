"""
reliability — Unified confidence score for archetype/operator twins.

Combines the five existing quality signals (which today live spread across
`eval_scores`, `CorpusProvenance`, `authorization`, and schema completeness)
into a single 0-1 `reliability_overall` plus a typed breakdown so consumers
(registry, dispatch, webapp, monitoring) can filter or rank twins without
re-implementing the merge.

Dimensions and default weights:

    fidelity      40%   holdout_cosine_p70 normalized against the type-aware
                        threshold (0.75 public-figure / 0.72 archetype). The
                        only sub-score that measures output quality, so it
                        gets the largest weight.

    corpus        25%   chunk quality_score * log-volume * source diversity.
                        Guards against high-fidelity scores that are really
                        overfit on a thin corpus.

    coverage      15%   source_count vs minimum + date_range recency.
                        Separates "passed with 3 sources" from "passed with
                        15 recent sources".

    authorization 10%   LGPD signal: granted / public_figure = 1.0,
                        archetype_synthetic = 0.9, pending = 0.4, denied = 0.

    schema        10%   Required fields populated for the twin_kind (operator
                        domains/responsibilities; entrepreneur company/decision).

Tiers (overall):

    high        ≥ 0.80   safe for production discovery
    medium      ≥ 0.65   safe with caveats; surface tier in UI
    low         ≥ 0.45   draft only, surface "low confidence" warning
    unreliable  <  0.45  do not surface

The score is additive — `passes_production_gate()` in schema.py is unchanged
and remains the strict hard gate. `reliability` is meant for ranking and
UX, not for replacing the binary gate.

CLI:

    python -m rag.twins.reliability <twin_id>          # one twin
    python -m rag.twins.reliability --slug arch-b-...  # by person_id
    python -m rag.twins.reliability --all              # every twin in DB
    python -m rag.twins.reliability --all --json       # machine output
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from rag.twins import storage
from rag.twins.schema import (
    EntrepreneurTwin,
    OperatorTwin,
    parse_twin,
)

log = logging.getLogger(__name__)

# Schema version of the reliability score itself. Bump when weights or
# sub-formulas change in a way that would invalidate stored scores.
RELIABILITY_SCHEMA_VERSION = "1.0"

# Default weights — keep summing to 1.0. Exposed at module scope so callers
# can tune for an experiment without forking the formula.
DEFAULT_WEIGHTS: dict[str, float] = {
    "fidelity": 0.40,
    "corpus": 0.25,
    "coverage": 0.15,
    "authorization": 0.10,
    "schema": 0.10,
}

# Layer-1 cosine thresholds. Must mirror eval_twin.LAYER1_THRESHOLD* — the
# constants are duplicated rather than imported so this module stays
# importable without the heavier eval dependencies (anthropic, voyage).
HOLDOUT_THRESHOLD_DEFAULT = 0.75
HOLDOUT_THRESHOLD_ARCHETYPE = 0.72
HOLDOUT_FLOOR = 0.50  # below this, fidelity = 0 regardless of threshold

# Corpus heuristics.
CORPUS_VOLUME_FULL_TOKENS = 50_000  # log-scale full-score anchor
CORPUS_DIVERSITY_FULL_TYPES = 3
COVERAGE_FULL_SOURCES = 8

# Recency band edges, in years from today.
RECENCY_BANDS: list[tuple[float, float]] = [
    (2.0, 1.0),
    (5.0, 0.7),
    (10.0, 0.4),
]
RECENCY_FALLBACK = 0.2  # > oldest band edge or missing date

# Authorization signal.
AUTHORIZATION_SCORES: dict[str, float] = {
    "granted": 1.0,
    "public_figure": 1.0,
    "archetype_synthetic": 0.9,
    "pending": 0.4,
    "denied": 0.0,
}
AUTHORIZATION_FALLBACK = 0.3  # unknown value

# Tier cutoffs, descending.
TIER_CUTOFFS: list[tuple[float, str]] = [
    (0.80, "high"),
    (0.65, "medium"),
    (0.45, "low"),
]
TIER_FALLBACK = "unreliable"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ReliabilityScore:
    """Typed breakdown of a twin's reliability assessment.

    `overall` is the weighted combination of the five sub-scores. Each
    sub-score is 0-1; weights are exposed via `weights` for auditability.

    `gates` carries hard pass/fail booleans that mirror the existing
    `passes_production_gate()` checks so a consumer can read both the
    nuance (overall) and the hard line (gates) from one object.

    `signals` is the raw input data used to compute the score, kept for
    reproducibility — explains *why* a sub-score landed where it did.
    """

    overall: float
    tier: str
    fidelity: float
    corpus: float
    coverage: float
    authorization: float
    schema: float
    gates: dict[str, bool] = field(default_factory=dict)
    signals: dict[str, Any] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    schema_version: str = RELIABILITY_SCHEMA_VERSION
    computed_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Sub-score helpers
# ---------------------------------------------------------------------------


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _threshold_for_authorization(authorization: str) -> float:
    if authorization == "archetype_synthetic":
        return HOLDOUT_THRESHOLD_ARCHETYPE
    return HOLDOUT_THRESHOLD_DEFAULT


def _score_fidelity(eval_scores: dict[str, Any], threshold: float) -> tuple[float, dict[str, Any]]:
    p70_raw = eval_scores.get("holdout_cosine_p70")
    if p70_raw is None:
        return 0.0, {"holdout_cosine_p70": None, "threshold": threshold}
    try:
        p70 = float(p70_raw)
    except (TypeError, ValueError):
        return 0.0, {"holdout_cosine_p70": None, "threshold": threshold}

    if p70 <= HOLDOUT_FLOOR:
        score = 0.0
    elif p70 >= threshold:
        score = 1.0
    else:
        # Linear ramp between floor and threshold.
        score = (p70 - HOLDOUT_FLOOR) / (threshold - HOLDOUT_FLOOR)

    return _clamp(score), {
        "holdout_cosine_p70": p70,
        "threshold": threshold,
        "hit_rate_075": eval_scores.get("hit_rate_075"),
        "mean": eval_scores.get("holdout_cosine_mean"),
        "n": eval_scores.get("holdout_cosine_n"),
    }


def _score_corpus(corpus: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    chunk_quality = _clamp(float(corpus.get("quality_score", 0.0) or 0.0))

    total_tokens = int(corpus.get("total_tokens", 0) or 0)
    if total_tokens <= 0:
        volume = 0.0
    else:
        # log10 ramp; CORPUS_VOLUME_FULL_TOKENS hits 1.0.
        volume = math.log10(max(total_tokens, 1)) / math.log10(CORPUS_VOLUME_FULL_TOKENS)
        volume = _clamp(volume)

    source_types = corpus.get("source_types") or {}
    distinct_types = sum(1 for v in source_types.values() if v)
    diversity = _clamp(distinct_types / CORPUS_DIVERSITY_FULL_TYPES)

    score = (chunk_quality + volume + diversity) / 3
    return _clamp(score), {
        "chunk_quality": chunk_quality,
        "volume": volume,
        "diversity": diversity,
        "total_tokens": total_tokens,
        "distinct_source_types": distinct_types,
    }


def _parse_iso_date(raw: Any) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _years_since(d: date | None, *, today: date | None = None) -> float | None:
    if d is None:
        return None
    ref = today or date.today()
    return (ref - d).days / 365.25


def _score_coverage(
    corpus: dict[str, Any],
    *,
    today: date | None = None,
) -> tuple[float, dict[str, Any]]:
    source_count = int(corpus.get("source_count", 0) or 0)
    count_norm = _clamp(source_count / COVERAGE_FULL_SOURCES)

    end_date = _parse_iso_date(corpus.get("date_range_end"))
    years = _years_since(end_date, today=today)
    if years is None or years < 0:
        recency = RECENCY_FALLBACK
    else:
        recency = RECENCY_FALLBACK
        for edge, val in RECENCY_BANDS:
            if years <= edge:
                recency = val
                break

    score = (count_norm + recency) / 2
    return _clamp(score), {
        "source_count": source_count,
        "source_count_norm": count_norm,
        "date_range_end": end_date.isoformat() if end_date else None,
        "years_since_latest": round(years, 2) if years is not None else None,
        "recency": recency,
    }


def _score_authorization(authorization: str) -> tuple[float, dict[str, Any]]:
    raw = (authorization or "").strip()
    score = AUTHORIZATION_SCORES.get(raw, AUTHORIZATION_FALLBACK)
    return score, {"authorization": raw or None}


def _operator_required_fields(operator: dict[str, Any]) -> dict[str, bool]:
    return {
        "domains": bool(operator.get("domains")),
        "responsibilities": len(operator.get("responsibilities") or []) >= 3,
        "frameworks": bool(operator.get("frameworks")),
        "communication_style": bool((operator.get("communication_style") or "").strip()),
        "team_role": bool((operator.get("team_role") or "").strip()),
    }


def _entrepreneur_required_fields(twin_dict: dict[str, Any]) -> dict[str, bool]:
    company = twin_dict.get("company") or {}
    decision = twin_dict.get("decision") or {}
    linguistic = twin_dict.get("linguistic") or {}
    return {
        "sector": bool((company.get("sector") or "").strip())
        and company.get("sector") != "outro",
        "region": bool((company.get("region") or "").strip()),
        "primary_drivers": len(decision.get("primary_drivers") or []) >= 2,
        "trust_sources": len(decision.get("trust_sources") or []) >= 2,
        "signature_phrases": len(linguistic.get("signature_phrases") or []) >= 3,
        "jargon_sector": len(linguistic.get("jargon_sector") or []) >= 3,
    }


def _score_schema(twin_dict: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    kind = twin_dict.get("twin_kind", "entrepreneur")
    if kind == "operator":
        checks = _operator_required_fields(twin_dict.get("operator") or {})
    else:
        checks = _entrepreneur_required_fields(twin_dict)

    if not checks:
        return 0.0, {"twin_kind": kind, "satisfied": {}, "total": 0}
    satisfied = sum(1 for v in checks.values() if v)
    score = satisfied / len(checks)
    return _clamp(score), {
        "twin_kind": kind,
        "satisfied": checks,
        "ratio": f"{satisfied}/{len(checks)}",
    }


def _tier_for(overall: float) -> str:
    for cutoff, label in TIER_CUTOFFS:
        if overall >= cutoff:
            return label
    return TIER_FALLBACK


def _gate_checks(twin_dict: dict[str, Any], signals: dict[str, Any]) -> dict[str, bool]:
    corpus = twin_dict.get("corpus") or {}
    eval_scores = twin_dict.get("eval_scores") or {}
    source_types = corpus.get("source_types") or {}
    p70 = eval_scores.get("holdout_cosine_p70")
    threshold = signals.get("fidelity", {}).get("threshold", HOLDOUT_THRESHOLD_DEFAULT)

    return {
        "fidelity_gate": isinstance(p70, (int, float)) and p70 >= threshold,
        "corpus_gate": (
            int(corpus.get("source_count", 0) or 0) >= 3
            and sum(1 for v in source_types.values() if v) >= 2
            and int(corpus.get("total_tokens", 0) or 0) >= 10_000
        ),
        "authorization_gate": (
            (twin_dict.get("_authorization") or "") in {"granted", "public_figure", "archetype_synthetic"}
        ),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute_reliability(
    twin_dict: dict[str, Any],
    *,
    authorization: str | None = None,
    weights: dict[str, float] | None = None,
    today: date | None = None,
) -> ReliabilityScore:
    """Compute a ReliabilityScore for a serialized twin dict.

    `twin_dict` is the dict shape produced by `Twin.model_dump()`. The
    function does not require pydantic — it reads dict keys directly so it
    can run against both Pydantic models and raw JSON loaded from Supabase.

    `authorization` should be passed by the caller (it lives on
    `twin_person`, not on the twin schema itself). If omitted, defaults to
    "pending" — penalises an unknown twin appropriately.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    auth = (authorization or "pending").strip()
    twin_dict = {**twin_dict, "_authorization": auth}

    threshold = _threshold_for_authorization(auth)

    eval_scores = twin_dict.get("eval_scores") or {}
    corpus = twin_dict.get("corpus") or {}

    fidelity, sig_f = _score_fidelity(eval_scores, threshold)
    corpus_s, sig_c = _score_corpus(corpus)
    coverage, sig_cov = _score_coverage(corpus, today=today)
    auth_score, sig_a = _score_authorization(auth)
    schema_score, sig_s = _score_schema(twin_dict)

    overall = (
        w["fidelity"] * fidelity
        + w["corpus"] * corpus_s
        + w["coverage"] * coverage
        + w["authorization"] * auth_score
        + w["schema"] * schema_score
    )
    overall = _clamp(overall)

    signals = {
        "fidelity": sig_f,
        "corpus": sig_c,
        "coverage": sig_cov,
        "authorization": sig_a,
        "schema": sig_s,
    }

    return ReliabilityScore(
        overall=round(overall, 4),
        tier=_tier_for(overall),
        fidelity=round(fidelity, 4),
        corpus=round(corpus_s, 4),
        coverage=round(coverage, 4),
        authorization=round(auth_score, 4),
        schema=round(schema_score, 4),
        gates=_gate_checks(twin_dict, signals),
        signals=signals,
        weights=dict(w),
        computed_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
    )


def flatten_for_eval_scores(score: ReliabilityScore) -> dict[str, float]:
    """Project a ReliabilityScore into the flat dict[str, float] shape that
    the existing `eval_scores` field expects.

    Existing monitoring and registry code reads `eval_scores` as flat floats
    (because the schema declares `dict[str, float]`). We expose the same
    numbers there so older consumers keep working, while the rich breakdown
    lives in a separate `reliability` field.
    """
    return {
        "reliability_overall": score.overall,
        "reliability_fidelity": score.fidelity,
        "reliability_corpus": score.corpus,
        "reliability_coverage": score.coverage,
        "reliability_authorization": score.authorization,
        "reliability_schema": score.schema,
    }


# ---------------------------------------------------------------------------
# Authorization lookup (DB-side)
# ---------------------------------------------------------------------------


def _authorization_for_person(person_id: str | None, db_path: Path | None) -> str:
    if not person_id:
        return "pending"
    try:
        with storage.connect(db_path) as conn:
            row = conn.execute(
                "SELECT authorization FROM person WHERE id = ?",
                (person_id,),
            ).fetchone()
    except Exception:
        return "pending"
    if not row:
        return "pending"
    return row["authorization"] or "pending"


def score_twin_from_db(
    twin_id: str | None = None,
    slug: str | None = None,
    *,
    db_path: Path | None = None,
) -> ReliabilityScore | None:
    """Load a twin from SQLite, compute reliability, and return the score.

    Returns None when no matching twin is found. Either `twin_id` or `slug`
    (person_id) must be supplied.
    """
    if not twin_id and not slug:
        raise ValueError("score_twin_from_db requires twin_id or slug")

    twin_dict = (
        storage.get_twin(twin_id, db_path=db_path)
        if twin_id
        else storage.get_twin_by_slug(slug, db_path=db_path)
    )
    if not twin_dict:
        return None
    person_id = twin_dict.get("person_id") or slug
    auth = _authorization_for_person(person_id, db_path)
    return compute_reliability(twin_dict, authorization=auth)


def score_all_twins(*, db_path: Path | None = None) -> list[tuple[dict[str, Any], ReliabilityScore]]:
    """Compute reliability for every twin in the DB.

    Returns a list of (twin_dict, score) tuples sorted by descending
    overall score so the highest-confidence twins surface first.
    """
    twins = storage.list_twins(db_path=db_path)
    out: list[tuple[dict[str, Any], ReliabilityScore]] = []
    for twin_dict in twins:
        person_id = twin_dict.get("person_id")
        auth = _authorization_for_person(person_id, db_path)
        score = compute_reliability(twin_dict, authorization=auth)
        out.append((twin_dict, score))
    out.sort(key=lambda pair: pair[1].overall, reverse=True)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_row(twin_dict: dict[str, Any], score: ReliabilityScore) -> str:
    label = twin_dict.get("archetype_label") or twin_dict.get("name_public") or twin_dict.get("id")
    return (
        f"{score.tier:<10} {score.overall:>5.3f}  "
        f"fid={score.fidelity:.2f} corp={score.corpus:.2f} cov={score.coverage:.2f} "
        f"auth={score.authorization:.2f} sch={score.schema:.2f}  "
        f"{twin_dict.get('id', '?')}  {label}"
    )


def _print_human(items: Iterable[tuple[dict[str, Any], ReliabilityScore]]) -> None:
    header = (
        f"{'tier':<10} {'score':>5}  "
        f"fid   corp  cov   auth  sch    twin_id  archetype"
    )
    print(header)
    print("-" * len(header))
    for twin_dict, score in items:
        print(_format_row(twin_dict, score))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("twin_id", nargs="?", help="Score a single twin by id")
    group.add_argument("--slug", help="Score a single twin by person_id (slug)")
    group.add_argument("--all", action="store_true", help="Score every twin in the DB")
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.all:
        items = score_all_twins(db_path=args.db)
        if args.json:
            print(
                json.dumps(
                    [
                        {"twin": {"id": t.get("id"), "label": t.get("archetype_label")},
                         "score": s.to_json()}
                        for t, s in items
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            if not items:
                print("(no twins in DB)")
            else:
                _print_human(items)
        return 0

    score = score_twin_from_db(twin_id=args.twin_id, slug=args.slug, db_path=args.db)
    if score is None:
        log.error("no twin found (twin_id=%s slug=%s)", args.twin_id, args.slug)
        return 2
    if args.json:
        print(json.dumps(score.to_json(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(score.to_json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
