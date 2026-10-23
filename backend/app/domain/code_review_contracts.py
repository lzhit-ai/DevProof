"""Materialized input values for code review; never ORM entities."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ReviewClaim:
    id: UUID
    text: str


@dataclass(frozen=True)
class ReviewEvidence:
    id: UUID
    locator: dict


@dataclass(frozen=True)
class ReviewFinding:
    id: UUID
    evidence_id: UUID
    claim_id: UUID | None
    finding_kind: str
    severity: str
    title: str
    problem: str
    trigger_scenario: str
    recommendation: str
    confidence: float
