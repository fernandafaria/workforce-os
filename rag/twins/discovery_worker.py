"""
discovery_worker — orchestrates the Discovery pipeline against Supabase.

Two modes:

    python -m rag.twins.discovery_worker drain-queue
        Loop: claim_discovery_run() → run discover_sources backends →
        insert candidates → mark run completed. Stops when claim returns
        nothing (queue empty) or after --max-runs iterations.

    python -m rag.twins.discovery_worker apply-approved
        Find every candidate with review_status='approved' AND applied_at
        IS NULL, group by slug, append entries into rag/twins/persons/<slug>.yaml,
        and mark applied_at + applied_commit_sha. Caller (the GH Actions
        workflow) handles git commit + push + PR.

This module talks to PostgREST directly via httpx — same pattern as
scripts/seed_skill_schemas.py, no supabase-py dependency. Authenticates
with SUPABASE_SERVICE_ROLE_KEY (RLS is bypassed by the policy carved out
in migration 089).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx
import yaml

# Reuse the discover_sources backends directly. Importing instead of
# shelling out gives us structured DiscoveredSource objects (no YAML
# round-trip) and lets exceptions propagate cleanly.
from rag.twins.discover_sources import (
    DiscoveredSource,
    filter_maigret,
    run_firecrawl_podcasts,
    run_itunes_podcasts,
    run_maigret,
    run_wayback,
)

log = logging.getLogger("discovery_worker")

REPO_ROOT = Path(__file__).resolve().parents[2]
PERSONS_DIR = REPO_ROOT / "rag" / "twins" / "persons"


# ─── Supabase client (PostgREST over httpx) ───────────────────────────────────


@dataclass
class Supa:
    url: str
    key: str

    @classmethod
    def from_env(cls) -> Supa:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:
            raise SystemExit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        return cls(url=url, key=key)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        r = httpx.post(
            f"{self.url}/rest/v1/rpc/{name}",
            headers=self._headers,
            json=payload,
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def insert(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        r = httpx.post(
            f"{self.url}/rest/v1/{table}",
            headers={
                **self._headers,
                "Prefer": "return=representation,resolution=merge-duplicates",
            },
            json=rows,
            timeout=60.0,
        )
        r.raise_for_status()
        return r.json()

    def update(self, table: str, match: dict[str, Any], patch: dict[str, Any]) -> Any:
        params = {f"{k}": f"eq.{v}" for k, v in match.items()}
        r = httpx.patch(
            f"{self.url}/rest/v1/{table}",
            headers=self._headers,
            params=params,
            json=patch,
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def select(
        self,
        table: str,
        *,
        filters: dict[str, str] | None = None,
        select: str = "*",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"select": select}
        if filters:
            params.update(filters)
        if limit:
            params["limit"] = str(limit)
        r = httpx.get(
            f"{self.url}/rest/v1/{table}",
            headers=self._headers,
            params=params,
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()


# ─── drain-queue ──────────────────────────────────────────────────────────────


def _url_hash(url: str) -> str:
    return sha256(url.encode("utf-8")).hexdigest()[:16]


def execute_run(run: dict[str, Any]) -> list[DiscoveredSource]:
    """Run all enabled backends for a single discovery_runs row."""
    # Normalize HTTPS_PROXY / YTDLP_PROXY if pasted in Webshare-list format
    # (host:port:user:pass). Idempotent. See rag/twins/proxy_utils.py.
    from rag.twins.proxy_utils import normalize_proxy_env

    normalize_proxy_env()
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("YTDLP_PROXY")
    found: list[DiscoveredSource] = []
    seen: set[str] = set()

    def _merge(items: list[DiscoveredSource]) -> None:
        for s in items:
            if s.url in seen:
                continue
            seen.add(s.url)
            found.append(s)

    if not run.get("skip_maigret"):
        for username in run.get("usernames") or []:
            try:
                report = run_maigret(username, proxy=proxy)
                _merge(filter_maigret(report))
            except FileNotFoundError as e:
                # Maigret not installed → log and skip; other backends still run.
                log.warning("maigret unavailable: %s", e)
                break
            except Exception as e:
                log.error("maigret failed for %s: %s", username, e)

    for domain in run.get("wayback_domains") or []:
        try:
            _merge(run_wayback(domain))
        except Exception as e:
            log.error("wayback failed for %s: %s", domain, e)

    if run.get("enable_itunes"):
        try:
            _merge(run_itunes_podcasts(run["name"]))
        except Exception as e:
            log.error("itunes failed: %s", e)

    if run.get("enable_firecrawl_podcasts"):
        try:
            _merge(run_firecrawl_podcasts(run["name"]))
        except Exception as e:
            log.error("firecrawl-podcasts failed: %s", e)

    return found


def candidates_payload(
    run: dict[str, Any], sources: list[DiscoveredSource]
) -> list[dict[str, Any]]:
    return [
        {
            "run_id": run["id"],
            "company_id": run["company_id"],
            "user_id": run["user_id"],
            "site_name": s.site_name,
            "url": s.url,
            "url_hash": _url_hash(s.url),
            "source_type": s.type,
            "tags": s.tags or [],
            "backend": _normalize_backend(s.backend),
            "notes": s.notes,
        }
        for s in sources
    ]


def _normalize_backend(backend: str) -> str:
    """discover_sources uses 'firecrawl-podcasts' but the table CHECK
    constraint accepts only the canonical four. Strip the suffix."""
    if backend.startswith("firecrawl"):
        return "firecrawl"
    if backend.startswith("itunes"):
        return "itunes"
    return backend


def drain_queue(supa: Supa, *, max_runs: int, gh_run_id: int | None) -> int:
    """Claim and process queued discovery_runs until empty or max reached."""
    processed = 0
    while processed < max_runs:
        claimed = supa.rpc("claim_discovery_run", {"p_gh_run_id": gh_run_id})
        if not claimed:
            log.info("queue empty — drained %d run(s)", processed)
            return processed
        # PostgREST returns scalar function results as a list-of-rows.
        run = claimed[0] if isinstance(claimed, list) else claimed
        log.info("claimed run id=%s slug=%s", run["id"], run["slug"])

        try:
            sources = execute_run(run)
            payload = candidates_payload(run, sources)
            inserted = supa.insert("discovery_candidates", payload) if payload else []
            supa.update(
                "discovery_runs",
                {"id": run["id"]},
                {
                    "status": "completed",
                    "completed_at": "now()",
                    "candidates_count": len(inserted),
                },
            )
            log.info("run %s done — %d candidate(s) inserted", run["id"], len(inserted))
        except Exception as e:
            log.exception("run %s failed", run["id"])
            supa.update(
                "discovery_runs",
                {"id": run["id"]},
                {
                    "status": "failed",
                    "completed_at": "now()",
                    "error_message": str(e)[:500],
                },
            )

        processed += 1

    log.info("hit max_runs=%d, exiting", max_runs)
    return processed


# ─── apply-approved ───────────────────────────────────────────────────────────


def _candidate_to_spec_entry(c: dict[str, Any]) -> dict[str, Any]:
    """Translate a discovery_candidates row into the SourceSpec dict
    that rag/twins/persons/<slug>.yaml expects."""
    entry: dict[str, Any] = {
        "url": c["url"],
        "title": c["site_name"],
        "type": c["source_type"],
        "first_person": True,
    }
    if c.get("notes"):
        entry["discovery_note"] = c["notes"]
    return entry


def _spec_path_for(slug: str) -> Path:
    return PERSONS_DIR / f"{slug}.yaml"


def _existing_urls(spec_path: Path) -> set[str]:
    if not spec_path.exists():
        return set()
    data = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    return {
        s.get("url") for s in (data.get("sources") or []) if isinstance(s, dict) and s.get("url")
    }


def _append_to_spec(spec_path: Path, entries: list[dict[str, Any]]) -> None:
    """Append candidate entries to the spec's `sources:` list, preserving
    file order. Uses safe_load + safe_dump round-trip."""
    data = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    sources = list(data.get("sources") or [])
    sources.extend(entries)
    data["sources"] = sources
    spec_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )


def apply_approved(supa: Supa) -> dict[str, list[str]]:
    """Drain approved-but-not-yet-applied candidates, edit YAMLs in place.

    Returns {slug: [candidate_ids]} so the caller (workflow) knows which
    files changed. Sets applied_at=now() but leaves applied_commit_sha and
    applied_pr_url NULL — those are filled in by a follow-up `stamp-applied`
    call once the workflow has the values.
    """
    rows = supa.select(
        "discovery_candidates",
        filters={
            "review_status": "eq.approved",
            "applied_at": "is.null",
        },
        select="id,run_id,url,site_name,source_type,notes,discovery_runs(slug)",
        limit=500,
    )
    if not rows:
        log.info("no approved candidates pending application")
        return {}

    # Group by slug.
    by_slug: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        slug = (r.get("discovery_runs") or {}).get("slug")
        if not slug:
            log.warning("candidate %s has no slug join — skipping", r["id"])
            continue
        by_slug.setdefault(slug, []).append(r)

    applied: dict[str, list[str]] = {}
    for slug, candidates in by_slug.items():
        spec = _spec_path_for(slug)
        if not spec.exists():
            log.warning(
                "spec missing for slug=%s — skipping %d candidate(s)", slug, len(candidates)
            )
            continue

        existing = _existing_urls(spec)
        new_entries = []
        applied_ids = []
        for c in candidates:
            if c["url"] in existing:
                # Already present — mark as duplicate to skip future processing.
                supa.update(
                    "discovery_candidates",
                    {"id": c["id"]},
                    {"review_status": "duplicate", "applied_at": "now()"},
                )
                continue
            new_entries.append(_candidate_to_spec_entry(c))
            applied_ids.append(c["id"])
            existing.add(c["url"])

        if not new_entries:
            log.info("slug=%s: all approved candidates were duplicates", slug)
            continue

        _append_to_spec(spec, new_entries)
        log.info("slug=%s: appended %d source(s) to %s", slug, len(new_entries), spec)

        # Mark applied_at now so we don't double-process if the workflow
        # is retried before the stamp step runs. commit_sha + pr_url are
        # filled in later by `stamp-applied`.
        for cid in applied_ids:
            supa.update(
                "discovery_candidates",
                {"id": cid},
                {"applied_at": "now()"},
            )

        applied[slug] = applied_ids

    return applied


def stamp_applied(
    supa: Supa,
    *,
    candidate_ids: list[str],
    commit_sha: str | None,
    pr_url: str | None,
) -> int:
    """Fill applied_commit_sha + applied_pr_url for the given candidate IDs."""
    if not candidate_ids:
        return 0
    patch: dict[str, Any] = {}
    if commit_sha:
        patch["applied_commit_sha"] = commit_sha
    if pr_url:
        patch["applied_pr_url"] = pr_url
    if not patch:
        return 0
    n = 0
    for cid in candidate_ids:
        supa.update("discovery_candidates", {"id": cid}, patch)
        n += 1
    return n


# ─── CLI ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_drain = sub.add_parser("drain-queue", help="process queued discovery runs")
    p_drain.add_argument("--max-runs", type=int, default=10)
    p_drain.add_argument("--gh-run-id", type=int, default=None)

    p_apply = sub.add_parser("apply-approved", help="apply approved candidates to twin specs")
    p_apply.add_argument(
        "--out-changed-slugs",
        type=Path,
        default=None,
        help="write newline-separated list of edited slugs here (for the workflow)",
    )
    p_apply.add_argument(
        "--out-applied-ids",
        type=Path,
        default=None,
        help="write JSON list of applied candidate IDs here (for stamp-applied)",
    )

    p_stamp = sub.add_parser(
        "stamp-applied",
        help="fill applied_commit_sha + applied_pr_url on already-applied candidates",
    )
    p_stamp.add_argument("--ids-file", type=Path, required=True)
    p_stamp.add_argument("--commit-sha", default=None)
    p_stamp.add_argument("--pr-url", default=None)

    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    supa = Supa.from_env()

    if args.cmd == "drain-queue":
        drain_queue(supa, max_runs=args.max_runs, gh_run_id=args.gh_run_id)
        return 0

    if args.cmd == "apply-approved":
        applied = apply_approved(supa)
        if args.out_changed_slugs:
            args.out_changed_slugs.write_text(
                "\n".join(sorted(applied.keys())) + ("\n" if applied else ""),
                encoding="utf-8",
            )
        if args.out_applied_ids:
            all_ids = [cid for ids in applied.values() for cid in ids]
            args.out_applied_ids.write_text(json.dumps(all_ids), encoding="utf-8")
        print(json.dumps({"applied": {k: len(v) for k, v in applied.items()}}))
        return 0

    if args.cmd == "stamp-applied":
        ids = json.loads(args.ids_file.read_text(encoding="utf-8"))
        n = stamp_applied(
            supa,
            candidate_ids=ids,
            commit_sha=args.commit_sha,
            pr_url=args.pr_url,
        )
        print(json.dumps({"stamped": n}))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
