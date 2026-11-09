"""R2 - did tests change alongside logic.

The rule reads the list of changed files, never their contents. It cannot
see whether the repository has a test suite at all, so a repository
without one should switch this rule off in its configuration rather than
read a standing ABSENT.
"""

from collections.abc import Mapping
from typing import Any

from pandagate.facts import PullRequestFacts
from pandagate.paths import PathKind, classify
from pandagate.rules.base import Outcome, Signal, register

DEFAULT_MIN_LOGIC_LINES = 5


class TestsWithCodeRule:
    """Reports whether test files changed in the same pull request as logic."""

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

        return Signal(
            self.rule_id,
            self.title,
            Outcome.ABSENT,
            f"{len(logic)} logic file(s) changed, {logic_lines} line(s), no test file changed",
            "Which test fails before this change and passes after it?",
        )


RULE = register(TestsWithCodeRule())
