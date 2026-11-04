"""Tests for the signal type and the rule registry."""

from collections.abc import Mapping
from typing import Any

import pytest

from pandagate.facts import PullRequestFacts
from pandagate.rules.base import Outcome, Rule, Signal, register, registry


class _StubRule:
    rule_id = "R0"
    title = "stub"

    def evaluate(self, facts: PullRequestFacts, options: Mapping[str, Any]) -> Signal:
        return Signal(self.rule_id, self.title, Outcome.NOT_APPLICABLE, "stub")


def test_outcomes_are_the_declared_four() -> None:
    assert {o.value for o in Outcome} == {"present", "absent", "not_applicable", "unknown"}


def test_absent_signal_requires_a_question() -> None:
    with pytest.raises(ValueError, match="must carry a question"):
        Signal("R1", "issue link", Outcome.ABSENT, "no reference found")


def test_absent_signal_with_a_question_is_accepted() -> None:
    signal = Signal("R1", "issue link", Outcome.ABSENT, "none found", "Which issue is this for?")
    assert signal.question == "Which issue is this for?"


@pytest.mark.parametrize(
    "outcome", [Outcome.PRESENT, Outcome.NOT_APPLICABLE, Outcome.UNKNOWN]
)
def test_question_is_rejected_on_a_non_absent_signal(outcome: Outcome) -> None:
    with pytest.raises(ValueError, match="only on an ABSENT signal"):
        Signal("R1", "issue link", outcome, "detail", "Why?")


def test_stub_rule_satisfies_the_protocol() -> None:
    rule: Rule = _StubRule()
    assert rule.rule_id == "R0"


def test_register_rejects_a_duplicate_rule_id() -> None:
    register(_StubRule())
    with pytest.raises(ValueError, match="duplicate rule_id"):
        register(_StubRule())


def test_registry_returns_a_copy() -> None:
    snapshot = registry()
    snapshot["injected"] = _StubRule()
    assert "injected" not in registry()
