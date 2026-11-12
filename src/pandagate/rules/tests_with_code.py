"""R2 - did tests change alongside logic.

The rule reads the list of changed files and, for a language that keeps
tests inside the file they cover, the diff text GitHub reports for that
file. Nothing is checked out and nothing is run. The rule cannot see
whether the repository has a test suite at all, so a repository without
one should switch this rule off in its configuration rather than read a
standing ABSENT.
"""

import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from pandagate.facts import ChangedFile, PullRequestFacts
from pandagate.paths import PathKind, classify
from pandagate.rules.base import Outcome, Signal, register

DEFAULT_MIN_LOGIC_LINES = 5

INLINE_TEST_MARKERS: Mapping[str, re.Pattern[str]] = {
    ".rs": re.compile(r"#!?\[\s*(?:cfg\(\s*test\s*\)|(?:\w+::)*(?:test|rstest|test_case)\b)"),
}


def _inline_marker(path: str) -> re.Pattern[str] | None:
    return INLINE_TEST_MARKERS.get(PurePosixPath(path).suffix.lower())


def adds_inline_tests(file: ChangedFile) -> bool:
    """Whether the lines added to a logic file carry a test marker."""
    marker = _inline_marker(file.path)
    if marker is None or file.patch is None:
        return False
    added = (line[1:] for line in file.patch.splitlines() if line.startswith("+"))
    return any(marker.search(line) for line in added)


def _lacks_diff_text(file: ChangedFile) -> bool:
    return _inline_marker(file.path) is not None and file.patch is None and file.additions > 0


class TestsWithCodeRule:
    """Reports whether tests changed in the same pull request as logic."""

    rule_id = "R2"
    title = "Tests alongside logic"

    def evaluate(self, facts: PullRequestFacts, options: Mapping[str, Any]) -> Signal:
        if facts.files_truncated:
            return Signal(
                self.rule_id,
                self.title,
                Outcome.UNKNOWN,
                "the file list was truncated, so the diff cannot be read in full",
            )

        minimum = int(options.get("min_logic_lines", DEFAULT_MIN_LOGIC_LINES))
        substantive = [f for f in facts.changed_files if not f.is_pure_rename]
        logic = [f for f in substantive if classify(f.path) is PathKind.LOGIC]

        if not logic:
            return Signal(
                self.rule_id, self.title, Outcome.NOT_APPLICABLE, "no logic files changed"
            )

        logic_lines = sum(f.additions + f.deletions for f in logic)
        if logic_lines < minimum:
            return Signal(
                self.rule_id,
                self.title,
                Outcome.NOT_APPLICABLE,
                f"{logic_lines} line(s) of logic changed, below the {minimum} line threshold",
            )

        tests = [f for f in substantive if classify(f.path) is PathKind.TEST]
        if tests:
            return Signal(
                self.rule_id,
                self.title,
                Outcome.PRESENT,
                f"{len(tests)} test file(s) changed alongside {len(logic)} logic file(s)",
            )

        inline = [f for f in logic if adds_inline_tests(f)]
        if inline:
            return Signal(
                self.rule_id,
                self.title,
                Outcome.PRESENT,
                f"tests added inline in {len(inline)} of {len(logic)} logic file(s)",
            )

        unreadable = [f for f in logic if _lacks_diff_text(f)]
        if unreadable:
            return Signal(
                self.rule_id,
                self.title,
                Outcome.UNKNOWN,
                f"no diff text for {len(unreadable)} logic file(s) that may hold tests inline",
            )

        return Signal(
            self.rule_id,
            self.title,
            Outcome.ABSENT,
            f"{len(logic)} logic file(s) changed, {logic_lines} line(s), no test file changed",
            "Which test fails before this change and passes after it?",
        )


RULE = register(TestsWithCodeRule())
