"""
Twin schema — v2 (discriminated union).

Pydantic contract for synthetic twins. Two kinds share a common corpus +
linguistic + eval base and diverge on what they model:

    EntrepreneurTwin   — real non-digital entrepreneur (original use case,
                         war-room 2026-04-21). Keeps CompanyContext +
                         DecisionFingerprint.

    OperatorTwin       — Febrain persona operating inside a team
                         (war-room 2026-04-23, D-AIE-001). Carries the
                         operator contract from `_shared/templates/AGENT-PROFILE.md`:
                         team_role, home_team, serves, domains,
                         responsibilities, frameworks, communication_style.

The two are parsed via `twin_kind: Literal["entrepreneur", "operator"]`
discriminator so consumers always branch explicitly instead of guessing
from optional fields.

Schema v1 (all existing specs) is fully backward compatible: `twin_kind`
defaults to "entrepreneur", existing CompanyContext/DecisionFingerprint
stay required. Migration is idempotent via `scripts/migrate_twins_v1_v2.py`.

Unknown/contextual fields still go in `extensions: dict` as the escape hatch.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

try:
    from pydantic import BaseModel, Field
except ImportError:  # graceful degradation when pydantic isn't installed
    # The rag/ package already depends on fastapi, which pulls in pydantic in
    # production. Keep a minimal fallback so tests and CLI imports don't crash
    # in minimal environments — shape validation is still the production path.

    _FACTORY_MARKER = ("__factory__",)

    def Field(default=None, default_factory=None, **_kwargs):  # type: ignore[no-redef]
        if default_factory is not None:
            # Marker tuple so BaseModel.__init__ can call the factory per
            # instance — avoids sharing a single mutable default across all
            # instances of the same class.
            return (_FACTORY_MARKER, default_factory)
        return default

    class BaseModel:  # type: ignore[no-redef]
        def __init__(self, **data):
            # Apply per-instance defaults for factory fields first.
            for cls in type(self).__mro__:
                for key, val in cls.__dict__.items():
                    if (
                        isinstance(val, tuple)
                        and len(val) == 2
                        and val[0] is _FACTORY_MARKER
                        and key not in data
                    ):
                        data[key] = val[1]()
            for k, v in data.items():
                setattr(self, k, v)

        def model_dump(self) -> dict:
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

        @classmethod
        def model_validate(cls, data: dict):
            return cls(**data)


# ---------------------------------------------------------------------------
# Sub-profiles (shared)
# ---------------------------------------------------------------------------


Sector = Literal[
    "distribuicao",
    "clinicas",
    "manufatura",
    "varejo_fisico",
    "advocacia",
    "construcao",
    "agronegocio",
    "servicos_b2b",
    "outro",
]

RevenueRange = Literal["1-10M", "10-50M", "50-200M", "200M+"]
EmployeeRange = Literal["1-50", "50-200", "200-1000", "1000+"]
DigitalMaturity = Literal["legacy", "basic_erp", "some_saas", "digital_native"]
SuccessionStage = Literal["none", "planning", "in_progress", "completed"]

Formality = Literal["muito_informal", "informal", "neutro", "formal"]
RiskAppetite = Literal["conservative", "moderate", "aggressive"]
DecisionSpeed = Literal["slow_deliberate", "measured", "fast"]

TwinStatus = Literal["draft", "eval_passed", "production", "deprecated"]

TwinKind = Literal["entrepreneur", "operator"]


class CompanyContext(BaseModel):
    # Defaults keep the Pydantic model permissive when Opus tool-use output
    # omits a field. The production gate (passes_production_gate) still
    # flags thin company data, so we don't lose signal by accepting the
    # fallback values.
    sector: Sector = "outro"
    sub_sector: str = ""
    revenue_range: RevenueRange = "200M+"
    employees_range: EmployeeRange = "1000+"
    region: str = ""
    digital_maturity: DigitalMaturity = "basic_erp"
    family_business: bool = False
    succession_stage: SuccessionStage | None = None


class LinguisticProfile(BaseModel):
    formality: Formality = "neutro"
    regional_markers: list[str] = Field(default_factory=list)
    signature_phrases: list[str] = Field(default_factory=list)
    jargon_sector: list[str] = Field(default_factory=list)
    avoids: list[str] = Field(default_factory=list)
    avg_sentence_length: int = 0  # baseline from real corpus


class DecisionFingerprint(BaseModel):
    """The piece that makes discovery useful.

    Without a real decision fingerprint, a twin gives the LLM-average
    answer to any trade-off question — which is worthless for product
    discovery. Extracted from how the person talked about past choices
    in the corpus, not invented.
    """

    risk_appetite: RiskAppetite = "moderate"
    decision_speed: DecisionSpeed = "measured"
    primary_drivers: list[str] = Field(default_factory=list)
    deal_breakers: list[str] = Field(default_factory=list)
    trust_sources: list[str] = Field(default_factory=list)


class CorpusProvenance(BaseModel):
    source_count: int = 0
    total_tokens: int = 0
    source_types: dict[str, int] = Field(default_factory=dict)
    date_range_start: date | None = None
    date_range_end: date | None = None
    quality_score: float = 0.0  # 0-1 (see shreya's rubric in storage.py)


class OperatorProfile(BaseModel):
    """Contract of a Febrain persona operating inside a team.

    Mirrors `_shared/templates/AGENT-PROFILE.md` 1:1 so a twin can carry
    the persona's operational role (not just voice + decision). Populated
    either from the persona markdown frontmatter during spec generation
    (`scripts/persona_to_twin_spec.py`) or extracted from the corpus by
    `build_twin.py` when the spec leaves fields empty.

    Required semantics (enforced by `passes_production_gate` — see below):
        - `domains` non-empty
        - `responsibilities` has ≥ 3 entries

    Defaults keep the Pydantic model permissive when tool-use output omits
    a field, mirroring the pattern used in `CompanyContext`.
    """

    team_role: str = ""  # "Chief Applied ML & RecSys Strategist"
    home_team: str = ""  # "ai-engineering"
    serves: list[str] = Field(default_factory=list)  # ["ai-engineering"]
    domains: list[str] = Field(default_factory=list)  # ["applied-ml", "recsys", ...]
    responsibilities: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    communication_style: str = ""


# ---------------------------------------------------------------------------
# Top-level twins
# ---------------------------------------------------------------------------


class EntrepreneurTwin(BaseModel):
    """Synthetic twin of a real non-digital entrepreneur.

    `is_composite=True` means this twin was built from a cluster of real
    people sharing a decision fingerprint — this is the default per LGPD
    mitigation agreed in the war-room. Nominal twins (is_composite=False)
    require explicit written authorization OR a documented public-figure
    exception — see rag/twins/README.md §Ethics.
    """

    twin_kind: Literal["entrepreneur"] = "entrepreneur"

    id: str
    name_public: str | None = None  # None when anonymized
    archetype_label: str  # e.g. "Distribuidor SP 50M sucessão-em-curso"
    is_composite: bool = True

    company: CompanyContext
    linguistic: LinguisticProfile
    decision: DecisionFingerprint
    corpus: CorpusProvenance

    eval_scores: dict[str, float] = Field(default_factory=dict)
    last_updated: date | None = None
    status: TwinStatus = "draft"

    # Unified reliability breakdown (see rag/twins/reliability.py). Stored
    # as an opaque dict here to avoid a circular import; the canonical shape
    # is `ReliabilityScore.to_json()` and is regenerated on every eval run.
    reliability: dict | None = None

    # Escape hatch for odd cases — don't promote to top-level without a v3 bump.
    extensions: dict[str, str] = Field(default_factory=dict)


class OperatorTwin(BaseModel):
    """Synthetic twin of a Febrain persona operating inside a team.

    Replaces the markdown persona at runtime when `status=eval_passed` +
    manual approval. Until then, coexists with the persona (persona stays
    active, twin is available for draft inspection). See
    `ai-engineering/projects/rituals/war-room/2026-04-23-operator-twin-schema.md`
    for the ratification.
    """

    twin_kind: Literal["operator"] = "operator"

    id: str
    name_public: str | None = None  # Eugene Yan, Lenny Rachitsky, etc.
    archetype_label: str  # e.g. "Operator — Applied ML Senior Scientist"
    is_composite: bool = False  # operators are nominal by default (public figure)

    operator: OperatorProfile
    linguistic: LinguisticProfile
    decision: DecisionFingerprint  # operators also decide (architecture, priorities)
    corpus: CorpusProvenance

    eval_scores: dict[str, float] = Field(default_factory=dict)
    last_updated: date | None = None
    status: TwinStatus = "draft"

    # See `EntrepreneurTwin.reliability` — same opaque-dict pattern.
    reliability: dict | None = None

    extensions: dict[str, str] = Field(default_factory=dict)


# Discriminated union — Pydantic parses `twin_kind` to pick the concrete class.
# Use `parse_twin(data)` below to consume this from raw dicts (storage / JSON).
Twin = Annotated[
    EntrepreneurTwin | OperatorTwin,
    Field(discriminator="twin_kind"),
]


def parse_twin(data: dict) -> EntrepreneurTwin | OperatorTwin:
    """Parse a raw dict into the correct Twin subtype via `twin_kind`.

    Back-compat: dicts without `twin_kind` default to "entrepreneur", so
    existing `twins.db` rows and the 34 checked-in `rag/twins/persons/*.yaml`
    specs keep validating after this upgrade. New operator specs MUST set
    `twin_kind: operator` explicitly.
    """
    kind = data.get("twin_kind", "entrepreneur")
    if kind == "entrepreneur":
        return EntrepreneurTwin.model_validate(data)
    if kind == "operator":
        return OperatorTwin.model_validate(data)
    raise ValueError(f"unknown twin_kind={kind!r}; expected 'entrepreneur' or 'operator'")


# ---------------------------------------------------------------------------
# Gating helpers (used by eval_twin.py and chat_with_twin.py)
# ---------------------------------------------------------------------------


def passes_production_gate(
    twin: EntrepreneurTwin,
    *,
    holdout_threshold: float = 0.75,
) -> tuple[bool, list[str]]:
    """Check whether a twin may be promoted to `production`.

    Returns (passed, failure_reasons). Thresholds match Hamel's layer-1
    gate — holdout cosine only for MVP; layers 2+3 (stylometry, judge)
    are added in Phase 2 before public-facing discovery.

    `holdout_threshold` defaults to 0.75 (public-figure twins). For
    population archetypes (`authorization: archetype_synthetic`), the
    caller should pass 0.72 — corpus is aggregated ethnography +
    3rd-person journalism, so answer-quote cosine is inherently
    softer without the twin being worse for discovery use.
    """
    reasons: list[str] = []

    # Common: corpus + eval
    if twin.corpus.source_count < 3:
        reasons.append(f"corpus: source_count={twin.corpus.source_count} < 3")

    if len(twin.corpus.source_types) < 2:
        reasons.append(f"corpus: only {len(twin.corpus.source_types)} source type(s), need ≥2")

    if twin.corpus.total_tokens < 10_000:
        reasons.append(f"corpus: total_tokens={twin.corpus.total_tokens} < 10k")

    holdout = twin.eval_scores.get("holdout_cosine_p70")
    if holdout is None:
        reasons.append("eval: holdout_cosine_p70 missing (run eval_twin.py)")
    elif holdout < holdout_threshold:
        reasons.append(f"eval: holdout_cosine_p70={holdout:.3f} < {holdout_threshold:.2f}")

    # Kind-specific
    if isinstance(twin, OperatorTwin):
        if not twin.operator.domains:
            reasons.append("operator: domains empty — persona replacement requires ≥1 domain")
        if len(twin.operator.responsibilities) < 3:
            reasons.append(
                f"operator: only {len(twin.operator.responsibilities)} responsibilities, need ≥3"
            )

    return (len(reasons) == 0, reasons)
