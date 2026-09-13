"""Authored case definitions and the per-day causal record (no engine imports)."""
from dataclasses import dataclass, field
from typing import TypedDict


@dataclass
class CaseQuestion:
    id: str
    text: str
    known_facts: list[str]
    unresolved_parts: list[str]
    action_ids: list[str]
    status: str = "open"


@dataclass
class CaseAction:
    id: str
    label: str
    description: str
    question_part: str
    skill: str
    team_size: int
    cost: int
    risk: str
    possible_evidence: list[str]
    possible_claims: list[str]
    resource_effects: dict
    next_hooks: list[str]
    possible_leads: list[str] = field(default_factory=list)
    stable: bool = False
    difficulty: float = 3.5
    failure_effects: dict = field(default_factory=dict)
    success_text: str = ""
    failure_text: str = ""
    context_tags: list[str] = field(default_factory=list)
    kind: str = "investigation"
    requires_lead: str = ""
    recovery: bool = False


class DayContext(TypedDict):
    month: int
    episode_id: str
    question_id: str
    action_id: str
    participants: list[str]
    success: bool
    evidence_gained: list[str]
    claims_gained: list[str]
    resources_changed: dict
    injuries: list[dict]
    relationship_changes: list[dict]
    next_hooks: list[dict]
    lead_ids: list[str]
    fact_ids: list[str]
    context_tags: list[str]
    deduction_result: dict
