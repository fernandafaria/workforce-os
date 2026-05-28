"""
Twin storage — local SQLite + optional Supabase mirror.

Design (Simon's MVP discipline): log everything from day 1, keep the
production write path simple. SQLite is the authoritative store for
local MVP work; Supabase mirror is additive and graceful-degrades when
env vars are missing (same pattern as rag/supabase_store.py).

Tables:
    person             — real entrepreneur the corpus traces back to
    corpus_chunk       — one chunk per row, with source metadata + embedding
    twin               — serialized EntrepreneurTwin (JSON) + status
    interview_turn     — every interviewer/twin turn (full transcript)
    eval_run           — one row per eval harness invocation

All writes go through this module so hooks (LGPD audit, corpus-quality
alerts) have a single choke point.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DEFAULT_DB = Path(os.environ.get("TWINS_DB_PATH", "rag/twins/twins.db"))

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS person (
    id              TEXT PRIMARY KEY,
    name_public     TEXT,
    archetype_label TEXT,
    authorization   TEXT NOT NULL DEFAULT 'pending',  -- pending|granted|public_figure|denied
    created_at      TEXT NOT NULL,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS corpus_chunk (
    id              TEXT PRIMARY KEY,
    person_id       TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    source_url      TEXT,
    source_type     TEXT NOT NULL,   -- interview|podcast|linkedin|talk|release|book|article|crawl
    source_date     TEXT,
    first_person    INTEGER DEFAULT 1,  -- 0 if content is ABOUT the person, not BY
    text            TEXT NOT NULL,
    token_count     INTEGER,
    quality_score   REAL DEFAULT 0.0,
    holdout         INTEGER DEFAULT 0,  -- 1 when reserved for eval
    embedding       BLOB,               -- JSON-encoded list[float]
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunk_person  ON corpus_chunk(person_id);
CREATE INDEX IF NOT EXISTS idx_chunk_holdout ON corpus_chunk(person_id, holdout);

CREATE TABLE IF NOT EXISTS twin (
    id              TEXT PRIMARY KEY,
    person_id       TEXT REFERENCES person(id) ON DELETE SET NULL,
    is_composite    INTEGER NOT NULL DEFAULT 1,
    archetype_label TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft',  -- draft|eval_passed|production|deprecated
    schema_json     TEXT NOT NULL,   -- full EntrepreneurTwin.model_dump()
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interview_turn (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    twin_id         TEXT NOT NULL,
    turn_index      INTEGER NOT NULL,
    speaker         TEXT NOT NULL,   -- interviewer|twin|system
    content         TEXT NOT NULL,
    tool_calls      TEXT,            -- JSON array when twin invoked corpus_search
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turn_session ON interview_turn(session_id, turn_index);

CREATE TABLE IF NOT EXISTS eval_run (
    id              TEXT PRIMARY KEY,
    twin_id         TEXT NOT NULL,
    harness         TEXT NOT NULL,   -- holdout_cosine|stylometry|llm_judge
    scores_json     TEXT NOT NULL,
    passed          INTEGER,
    notes           TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_twin ON eval_run(twin_id, created_at);
"""


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


def _isoformat_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@contextmanager
def connect(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with schema ensured. Always closes."""
    path = Path(db_path) if db_path else _DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA_SQL)
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Person
# ---------------------------------------------------------------------------


def upsert_person(
    person_id: str,
    *,
    name_public: str | None,
    archetype_label: str,
    authorization: str = "pending",
    notes: str | None = None,
    db_path: Path | str | None = None,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO person (id, name_public, archetype_label, authorization, created_at, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name_public     = excluded.name_public,
                archetype_label = excluded.archetype_label,
                authorization   = excluded.authorization,
                notes           = COALESCE(excluded.notes, person.notes)
            """,
            (person_id, name_public, archetype_label, authorization, _isoformat_now(), notes),
        )


def get_person(person_id: str, db_path: Path | str | None = None) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM person WHERE id = ?", (person_id,)).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Corpus chunks
# ---------------------------------------------------------------------------


def insert_chunks(
    person_id: str,
    chunks: Iterable[dict],
    db_path: Path | str | None = None,
) -> int:
    """Insert a batch of chunks. Each chunk dict may provide:

    text, source_url, source_type, source_date, first_person,
    token_count, quality_score, holdout, embedding (list[float])
    """
    inserted = 0
    with connect(db_path) as conn:
        for c in chunks:
            embedding = c.get("embedding")
            blob = json.dumps(embedding).encode("utf-8") if embedding else None
            conn.execute(
                """
                INSERT INTO corpus_chunk (
                    id, person_id, source_url, source_type, source_date,
                    first_person, text, token_count, quality_score, holdout,
                    embedding, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    c.get("id") or str(uuid.uuid4()),
                    person_id,
                    c.get("source_url"),
                    c["source_type"],
                    c.get("source_date"),
                    1 if c.get("first_person", True) else 0,
                    c["text"],
                    c.get("token_count") or _approx_tokens(c["text"]),
                    float(c.get("quality_score", 0.0)),
                    1 if c.get("holdout") else 0,
                    blob,
                    _isoformat_now(),
                ),
            )
            inserted += 1
    return inserted


def list_chunks(
    person_id: str,
    *,
    include_holdout: bool = False,
    db_path: Path | str | None = None,
) -> list[dict]:
    with connect(db_path) as conn:
        if include_holdout:
            rows = conn.execute(
                "SELECT * FROM corpus_chunk WHERE person_id = ? ORDER BY created_at",
                (person_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM corpus_chunk "
                "WHERE person_id = ? AND holdout = 0 ORDER BY created_at",
                (person_id,),
            ).fetchall()
    return [_row_to_chunk_dict(r) for r in rows]


def corpus_stats(person_id: str, db_path: Path | str | None = None) -> dict:
    """Compute source_count / total_tokens / source_types for provenance."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT source_type, COUNT(*) AS n, SUM(token_count) AS toks,
                   MIN(source_date) AS d_min, MAX(source_date) AS d_max
            FROM corpus_chunk WHERE person_id = ? AND holdout = 0
            GROUP BY source_type
            """,
            (person_id,),
        ).fetchall()
        distinct_sources = conn.execute(
            "SELECT COUNT(DISTINCT source_url) FROM corpus_chunk "
            "WHERE person_id = ? AND holdout = 0",
            (person_id,),
        ).fetchone()[0]

    source_types = {r["source_type"]: r["n"] for r in rows}
    total_tokens = sum((r["toks"] or 0) for r in rows)
    d_min = min((r["d_min"] for r in rows if r["d_min"]), default=None)
    d_max = max((r["d_max"] for r in rows if r["d_max"]), default=None)
    return {
        "source_count": distinct_sources or 0,
        "total_tokens": int(total_tokens),
        "source_types": source_types,
        "date_range_start": d_min,
        "date_range_end": d_max,
    }


def mark_holdout(
    person_id: str, ratio: float = 0.2, seed: int = 42, db_path: Path | str | None = None
) -> int:
    """Randomly reserve `ratio` of chunks as holdout for eval.

    Stratified by source_type so each source type contributes to holdout
    proportionally (Shreya's requirement — otherwise holdout is biased
    to whichever type has the most volume, usually LinkedIn).
    """
    import random

    rng = random.Random(seed)
    marked = 0
    with connect(db_path) as conn:
        types = conn.execute(
            "SELECT DISTINCT source_type FROM corpus_chunk WHERE person_id = ?",
            (person_id,),
        ).fetchall()
        for t in types:
            ids = [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM corpus_chunk "
                    "WHERE person_id = ? AND source_type = ? AND holdout = 0",
                    (person_id, t["source_type"]),
                ).fetchall()
            ]
            rng.shuffle(ids)
            n_hold = max(1, int(len(ids) * ratio)) if ids else 0
            for chunk_id in ids[:n_hold]:
                conn.execute("UPDATE corpus_chunk SET holdout = 1 WHERE id = ?", (chunk_id,))
                marked += 1
    return marked


# ---------------------------------------------------------------------------
# Twin
# ---------------------------------------------------------------------------


def upsert_twin(twin_dict: dict, db_path: Path | str | None = None) -> None:
    """Persist a serialized EntrepreneurTwin.model_dump() dict."""
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO twin "
            "(id, person_id, is_composite, archetype_label, status, "
            "schema_json, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "person_id = excluded.person_id, "
            "is_composite = excluded.is_composite, "
            "archetype_label = excluded.archetype_label, "
            "status = excluded.status, "
            "schema_json = excluded.schema_json, "
            "updated_at = excluded.updated_at",
            (
                twin_dict["id"],
                twin_dict.get("person_id"),
                1 if twin_dict.get("is_composite", True) else 0,
                twin_dict["archetype_label"],
                twin_dict.get("status", "draft"),
                json.dumps(twin_dict, default=str),
                _isoformat_now(),
            ),
        )


def get_twin(twin_id: str, db_path: Path | str | None = None) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT schema_json FROM twin WHERE id = ?", (twin_id,)).fetchone()
    if not row:
        return None
    return json.loads(row["schema_json"])


def get_twin_by_slug(slug: str, db_path: Path | str | None = None) -> dict | None:
    """Return the most-recently-updated twin whose person_id matches slug."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT schema_json FROM twin WHERE person_id = ? ORDER BY updated_at DESC LIMIT 1",
            (slug,),
        ).fetchone()
    if not row:
        return None
    return json.loads(row["schema_json"])


def list_twins(status: str | None = None, db_path: Path | str | None = None) -> list[dict]:
    with connect(db_path) as conn:
        if status:
            rows = conn.execute(
                "SELECT schema_json FROM twin WHERE status = ? ORDER BY updated_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT schema_json FROM twin ORDER BY updated_at DESC").fetchall()
    return [json.loads(r["schema_json"]) for r in rows]


# ---------------------------------------------------------------------------
# Interview turns
# ---------------------------------------------------------------------------


def log_turn(
    *,
    session_id: str,
    twin_id: str,
    turn_index: int,
    speaker: str,
    content: str,
    tool_calls: list | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    db_path: Path | str | None = None,
) -> str:
    turn_id = str(uuid.uuid4())
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO interview_turn (
                id, session_id, twin_id, turn_index, speaker, content,
                tool_calls, tokens_in, tokens_out, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn_id,
                session_id,
                twin_id,
                turn_index,
                speaker,
                content,
                json.dumps(tool_calls) if tool_calls else None,
                tokens_in,
                tokens_out,
                _isoformat_now(),
            ),
        )
    return turn_id


def transcript(session_id: str, db_path: Path | str | None = None) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM interview_turn WHERE session_id = ? ORDER BY turn_index",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Eval runs
# ---------------------------------------------------------------------------


def log_eval(
    *,
    twin_id: str,
    harness: str,
    scores: dict[str, Any],
    passed: bool | None,
    notes: str | None = None,
    db_path: Path | str | None = None,
) -> str:
    run_id = str(uuid.uuid4())
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO eval_run (id, twin_id, harness, scores_json, passed, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                twin_id,
                harness,
                json.dumps(scores),
                None if passed is None else (1 if passed else 0),
                notes,
                _isoformat_now(),
            ),
        )
    return run_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _approx_tokens(text: str) -> int:
    """Cheap token estimate — good enough for provenance stats."""
    return max(1, len(text) // 4)


def _row_to_chunk_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    blob = d.pop("embedding", None)
    if blob:
        try:
            d["embedding"] = json.loads(blob.decode("utf-8") if isinstance(blob, bytes) else blob)
        except (json.JSONDecodeError, UnicodeDecodeError):
            d["embedding"] = None
    else:
        d["embedding"] = None
    return d
