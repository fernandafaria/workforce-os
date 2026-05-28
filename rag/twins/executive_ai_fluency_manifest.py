"""
executive_ai_fluency_manifest — interview specs for exec AI fluency cohort (200 cells).

Maps cohort matrix → research_goal + opener per person_id.
"""

from __future__ import annotations

from dataclasses import dataclass

from rag.twins.executive_ai_fluency_cohort import (
    COHORT_MATRIX,
    ExecCohortCell,
    cells_for_priority,
)


@dataclass(frozen=True)
class ExecutiveInterviewSpec:
    person_id: str
    lote: str
    priority: str
    research_goal: str
    opener: str
    archetype_id: str
    slice_id: str


def _to_spec(cell: ExecCohortCell) -> ExecutiveInterviewSpec:
    return ExecutiveInterviewSpec(
        person_id=cell.person_id,
        lote=cell.lote,
        priority=cell.priority,
        research_goal=cell.research_goal,
        opener=cell.opener,
        archetype_id=cell.archetype_id,
        slice_id=cell.slice_id,
    )


ALL_SPECS: tuple[ExecutiveInterviewSpec, ...] = tuple(_to_spec(c) for c in COHORT_MATRIX)


DEFAULT_EXEC_RESEARCH_GOAL = (
    "Como um executivo no Brasil sai da sensação de estar atrasado em IA "
    "(uso chat-only, vergonha, falta de tempo) para confiança prática — "
    "e o que faz confiar em times de especialistas / produtos como Synthetic teams "
    "vs mais um curso ou ferramenta genérica."
)

DEFAULT_EXEC_OPENER = (
    "Conta da última vez que IA apareceu de verdade no seu dia de trabalho — "
    "não em palestra, no que você fez ou pediu para alguém fazer."
)


def specs_for_priority(priority: str) -> list[ExecutiveInterviewSpec]:
    return [_to_spec(c) for c in cells_for_priority(priority)]


def spec_for_person(person_id: str) -> ExecutiveInterviewSpec | None:
    for s in ALL_SPECS:
        if s.person_id == person_id:
            return s
    return None
