"""
Sync twins from local SQLite to Supabase PostgreSQL.

Reads from rag/twins/twins.db (SQLite) and writes to Supabase via REST API.
Handles schema mapping and type conversions.

Schema mapping:
  person          → twin_person
  corpus_chunk    → twin_corpus_chunk
  twin            → twin
  interview_turn  → twin_interview_turn
  eval_run        → twin_eval_run

Usage:
  python rag/twins/sync_to_supabase.py [--db-path rag/twins/twins.db]
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ftlzbhmjjtetrchfcxtv.supabase.co")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def get_supabase_client() -> Any:
    """Create REST client for Supabase using service role key."""
    if not SUPABASE_SERVICE_KEY:
        raise ValueError(
            "SUPABASE_SERVICE_ROLE_KEY not set. Set via: "
            "export SUPABASE_SERVICE_ROLE_KEY=<your-key>"
        )
    if not requests:
        raise ImportError("requests library required for Supabase REST API sync")

    class SupabaseRestClient:
        def __init__(self, url: str, key: str):
            self.url = url
            self.headers = {
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            }

        def table(self, name: str):
            return SupabaseTable(self.url, name, self.headers)

    class SupabaseTable:
        def __init__(self, url: str, name: str, headers: dict):
            self.url = f"{url}/rest/v1/{name}"
            self.headers = headers

        def insert(self, data):
            return SupabaseInsert(self.url, self.headers, data)

    class SupabaseInsert:
        def __init__(self, url: str, headers: dict, data: Any):
            self.url = url
            self.headers = headers
            self.data = data if isinstance(data, list) else [data]

        def execute(self):
            response = requests.post(self.url, json=self.data, headers=self.headers, timeout=30)
            if response.status_code not in (200, 201):
                raise Exception(f"Supabase API error {response.status_code}: {response.text}")
            time.sleep(0.05)  # Small delay between requests to avoid rate limiting
            return response.json()

    return SupabaseRestClient(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def sync_twin_persons(conn: sqlite3.Connection, supa: Any) -> int:
    """Sync person table → twin_person."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name_public, archetype_label, authorization, notes, created_at
        FROM person
    """
    )
    rows = cursor.fetchall()
    inserted = 0

    for row in rows:
        person_id, name_public, archetype_label, auth, notes, created_at = row
        try:
            supa.table("twin_person").insert(
                {
                    "id": person_id,
                    "name_public": name_public,
                    "archetype_label": archetype_label or "Unknown",
                    "authorization": auth or "pending",
                    "notes": notes,
                    "created_at": created_at or datetime.utcnow().isoformat(),
                }
            ).execute()
            inserted += 1
            log.info(f"✓ Synced person: {person_id}")
        except Exception as e:
            log.warning(f"✗ Failed to sync person {person_id}: {e}")

    return inserted


def sync_twin_corpus_chunks(conn: sqlite3.Connection, supa: Any) -> int:
    """Sync corpus_chunk table → twin_corpus_chunk."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, person_id, source_url, source_type, source_date,
               first_person, text, token_count, quality_score, holdout,
               embedding, created_at
        FROM corpus_chunk
    """
    )
    rows = cursor.fetchall()
    inserted = 0

    for row in rows:
        (
            chunk_id,
            person_id,
            source_url,
            source_type,
            source_date,
            first_person,
            text,
            token_count,
            quality_score,
            holdout,
            embedding_blob,
            created_at,
        ) = row

        # Parse embedding from JSON blob if present
        embedding_vector = None
        if embedding_blob:
            try:
                embedding_vector = json.loads(embedding_blob)
            except (json.JSONDecodeError, TypeError):
                log.warning(f"Failed to parse embedding for chunk {chunk_id}")

        try:
            supa.table("twin_corpus_chunk").insert(
                {
                    "id": chunk_id,
                    "person_id": person_id,
                    "source_url": source_url,
                    "source_type": source_type or "article",
                    "source_date": source_date,
                    "first_person": bool(first_person),
                    "text": text,
                    "token_count": token_count,
                    "quality_score": quality_score or 0.0,
                    "holdout": bool(holdout),
                    "embedding": embedding_vector,
                    "created_at": created_at or datetime.utcnow().isoformat(),
                }
            ).execute()
            inserted += 1
        except Exception as e:
            log.warning(f"✗ Failed to sync chunk {chunk_id}: {e}")

    log.info(f"Synced {inserted}/{len(rows)} corpus chunks")
    return inserted


def sync_twins(conn: sqlite3.Connection, supa: Any) -> int:
    """Sync twin table → twin."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, person_id, is_composite, archetype_label, status,
               schema_json, updated_at
        FROM twin
    """
    )
    rows = cursor.fetchall()
    inserted = 0

    for row in rows:
        (
            twin_id,
            person_id,
            is_composite,
            archetype_label,
            status,
            schema_json_str,
            updated_at,
        ) = row

        # Parse schema_json
        try:
            schema_json = json.loads(schema_json_str) if schema_json_str else {}
        except json.JSONDecodeError:
            schema_json = {}

        try:
            supa.table("twin").insert(
                {
                    "id": twin_id,
                    "person_id": person_id,
                    "is_composite": bool(is_composite),
                    "archetype_label": archetype_label or "Unknown",
                    "status": status or "draft",
                    "schema_json": schema_json,
                    "eval_scores": schema_json.get("eval_scores") or {},
                    "reliability_json": schema_json.get("reliability") or {},
                    "created_at": updated_at or datetime.utcnow().isoformat(),
                    "updated_at": updated_at or datetime.utcnow().isoformat(),
                }
            ).execute()
            inserted += 1
            log.info(f"✓ Synced twin: {twin_id} (person: {person_id})")
        except Exception as e:
            log.warning(f"✗ Failed to sync twin {twin_id}: {e}")

    return inserted


def sync_interview_turns(conn: sqlite3.Connection, supa: Any) -> int:
    """Sync interview_turn table → twin_interview_turn."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, session_id, twin_id, turn_index, speaker, content,
               tool_calls, tokens_in, tokens_out, created_at
        FROM interview_turn
    """
    )
    rows = cursor.fetchall()
    inserted = 0

    for row in rows:
        (
            turn_id,
            session_id,
            twin_id,
            turn_index,
            speaker,
            content,
            tool_calls_str,
            tokens_in,
            tokens_out,
            created_at,
        ) = row

        # Parse tool_calls
        try:
            tool_calls = json.loads(tool_calls_str) if tool_calls_str else None
        except json.JSONDecodeError:
            tool_calls = None

        try:
            supa.table("twin_interview_turn").insert(
                {
                    "id": turn_id,
                    "session_id": session_id,
                    "twin_id": twin_id,
                    "turn_index": turn_index,
                    "speaker": speaker or "system",
                    "content": content,
                    "tool_calls": tool_calls,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "created_at": created_at or datetime.utcnow().isoformat(),
                }
            ).execute()
            inserted += 1
        except Exception as e:
            log.warning(f"✗ Failed to sync interview turn {turn_id}: {e}")

    log.info(f"Synced {inserted}/{len(rows)} interview turns")
    return inserted


def sync_eval_runs(conn: sqlite3.Connection, supa: Any) -> int:
    """Sync eval_run table → twin_eval_run."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, twin_id, harness, scores_json, passed, notes, created_at
        FROM eval_run
    """
    )
    rows = cursor.fetchall()
    inserted = 0

    for row in rows:
        eval_id, twin_id, harness, scores_json_str, passed, notes, created_at = row

        # Parse scores_json
        try:
            scores_json = json.loads(scores_json_str) if scores_json_str else {}
        except json.JSONDecodeError:
            scores_json = {}

        try:
            supa.table("twin_eval_run").insert(
                {
                    "id": eval_id,
                    "twin_id": twin_id,
                    "harness": harness or "holdout_cosine",
                    "scores_json": scores_json,
                    "passed": bool(passed) if passed is not None else None,
                    "notes": notes,
                    "created_at": created_at or datetime.utcnow().isoformat(),
                }
            ).execute()
            inserted += 1
            log.info(f"✓ Synced eval_run: {eval_id} (twin: {twin_id})")
        except Exception as e:
            log.warning(f"✗ Failed to sync eval_run {eval_id}: {e}")

    return inserted


def main():
    """Main sync entrypoint."""
    import argparse

    parser = argparse.ArgumentParser(description="Sync twins from SQLite to Supabase")
    parser.add_argument(
        "--db-path",
        default="rag/twins/twins.db",
        help="Path to local twins.db (default: rag/twins/twins.db)",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        log.error(f"Database not found: {db_path}")
        return 1

    log.info(f"Connecting to {db_path}...")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    log.info(f"Connecting to Supabase {SUPABASE_URL}...")
    try:
        supa = get_supabase_client()
    except ValueError as e:
        log.error(f"Supabase authentication failed: {e}")
        return 1

    try:
        log.info("=" * 60)
        log.info("Starting twin sync...")
        log.info("=" * 60)

        # Sync in dependency order
        n_persons = sync_twin_persons(conn, supa)
        log.info(f"✓ Synced {n_persons} persons\n")

        n_chunks = sync_twin_corpus_chunks(conn, supa)
        log.info(f"✓ Synced {n_chunks} corpus chunks\n")

        n_twins = sync_twins(conn, supa)
        log.info(f"✓ Synced {n_twins} twins\n")

        n_turns = sync_interview_turns(conn, supa)
        log.info(f"✓ Synced {n_turns} interview turns\n")

        n_evals = sync_eval_runs(conn, supa)
        log.info(f"✓ Synced {n_evals} eval runs\n")

        log.info("=" * 60)
        log.info(
            f"Sync complete: {n_persons} persons, {n_chunks} chunks, "
            f"{n_twins} twins, {n_turns} turns, {n_evals} evals"
        )
        log.info("=" * 60)
        return 0

    except Exception as e:
        log.error(f"Sync failed: {e}", exc_info=True)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    exit(main())
