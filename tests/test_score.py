"""Tests for running the enabled rules over one pull request."""

from collections.abc import Mapping
from typing import Any

import pytest

from pandagate.config import Config, Mode
from pandagate.facts import PullRequestFacts
from pandagate.rules.base import Outcome, Signal, register
from pandagate.score import UNREADABLE_DETAIL, Report, score


def make_facts(**overrides: Any) -> PullRequestFacts:
    fields: dict[str, Any] = {
        "repository": "octocat/example",
        "number": 42,
        "title": "Add a thing",
        "body": "",
        "author": "contributor",
        "author_association": "CONTRIBUTOR",
        "base_ref": "main",
        "commits": 1,
        "additions": 10,
        "deletions": 2,
        "changed_files": (),
    }
    fields.update(overrides)
    return PullRequestFacts(**fields)


class FakeRule:
    """A rule that reports whatever it was constructed with."""

    def __init__(
        self,
        rule_id: str,
        outcome: Outcome = Outcome.PRESENT,
        detail: str = "observed",
        question: str | None = None,
    ) -> None:
        self.rule_id = rule_id
        self.title = f"Title of {rule_id}"
        self.outcome = outcome
        self.detail = detail
        self.question = question
        self.seen_options: list[dict[str, Any]] = []

    def evaluate(self, facts: PullRequestFacts, options: Mapping[str, Any]) -> Signal:
        self.seen_options.append(dict(options))
        return Signal(self.rule_id, self.title, self.outcome, self.detail, self.question)


class RaisingRule:
    def __init__(self, rule_id: str, error: BaseException) -> None:
        self.rule_id = rule_id
        self.title = f"Title of {rule_id}"
        self.error = error

    def evaluate(self, facts: PullRequestFacts, options: Mapping[str, Any]) -> Signal:
        raise self.error


class NonSignalRule:
    rule_id = "RX"
    title = "Returns the wrong thing"

    def evaluate(self, facts: PullRequestFacts, options: Mapping[str, Any]) -> Signal:
        return "present"  # type: ignore[return-value]


class MisidentifiedRule:
    rule_id = "RX"
    title = "Reports under another identifier"

    def evaluate(self, facts: PullRequestFacts, options: Mapping[str, Any]) -> Signal:
        return Signal("R1", "Issue link", Outcome.PRESENT, "borrowed identifier")


class TitlelessRule:
    rule_id = "RX"

    def evaluate(self, facts: PullRequestFacts, options: Mapping[str, Any]) -> Signal:
        raise RuntimeError("no title to read")


def test_runs_every_registered_rule_by_default() -> None:
    rules = {"R1": FakeRule("R1"), "R2": FakeRule("R2")}
    report = score(make_facts(), Config(), rules)
    assert [signal.rule_id for signal in report.signals] == ["R1", "R2"]
    assert report.warnings == ()


def test_signals_are_ordered_by_identifier_not_by_registration() -> None:
    rules = {"R3": FakeRule("R3"), "R1": FakeRule("R1"), "R2": FakeRule("R2")}
    report = score(make_facts(), Config(), rules)
    assert [signal.rule_id for signal in report.signals] == ["R1", "R2", "R3"]


def test_falls_back_to_the_registry_when_no_rules_are_passed() -> None:
    register(FakeRule("RZ"))
    report = score(make_facts(), Config())
    assert "RZ" in {signal.rule_id for signal in report.signals}


def test_mode_off_runs_nothing() -> None:
    rule = FakeRule("R1")
    report = score(make_facts(), Config(mode=Mode.OFF), {"R1": rule})
    assert report.signals == ()
    assert rule.seen_options == []


def test_mode_off_still_carries_configuration_warnings() -> None:
    config = Config(mode=Mode.OFF, warnings=("unknown key: verdict",))
    report = score(make_facts(), config, {"R1": FakeRule("R1")})
    assert report.warnings == ("unknown key: verdict",)


def test_only_enabled_rules_run() -> None:
    enabled, disabled = FakeRule("R1"), FakeRule("R2")
    config = Config(enabled_rules=("R1",))
    report = score(make_facts(), config, {"R1": enabled, "R2": disabled})
    assert [signal.rule_id for signal in report.signals] == ["R1"]
    assert disabled.seen_options == []


def test_an_empty_enabled_rules_list_runs_nothing_and_warns_about_nothing() -> None:
    config = Config(enabled_rules=())
    report = score(make_facts(), config, {"R1": FakeRule("R1")})
    assert report.signals == ()
    assert report.warnings == ()


def test_unknown_identifier_warns_and_the_known_rules_still_run() -> None:
    config = Config(enabled_rules=("R1", "R99"))
    report = score(make_facts(), config, {"R1": FakeRule("R1")})
    assert [signal.rule_id for signal in report.signals] == ["R1"]
    assert report.warnings == ("enabled_rules: no rule with this identifier: R99",)


def test_configuration_warnings_come_first() -> None:
    config = Config(enabled_rules=("R99",), warnings=("unknown key: verdict",))
    report = score(make_facts(), config, {"R1": FakeRule("R1")})
    assert report.warnings[0] == "unknown key: verdict"
    assert len(report.warnings) == 2


def test_an_empty_registry_warns_instead_of_reporting_silence() -> None:
    report = score(make_facts(), Config(), {})
    assert report.signals == ()
    assert report.warnings == ("no rules are registered",)


def test_an_empty_registry_does_not_blame_the_configuration() -> None:
    report = score(make_facts(), Config(enabled_rules=("R1", "R2")), {})
    assert report.warnings == ("no rules are registered",)


def test_options_reach_the_rule() -> None:
    rule = FakeRule("R2")
    config = Config(rule_options={"R2": {"min_logic_lines": 12}})
    score(make_facts(), config, {"R2": rule})
    assert rule.seen_options == [{"min_logic_lines": 12}]


def test_a_rule_without_options_is_given_an_empty_mapping() -> None:
    rule = FakeRule("R2")
    score(make_facts(), Config(), {"R2": rule})
    assert rule.seen_options == [{}]


def test_a_raising_rule_becomes_an_unknown_signal() -> None:
    rules = {"R1": RaisingRule("R1", TypeError("bad payload")), "R2": FakeRule("R2")}
    report = score(make_facts(), Config(), rules)
    failed, healthy = report.signals
    assert failed.rule_id == "R1"
    assert failed.outcome is Outcome.UNKNOWN
    assert failed.detail == UNREADABLE_DETAIL
    assert failed.title == "Title of R1"
    assert healthy.outcome is Outcome.PRESENT


def test_a_raising_rule_carries_no_question() -> None:
    report = score(make_facts(), Config(), {"R1": RaisingRule("R1", ValueError("boom"))})
    assert report.signals[0].question is None
    assert report.questions == ()


def test_a_raising_rule_warns_with_the_exception_type_only() -> None:
    error = TypeError("undisclosed payload contents")
    report = score(make_facts(), Config(), {"R1": RaisingRule("R1", error)})
    assert report.warnings == ("R1: the rule raised TypeError",)


def test_a_rule_returning_something_other_than_a_signal_is_a_failure() -> None:
    report = score(make_facts(), Config(), {"RX": NonSignalRule()})
    assert report.signals[0].outcome is Outcome.UNKNOWN
    assert report.warnings == ("RX: the rule returned str where a signal was expected",)


def test_a_rule_reporting_under_another_identifier_is_a_failure() -> None:
    report = score(make_facts(), Config(), {"RX": MisidentifiedRule()})
    assert report.signals[0].rule_id == "RX"
    assert report.signals[0].outcome is Outcome.UNKNOWN
    assert report.warnings == ("RX: the rule reported under the identifier R1",)


def test_a_failing_rule_without_a_title_falls_back_to_its_identifier() -> None:
    report = score(make_facts(), Config(), {"RX": TitlelessRule()})
    assert report.signals[0].title == "RX"


def test_a_keyboard_interrupt_is_not_swallowed() -> None:
    rules = {"R1": RaisingRule("R1", KeyboardInterrupt())}
    with pytest.raises(KeyboardInterrupt):
        score(make_facts(), Config(), rules)


def test_a_system_exit_is_not_swallowed() -> None:
    rules = {"R1": RaisingRule("R1", SystemExit(1))}
    with pytest.raises(SystemExit):
        score(make_facts(), Config(), rules)


def test_questions_collects_what_the_absent_signals_carry() -> None:
    rules = {
        "R1": FakeRule("R1", Outcome.ABSENT, "no link", "Which issue does this close?"),
        "R2": FakeRule("R2", Outcome.PRESENT, "tests changed"),
        "R3": FakeRule("R3", Outcome.ABSENT, "three areas", "Can this be split?"),
    }
    report = score(make_facts(), Config(), rules)
    assert report.questions == ("Which issue does this close?", "Can this be split?")


def test_by_outcome_filters_and_keeps_report_order() -> None:
    rules = {
        "R1": FakeRule("R1", Outcome.ABSENT, "no link", "Which issue?"),
        "R2": FakeRule("R2", Outcome.NOT_APPLICABLE, "no logic files"),
        "R3": FakeRule("R3", Outcome.ABSENT, "three areas", "Can this be split?"),
    }
    report = score(make_facts(), Config(), rules)
    absent = report.by_outcome(Outcome.ABSENT)
    assert [signal.rule_id for signal in absent] == ["R1", "R3"]
    assert report.by_outcome(Outcome.PRESENT) == ()


def test_an_empty_report_is_the_default() -> None:
    report = Report()
    assert report.signals == ()
    assert report.warnings == ()
    assert report.questions == ()
