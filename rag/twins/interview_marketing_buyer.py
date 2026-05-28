"""
interview_marketing_buyer — CLI alias for marketing-buyer discovery interviews.

Delegates to interview_archetype with --mode marketing-buyer and a default
research goal for SyntheticPerson Insights/Lab ICP validation.

Usage:
    python -m rag.twins.interview_marketing_buyer <twin_id> --turns 8 \\
        --opener "Conta da última vez que você levou um estudo ao board."
"""

from __future__ import annotations

import sys

from rag.twins import interview_archetype
from rag.twins.marketing_discovery_manifest import DEFAULT_CMO_RESEARCH_GOAL as DEFAULT_MARKETING_RESEARCH_GOAL


def main(argv: list[str] | None = None) -> int:
    raw = list(argv if argv is not None else sys.argv[1:])
    if not raw or raw[0].startswith("-"):
        print(__doc__, file=sys.stderr)
        return 2

    twin_id = raw[0]
    rest = raw[1:]
    if "--research-goal" not in rest:
        rest = ["--research-goal", DEFAULT_MARKETING_RESEARCH_GOAL, *rest]
    if "--mode" not in rest:
        rest = ["--mode", "marketing-buyer", *rest]
    return interview_archetype.main([twin_id, *rest])


if __name__ == "__main__":
    raise SystemExit(main())
