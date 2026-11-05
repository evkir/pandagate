"""Tests for R2, tests alongside logic."""

from pandagate.facts import ChangedFile, PullRequestFacts
from pandagate.rules.base import Outcome
from pandagate.rules.tests_with_code import RULE


def _file(
    path: str, additions: int = 10, deletions: int = 0, status: str = "modified"
) -> ChangedFile:
    return ChangedFile(path=path, status=status, additions=additions, deletions=deletions)


def _facts(*files: ChangedFile, truncated: bool = False) -> PullRequestFacts:
    return PullRequestFacts(
        repository="evkir/pandagate",
        number=412,
        title="Change",
        body="",
        author="contributor",
        author_association="NONE",
        base_ref="main",
        commits=1,
        additions=sum(f.additions for f in files),
        deletions=sum(f.deletions for f in files),
        changed_files=files,
        files_truncated=truncated,
    )


def test_truncated_file_list_is_unknown() -> None:
    signal = RULE.evaluate(_facts(_file("src/app.py"), truncated=True), {})
    assert signal.outcome is Outcome.UNKNOWN
    assert signal.question is None


def test_logic_with_tests_is_present() -> None:
    signal = RULE.evaluate(_facts(_file("src/app.py"), _file("tests/test_app.py")), {})
    assert signal.outcome is Outcome.PRESENT
    assert "1 test file(s)" in signal.detail


def test_logic_without_tests_is_absent_with_a_question() -> None:
    signal = RULE.evaluate(_facts(_file("src/app.py", additions=80)), {})
    assert signal.outcome is Outcome.ABSENT
    assert signal.question == "Which test fails before this change and passes after it?"


def test_documentation_only_change_is_out_of_scope() -> None:
    signal = RULE.evaluate(_facts(_file("README.md"), _file("docs/guide.md")), {})
    assert signal.outcome is Outcome.NOT_APPLICABLE
    assert signal.detail == "no logic files changed"


def test_configuration_only_change_is_out_of_scope() -> None:
    assert RULE.evaluate(_facts(_file("pyproject.toml")), {}).outcome is Outcome.NOT_APPLICABLE


def test_small_logic_change_is_below_the_threshold() -> None:
    signal = RULE.evaluate(_facts(_file("src/app.py", additions=1, deletions=1)), {})
    assert signal.outcome is Outcome.NOT_APPLICABLE
    assert "below the 5 line threshold" in signal.detail


def test_threshold_is_configurable() -> None:
    facts = _facts(_file("src/app.py", additions=3, deletions=0))
    assert RULE.evaluate(facts, {"min_logic_lines": 1}).outcome is Outcome.ABSENT
    assert RULE.evaluate(facts, {"min_logic_lines": 50}).outcome is Outcome.NOT_APPLICABLE


def test_a_pure_rename_does_not_ask_for_tests() -> None:
    renames = [
        _file("src/a.py", additions=0, deletions=0, status="renamed"),
        _file("src/b.py", additions=0, deletions=0, status="renamed"),
    ]
    assert RULE.evaluate(_facts(*renames), {}).outcome is Outcome.NOT_APPLICABLE


def test_a_rename_that_also_edits_lines_still_counts() -> None:
    signal = RULE.evaluate(_facts(_file("src/a.py", additions=30, status="renamed")), {})
    assert signal.outcome is Outcome.ABSENT


def test_test_only_change_is_out_of_scope() -> None:
    assert RULE.evaluate(_facts(_file("tests/test_app.py")), {}).outcome is Outcome.NOT_APPLICABLE


def test_empty_pull_request_is_out_of_scope() -> None:
    assert RULE.evaluate(_facts(), {}).outcome is Outcome.NOT_APPLICABLE
