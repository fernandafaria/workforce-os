"""
run_all — batch orchestrator for the full twins pipeline over a set of specs.

For each `persons/<slug>.yaml` picked up under `--persons-dir`, runs:

    [optional] transcribe_spec  → drop .md transcripts under _corpus/<slug>/
    ingest_person.run           → chunk + embed into SQLite (Voyage)
    build_twin.build            → extract EntrepreneurTwin from corpus (Opus)
    eval_twin.run_holdout_cosine → Hamel layer-1 gate

Writes a consolidated JSON report at the end with per-person pass/fail plus
cost-control counters.

Safety / sanity
---------------
  * URL sanity check: warns on YouTube channel/show URLs (not episode URLs)
    so you don't accidentally unleash yt-dlp against a full channel.
  * `--limit N` caps the first N specs — always use this on first run.
  * `--dry-run` plans but does nothing (no network, no API).
  * `--skip-transcribe` lets you iterate build/eval once transcripts exist
    without re-fetching audio.
  * Every stage is try/except — a single person failing does not stop the
    batch.

Usage
-----
    # preview everything (no network)
    python -m rag.twins.run_all --dry-run

    # run first 3, skip transcription (transcripts already dropped manually)
    python -m rag.twins.run_all --limit 3 --skip-transcribe

    # one specific person end-to-end
    python -m rag.twins.run_all --only mrv-rubens-menin
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# URL heuristic: YouTube channel page vs specific episode.
# Specific episodes match one of these; anything else on youtube.com is
# probably a channel/playlist and yt-dlp would download everything.
_YT_EPISODE_RE = re.compile(
    r"youtube\.com/watch\?v=|youtu\.be/[\w\-]+|youtube\.com/shorts/",
    re.IGNORECASE,
)


@dataclass
class StageResult:
    ok: bool = False
    note: str = ""
    duration_sec: float = 0.0


@dataclass
class PersonRunReport:
    slug: str
    url_sanity: StageResult = field(default_factory=StageResult)
    transcribe: StageResult = field(default_factory=StageResult)
    ingest: StageResult = field(default_factory=StageResult)
    build: StageResult = field(default_factory=StageResult)
    eval_: StageResult = field(default_factory=StageResult)
    twin_id: str | None = None
    passed_gate: bool | None = None


# ---------------------------------------------------------------------------
# URL sanity
# ---------------------------------------------------------------------------


def check_url_sanity(spec_path: Path) -> StageResult:
    """Flag suspicious URLs — YouTube handles like @channel without an
    explicit episode path. Non-blocking (the real transcribe call will still
    refuse to pull a full channel), but surfaces the issue early so
    the operator replaces the URL before paying for a bad run.
    """
    from rag.twins.ingest_person import load_person_spec

    spec = load_person_spec(spec_path)
    suspicious: list[str] = []
    for src in spec.sources:
        if not src.url:
            continue
        u = src.url
        if ("youtube.com" in u or "youtu.be" in u) and not _YT_EPISODE_RE.search(u):
            suspicious.append(u)
    if suspicious:
        return StageResult(
            ok=False,
            note=f"{len(suspicious)} URL(s) look channel-level (need episode): {suspicious[:3]}",
        )
    return StageResult(ok=True, note="ok")


# ---------------------------------------------------------------------------
# Stage wrappers — each is defensive and returns a StageResult
# ---------------------------------------------------------------------------


def _timed(fn):
    """Decorator converting raised exceptions into a failed StageResult with
    stage duration still reported."""

    def wrapper(*args, **kwargs) -> StageResult:
        t0 = time.monotonic()
        try:
            note = fn(*args, **kwargs) or "ok"
            return StageResult(ok=True, note=str(note)[:300], duration_sec=time.monotonic() - t0)
        except Exception as e:
            return StageResult(
                ok=False,
                note=f"{type(e).__name__}: {e}"[:300],
                duration_sec=time.monotonic() - t0,
            )

    return wrapper


@_timed
def _stage_transcribe(spec_path: Path, *, dry_run: bool) -> str:
    from rag.twins.transcribe import transcribe_spec

    report = transcribe_spec(spec_path, dry_run=dry_run)
    return (
        f"attempted={report.attempted} written={report.written} "
        f"unsupported={report.skipped_unsupported} failed={report.failed}"
    )


@_timed
def _stage_ingest(spec_path: Path, *, dry_run: bool) -> str:
    from rag.twins.ingest_person import run as ingest_run

    report = ingest_run(spec_path, dry_run=dry_run)
    return f"chunks={report.chunks_inserted} holdout={report.holdout_marked} tokens={report.total_tokens}"


@_timed
def _stage_build(person_id: str, *, dry_run: bool) -> str:
    from rag.twins.build_twin import build

    twin = build(person_id, dry_run=dry_run)
    return f"twin_id={twin.id} status={twin.status}"


@_timed
def _stage_eval(twin_id: str, *, mock: bool) -> str:
    from rag.twins.eval_twin import run_holdout_cosine

    report = run_holdout_cosine(twin_id, mock=mock)
    return f"passed={report.passed} summary={report.summary}"


# ---------------------------------------------------------------------------
# Spec discovery
# ---------------------------------------------------------------------------


def discover_specs(persons_dir: Path, only: list[str] | None) -> list[Path]:
    candidates = sorted(p for p in persons_dir.glob("*.yaml") if not p.name.startswith("example"))
    if only:
        allowed = set(only)
        return [p for p in candidates if p.stem in allowed]
    return candidates


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_one(
    spec_path: Path,
    *,
    dry_run: bool,
    skip_transcribe: bool,
    skip_build_eval: bool,
    eval_mock: bool,
    strict_url_check: bool = False,
) -> PersonRunReport:
    slug = spec_path.stem
    rep = PersonRunReport(slug=slug)
    log.info("====== %s ======", slug)

    rep.url_sanity = check_url_sanity(spec_path)
    if not rep.url_sanity.ok:
        log.warning("[%s] url sanity: %s", slug, rep.url_sanity.note)
        if strict_url_check and not dry_run and not skip_transcribe:
            # Hard-fail the person. Avoids paying for a yt-dlp run that
            # would try to download a whole channel. Operator must tighten
            # the URL to a specific episode before rerunning.
            rep.transcribe = StageResult(
                ok=False,
                note="strict_url_check: refusing to transcribe channel-level URLs",
            )
            return rep

    if not skip_transcribe:
        rep.transcribe = _stage_transcribe(spec_path, dry_run=dry_run)
        log.info("[%s] transcribe: %s", slug, rep.transcribe.note)
    else:
        rep.transcribe = StageResult(ok=True, note="skipped")

    rep.ingest = _stage_ingest(spec_path, dry_run=dry_run)
    log.info("[%s] ingest: %s", slug, rep.ingest.note)

    if skip_build_eval or dry_run:
        return rep

    if not rep.ingest.ok:
        log.warning("[%s] ingest failed; skipping build+eval", slug)
        return rep

    rep.build = _stage_build(slug, dry_run=dry_run)
    log.info("[%s] build: %s", slug, rep.build.note)
    if rep.build.ok:
        # Parse twin_id out of the note for eval
        match = re.search(r"twin_id=([a-f0-9\-]+)", rep.build.note)
        if match:
            rep.twin_id = match.group(1)
            rep.eval_ = _stage_eval(rep.twin_id, mock=eval_mock)
            log.info("[%s] eval: %s", slug, rep.eval_.note)
            passed_match = re.search(r"passed=(True|False)", rep.eval_.note)
            if passed_match:
                rep.passed_gate = passed_match.group(1) == "True"
    return rep


def run_all(
    persons_dir: Path,
    *,
    only: list[str] | None,
    limit: int | None,
    dry_run: bool,
    skip_transcribe: bool,
    skip_build_eval: bool,
    eval_mock: bool,
    out_path: Path | None,
    strict_url_check: bool = False,
) -> list[PersonRunReport]:
    specs = discover_specs(persons_dir, only)
    if limit:
        specs = specs[:limit]

    log.info(
        "running %d specs (dry_run=%s skip_transcribe=%s)", len(specs), dry_run, skip_transcribe
    )

    reports: list[PersonRunReport] = []
    for spec_path in specs:
        try:
            rep = run_one(
                spec_path,
                dry_run=dry_run,
                skip_transcribe=skip_transcribe,
                skip_build_eval=skip_build_eval,
                eval_mock=eval_mock,
                strict_url_check=strict_url_check,
            )
        except Exception as e:
            log.exception("unhandled failure on %s", spec_path)
            rep = PersonRunReport(slug=spec_path.stem)
            rep.ingest = StageResult(ok=False, note=f"fatal: {e}")
        reports.append(rep)

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps([asdict(r) for r in reports], ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        log.info("wrote report %s", out_path)
    return reports


def _summarize(reports: list[PersonRunReport]) -> dict:
    total = len(reports)
    ingested = sum(1 for r in reports if r.ingest.ok)
    built = sum(1 for r in reports if r.build.ok)
    passed = sum(1 for r in reports if r.passed_gate)
    sanity_warnings = sum(1 for r in reports if not r.url_sanity.ok)
    return {
        "total_specs": total,
        "url_sanity_warnings": sanity_warnings,
        "ingested_ok": ingested,
        "built_ok": built,
        "eval_gate_passed": passed,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--persons-dir", type=Path, default=Path("rag/twins/persons"))
    p.add_argument(
        "--only",
        nargs="*",
        help="slug(s) to run (matches <slug>.yaml). default: all non-example",
    )
    p.add_argument("--limit", type=int, default=None, help="cap first N specs (cost control)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--skip-transcribe", action="store_true")
    p.add_argument(
        "--skip-build-eval",
        action="store_true",
        help="stop after ingest — useful when you only want to refresh corpus",
    )
    p.add_argument(
        "--eval-mock",
        action="store_true",
        help="use eval_twin --mock (no Anthropic/Voyage API); for plumbing tests",
    )
    p.add_argument(
        "--strict-url-check",
        action="store_true",
        help="hard-fail transcription if any URL looks channel-level "
        "(recommended in CI/workflow_dispatch full mode)",
    )
    p.add_argument("--out", type=Path, default=Path("rag/twins/run_all_report.json"))
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    from rag.twins.load_repo_env import load_repo_env

    load_repo_env()
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    reports = run_all(
        args.persons_dir,
        only=args.only,
        limit=args.limit,
        dry_run=args.dry_run,
        skip_transcribe=args.skip_transcribe,
        skip_build_eval=args.skip_build_eval,
        eval_mock=args.eval_mock,
        out_path=args.out,
        strict_url_check=args.strict_url_check,
    )
    summary = _summarize(reports)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    any_failed = any(not r.ingest.ok for r in reports) and not args.dry_run
    return 2 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
