#!/usr/bin/env python3
"""
Workforce OS — Batch twin graduation pipeline.

Walks every public_figure twin that hasn't yet been promoted and drives
the full creation pipeline against the Supabase edge functions:

    ingest  →  synth  →  (optional) interview  →  eval  →  publish

A twin is "graduated" once its last eval clears the threshold and we set
``twin.status = 'eval_passed'``.

Idempotent: each stage individually checks whether its work is already
done (via the existing endpoints' state). Re-running this script picks
up where the previous run stopped.

Usage
-----
    SUPABASE_URL=...                            \\
    SUPABASE_SERVICE_ROLE_KEY=...               \\
    python scripts/graduate_public_figures.py   \\
        --concurrency 3                         \\
        --threshold 0.50                        \\
        --no-interview                          \\
        --dry-run

Cost notes (estimate per twin):
- Voyage embeds (corpus + 2 per eval probe): ~$0.05
- Anthropic synth (~21k tokens in, 1.6k out): ~$0.30
- Anthropic interview (8 turns): ~$0.07  [skipped with --no-interview]
- Anthropic eval (4 probes): ~$0.10
- TOTAL per twin: ~$0.52  ($0.45 with --no-interview)
For ~63 candidates: ~$33 ($28 with --no-interview).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import httpx
from supabase import Client, create_client

log = logging.getLogger("graduate")

EDGE_INGEST = "twin-corpus-ingest"
EDGE_SYNTH = "twin-synthesize"
EDGE_INTERVIEW = "twin-interview"
EDGE_EVAL = "twin-eval"

SAM_ALTMAN_TWIN_ID = "279da0b1-3ffe-44b7-a7d2-7d45fb575d52"


@dataclass
class TwinResult:
    twin_id: str
    name: str
    ingested_chunks: int = 0
    synthesized: bool = False
    interviewed: bool = False
    eval_passed: Optional[bool] = None
    eval_score: Optional[float] = None
    published: bool = False
    errors: List[str] = field(default_factory=list)
    elapsed_s: float = 0.0


@dataclass
class Config:
    supabase_url: str
    service_role_key: str
    concurrency: int = 3
    threshold: float = 0.50
    do_interview: bool = True
    dry_run: bool = False
    only_slug: Optional[str] = None
    only_id: Optional[str] = None
    limit: Optional[int] = None


def _edge(cfg: Config, slug: str) -> str:
    return f"{cfg.supabase_url.rstrip('/')}/functions/v1/{slug}"


def _headers(cfg: Config) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.service_role_key}",
    }


def list_candidates(client: Client, cfg: Config) -> List[Dict[str, Any]]:
    """Public-figure twins that still need graduation work."""
    q = (
        client.table("twin")
        .select("id, person_id, archetype_label, status, schema_json")
        .eq("status", "draft")
    )
    rows = q.execute().data or []

    person_ids = list({r["person_id"] for r in rows if r.get("person_id")})
    persons: Dict[str, Dict[str, Any]] = {}
    if person_ids:
        pr = (
            client.table("twin_person")
            .select("id, name_public, authorization")
            .in_("id", person_ids)
            .execute()
        )
        persons = {p["id"]: p for p in (pr.data or [])}

    candidates: List[Dict[str, Any]] = []
    for r in rows:
        pid = r.get("person_id")
        person = persons.get(pid) or {}
        if person.get("authorization") != "public_figure":
            continue
        if cfg.only_slug and pid != cfg.only_slug:
            continue
        if cfg.only_id and r["id"] != cfg.only_id:
            continue
        # Skip Sam Altman — already graduated, here for safety.
        if r["id"] == SAM_ALTMAN_TWIN_ID and not (cfg.only_id or cfg.only_slug):
            continue
        candidates.append(
            {
                "twin_id": r["id"],
                "person_id": pid,
                "name": person.get("name_public") or "Unknown",
                "archetype_label": r.get("archetype_label"),
                "schema_json": r.get("schema_json") or {},
            }
        )

    if cfg.limit:
        candidates = candidates[: cfg.limit]
    return candidates


async def _post(
    cfg: Config, edge: str, body: Dict[str, Any], timeout_s: float
) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(_edge(cfg, edge), headers=_headers(cfg), json=body)
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text[:500]}
            data["status_code"] = resp.status_code
            return data
    except Exception as e:
        return {"error": str(e), "status_code": -1}


async def stage_ingest(cfg: Config, twin_id: str) -> Dict[str, Any]:
    return await _post(cfg, EDGE_INGEST, {"twin_id": twin_id}, timeout_s=180)


async def stage_synth(cfg: Config, twin_id: str) -> Dict[str, Any]:
    return await _post(cfg, EDGE_SYNTH, {"twin_id": twin_id}, timeout_s=180)


async def stage_interview(cfg: Config, twin_id: str) -> Dict[str, Any]:
    return await _post(
        cfg, EDGE_INTERVIEW, {"twin_id": twin_id, "num_questions": 6}, timeout_s=180
    )


async def stage_eval(cfg: Config, twin_id: str, threshold: float) -> Dict[str, Any]:
    return await _post(
        cfg,
        EDGE_EVAL,
        {"twin_id": twin_id, "num_probes": 4, "threshold": threshold},
        timeout_s=180,
    )


def publish_if_passed(client: Client, twin_id: str) -> bool:
    """Mirrors api/twins/pipeline.TwinPipeline.publish without the LLM bits."""
    last = (
        client.table("twin_eval_run")
        .select("id, passed")
        .eq("twin_id", twin_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not last.data:
        return False
    if not last.data[0].get("passed"):
        return False
    client.table("twin").update({"status": "eval_passed"}).eq("id", twin_id).execute()
    return True


async def graduate_one(
    cfg: Config, client: Client, cand: Dict[str, Any]
) -> TwinResult:
    twin_id = cand["twin_id"]
    name = cand["name"]
    result = TwinResult(twin_id=twin_id, name=name)
    start = time.monotonic()

    log.info(f"[{name}] starting graduation")

    if cfg.dry_run:
        log.info(f"[{name}] DRY RUN — would ingest+synth+eval+publish")
        result.elapsed_s = time.monotonic() - start
        return result

    # 1) Ingest
    r_ingest = await stage_ingest(cfg, twin_id)
    if r_ingest.get("status_code") != 200:
        result.errors.append(f"ingest: {r_ingest.get('error') or r_ingest}")
        result.elapsed_s = time.monotonic() - start
        return result
    result.ingested_chunks = int(r_ingest.get("chunks_created") or 0)
    log.info(f"[{name}] ingest: {result.ingested_chunks} new chunks")

    # If still zero chunks after ingest AND none existed before, can't synth.
    total_chunks_after = (
        client.table("twin_corpus_chunk")
        .select("id", count="exact")
        .eq("person_id", cand["person_id"])
        .execute()
        .count
        or 0
    )
    if total_chunks_after == 0:
        result.errors.append("no corpus chunks available after ingest")
        result.elapsed_s = time.monotonic() - start
        return result

    # 2) Synth (skip if already done)
    has_synth = bool((cand.get("schema_json") or {}).get("synthesized"))
    if not has_synth:
        r_synth = await stage_synth(cfg, twin_id)
        if r_synth.get("status_code") != 200:
            result.errors.append(f"synth: {r_synth.get('error') or r_synth}")
            result.elapsed_s = time.monotonic() - start
            return result
        result.synthesized = True
        log.info(f"[{name}] synth: ok")
    else:
        result.synthesized = True
        log.info(f"[{name}] synth: already done, skipping")

    # 3) Interview (optional)
    if cfg.do_interview:
        r_int = await stage_interview(cfg, twin_id)
        if r_int.get("status_code") != 200:
            result.errors.append(f"interview: {r_int.get('error') or r_int}")
            # interview failure is not fatal — continue to eval
        else:
            result.interviewed = True
            log.info(f"[{name}] interview: ok")

    # 4) Eval
    r_eval = await stage_eval(cfg, twin_id, cfg.threshold)
    if r_eval.get("status_code") != 200:
        result.errors.append(f"eval: {r_eval.get('error') or r_eval}")
        result.elapsed_s = time.monotonic() - start
        return result
    result.eval_passed = bool(r_eval.get("passed"))
    score = r_eval.get("score")
    result.eval_score = float(score) if score is not None else None
    log.info(
        f"[{name}] eval: score={result.eval_score:.3f} "
        f"passed={result.eval_passed} threshold={cfg.threshold}"
    )

    # 5) Publish gate
    if result.eval_passed:
        if publish_if_passed(client, twin_id):
            result.published = True
            log.info(f"[{name}] PUBLISHED → eval_passed")
        else:
            result.errors.append("publish gate failed")

    result.elapsed_s = time.monotonic() - start
    return result


async def run_batch(
    cfg: Config, client: Client, candidates: List[Dict[str, Any]]
) -> List[TwinResult]:
    semaphore = asyncio.Semaphore(cfg.concurrency)
    results: List[TwinResult] = []

    async def worker(c: Dict[str, Any]) -> TwinResult:
        async with semaphore:
            return await graduate_one(cfg, client, c)

    tasks = [asyncio.create_task(worker(c)) for c in candidates]
    for t in asyncio.as_completed(tasks):
        r = await t
        results.append(r)
    return results


def write_report(results: List[TwinResult], path: str) -> None:
    payload = {
        "total": len(results),
        "published": sum(1 for r in results if r.published),
        "eval_passed": sum(1 for r in results if r.eval_passed),
        "with_errors": sum(1 for r in results if r.errors),
        "rows": [asdict(r) for r in results],
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"\nReport written to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch graduate public_figure twins.")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=0.50)
    parser.add_argument(
        "--no-interview", action="store_true", help="Skip Stage 4 (saves ~$0.07/twin)"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only-slug", type=str, help="Process only this person_id")
    parser.add_argument("--only-id", type=str, help="Process only this twin uuid")
    parser.add_argument("--limit", type=int, help="Hard cap on number processed")
    parser.add_argument("--report", type=str, default="graduate_report.json")
    parser.add_argument("--log-level", type=str, default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set", file=sys.stderr)
        return 2

    cfg = Config(
        supabase_url=url,
        service_role_key=key,
        concurrency=args.concurrency,
        threshold=args.threshold,
        do_interview=not args.no_interview,
        dry_run=args.dry_run,
        only_slug=args.only_slug,
        only_id=args.only_id,
        limit=args.limit,
    )

    client = create_client(cfg.supabase_url, cfg.service_role_key)
    candidates = list_candidates(client, cfg)

    print(
        f"Found {len(candidates)} eligible public_figure twin(s). "
        f"dry_run={cfg.dry_run} concurrency={cfg.concurrency} threshold={cfg.threshold} "
        f"interview={cfg.do_interview}"
    )
    if not candidates:
        return 0

    results = asyncio.run(run_batch(cfg, client, candidates))

    print("\n=== Graduation summary ===")
    print(f"  total processed:  {len(results)}")
    print(f"  published:        {sum(1 for r in results if r.published)}")
    print(f"  eval passed:      {sum(1 for r in results if r.eval_passed)}")
    print(f"  with errors:      {sum(1 for r in results if r.errors)}")
    if any(r.errors for r in results):
        print("\nErrors:")
        for r in results:
            if r.errors:
                print(f"  - {r.name} ({r.twin_id}): {r.errors[0]}")

    write_report(results, args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
