"""Tests for R2 reading tests kept inside a logic file."""

import pytest

from pandagate.facts import ChangedFile, PullRequestFacts
from pandagate.rules.base import Outcome
from pandagate.rules.tests_with_code import RULE, adds_inline_tests

ADDS_TEST = (
    "@@ -10,3 +10,9 @@ mod tests {\n"
    "     use super::*;\n"
    "+\n"
    "+    #[tokio::test]\n"
    "+    async fn wakes() {\n"
    "+        assert!(run().await);\n"
    "+    }\n"
)
LOGIC_ONLY = "@@ -1,3 +1,5 @@\n fn run() -> bool {\n+    let ready = poll();\n+    ready\n }\n"


def _file(path: str, patch: str | None) -> ChangedFile:
    return ChangedFile(path=path, status="modified", additions=6, deletions=0, patch=patch)


def _facts(*files: ChangedFile) -> PullRequestFacts:
    return PullRequestFacts(
        repository="octo/demo",
        number=1,
        title="",
        body="",
        author="contributor",
        author_association="NONE",
        base_ref="main",
        commits=1,
        additions=6,
        deletions=0,
        changed_files=files,
    )


def test_a_test_added_inside_a_logic_file_is_present() -> None:
    signal = RULE.evaluate(_facts(_file("src/sync/notify.rs", ADDS_TEST)), {})
    assert signal.outcome is Outcome.PRESENT
    assert signal.detail == "tests added inline in 1 of 1 logic file(s)"
    assert signal.question is None


def test_a_logic_only_patch_is_absent() -> None:
    signal = RULE.evaluate(_facts(_file("src/sync/notify.rs", LOGIC_ONLY)), {})
    assert signal.outcome is Outcome.ABSENT
    assert signal.question is not None


def test_a_marker_on_a_context_or_removed_line_does_not_count() -> None:
    patch = "@@ -1,4 +1,4 @@\n #[test]\n-#[test]\n+fn renamed() {}\n"
    assert adds_inline_tests(_file("src/lib.rs", patch)) is False


def test_a_missing_patch_for_such_a_language_is_unknown() -> None:
    signal = RULE.evaluate(_facts(_file("src/lib.rs", None)), {})
    assert signal.outcome is Outcome.UNKNOWN
    assert signal.detail == "no diff text for 1 logic file(s) that may hold tests inline"
    assert signal.question is None


def test_a_missing_patch_for_another_language_is_still_absent() -> None:
    assert RULE.evaluate(_facts(_file("src/app.py", None)), {}).outcome is Outcome.ABSENT


def test_a_rust_marker_in_another_language_does_not_count() -> None:
    signal = RULE.evaluate(_facts(_file("src/app.py", "@@ -1 +1,2 @@\n x = 1\n+#[test]\n")), {})
    assert signal.outcome is Outcome.ABSENT


def test_a_changed_test_file_wins_over_a_missing_patch() -> None:
    signal = RULE.evaluate(_facts(_file("src/lib.rs", None), _file("tests/it.rs", None)), {})
    assert signal.outcome is Outcome.PRESENT
    assert signal.detail == "1 test file(s) changed alongside 1 logic file(s)"


@pytest.mark.parametrize(
    "line",
    [
        "#[test]",
        '#[tokio::test(flavor = "multi_thread")]',
        "#[cfg(test)]",
        "#![cfg(test)]",
        "#[rstest]",
        "#[test_case(1)]",
        "#[test_log::test]",
    ],
)
def test_rust_test_attributes_are_markers(line: str) -> None:
    assert adds_inline_tests(_file("src/lib.rs", f"@@ -1 +1,2 @@\n fn a() {{}}\n+{line}\n"))


@pytest.mark.parametrize("line", ["#[testing]", "#[derive(Debug)]", "// attest the result"])
def test_other_lines_are_not_markers(line: str) -> None:
    assert not adds_inline_tests(_file("src/lib.rs", f"@@ -1 +1,2 @@\n fn a() {{}}\n+{line}\n"))
