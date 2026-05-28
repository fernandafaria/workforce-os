"""
export_interview_transcript — export interview_turn rows for Aspasia synthesize-research.

Writes markdown (human) + jsonl bundle (machine) under
company/SyntheticPerson/syntheticperson-ai/memory/synthetic-interviews/.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from rag.twins import storage

DEFAULT_OUT_DIR = Path(
    "company/SyntheticPerson/syntheticperson-ai/memory/synthetic-interviews"
)


def _format_markdown(session_id: str, turns: list[dict], *, person_id: str | None) -> str:
    lines = [
        f"# Synthetic interview — {session_id}",
        "",
        f"- **exported_at**: {datetime.now(timezone.utc).isoformat()}",
        f"- **person_id**: {person_id or '(unknown)'}",
        f"- **turns**: {len(turns)}",
        "",
        "---",
        "",
    ]
    for row in turns:
        speaker = row.get("speaker", "?")
        idx = row.get("turn_index", "?")
        content = (row.get("content") or "").strip()
        lines.append(f"### Turn {idx} — {speaker}")
        lines.append("")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


def export_session(
    session_id: str,
    *,
    out_dir: Path = DEFAULT_OUT_DIR,
    db_path: Path | None = None,
) -> tuple[Path, Path]:
    turns = storage.transcript(session_id, db_path=db_path)
    if not turns:
        raise SystemExit(f"No turns for session_id={session_id}")

    person_id = None
    twin_id = turns[0].get("twin_id")
    if twin_id:
        twin = storage.get_twin(twin_id, db_path=db_path)
        if twin:
            person_id = twin.get("person_id")

    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{session_id}.md"
    json_path = out_dir / f"{session_id}.jsonl"

    md_path.write_text(
        _format_markdown(session_id, turns, person_id=person_id),
        encoding="utf-8",
    )
    with json_path.open("w", encoding="utf-8") as fh:
        for row in turns:
            fh.write(
                json.dumps(
                    {
                        "session_id": session_id,
                        "person_id": person_id,
                        "turn_index": row.get("turn_index"),
                        "speaker": row.get("speaker"),
                        "content": row.get("content"),
                        "tool_calls": row.get("tool_calls"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return md_path, json_path


def list_sessions(
    *,
    prefix: str | None = "mkt-interview",
    db_path: Path | None = None,
) -> list[str]:
    with storage.connect(db_path) as conn:
        if prefix:
            rows = conn.execute(
                """
                SELECT DISTINCT session_id FROM interview_turn
                WHERE session_id LIKE ?
                ORDER BY session_id
                """,
                (f"{prefix}%",),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT session_id FROM interview_turn ORDER BY session_id"
            ).fetchall()
    return [r["session_id"] for r in rows]


def export_all(
    *,
    prefix: str | None = "mkt-interview",
    out_dir: Path = DEFAULT_OUT_DIR,
    db_path: Path | None = None,
) -> list[tuple[Path, Path]]:
    paths: list[tuple[Path, Path]] = []
    for sid in list_sessions(prefix=prefix, db_path=db_path):
        paths.append(export_session(sid, out_dir=out_dir, db_path=db_path))
    return paths


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("session_id", nargs="?", help="Session to export (omit with --all)")
    p.add_argument("--all", action="store_true", help="Export all mkt-interview-* sessions")
    p.add_argument("--list", action="store_true", help="List session IDs only")
    p.add_argument("--prefix", default="mkt-interview", help="Session ID prefix filter")
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--db", type=Path, default=None)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.list:
        for sid in list_sessions(prefix=args.prefix or None, db_path=args.db):
            print(sid)
        return 0
    if args.all:
        exported = export_all(prefix=args.prefix, out_dir=args.out_dir, db_path=args.db)
        if not exported:
            print("No sessions to export.", file=sys.stderr)
            return 1
        for md, js in exported:
            print(md)
            print(js)
        return 0
    if not args.session_id:
        print("Provide session_id or use --all / --list", file=sys.stderr)
        return 2
    md, js = export_session(args.session_id, out_dir=args.out_dir, db_path=args.db)
    print(md)
    print(js)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
