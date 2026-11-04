"""Rule protocol, signal type and registry.

A rule reports one observable signal about a pull request. A rule never
reports a judgement about who or what authored it.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from pandagate.facts import PullRequestFacts


class Outcome(StrEnum):
    """What a rule could establish.

    PRESENT        the evidence this rule looks for is there
    ABSENT         it is not there, and the rule carries a question about it
    NOT_APPLICABLE this pull request is out of the rule's scope
    UNKNOWN        the rule could not read what it needs
    """

    PRESENT = "present"
    ABSENT = "absent"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Signal:
    """One rule's reading of one pull request.

    An ABSENT signal must carry a question for the maintainer to ask. A
    missing signal is a thing to ask about, never a charge to answer.
    """

    rule_id: str
    title: str
    outcome: Outcome
    detail: str
    question: str | None = None

    def __post_init__(self) -> None:
        if self.outcome is Outcome.ABSENT and not self.question:
            raise ValueError(f"{self.rule_id}: an ABSENT signal must carry a question")
        if self.outcome is not Outcome.ABSENT and self.question:
            raise ValueError(f"{self.rule_id}: a question belongs only on an ABSENT signal")


class Rule(Protocol):
    """What every evidence rule implements."""

    rule_id: str
    title: str

    def evaluate(self, facts: PullRequestFacts, options: Mapping[str, Any]) -> Signal: ...


_REGISTRY: dict[str, Rule] = {}


def register(rule: Rule) -> Rule:
    """Register a rule instance, rejecting a duplicate identifier."""
    if rule.rule_id in _REGISTRY:
        raise ValueError(f"duplicate rule_id: {rule.rule_id}")
    _REGISTRY[rule.rule_id] = rule
    return rule


def registry() -> dict[str, Rule]:
    """A copy of the registered rules, keyed by rule_id."""
    return dict(_REGISTRY)
