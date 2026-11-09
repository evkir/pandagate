"""R3 - how far the change is spread across the tree.

Areas are counted over logic files only. A change that also touches its
tests, the changelog and the CI configuration is one change, not four, so
counting every kind of file would report every ordinary pull request as
scattered.

An area is the first `area_depth` path segments, two by default. Depth of
one would call packages/a and packages/b the same area in a monorepo;
greater depth would split src/app/models from src/app/views in a single
application.
"""

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

from pandagate.facts import ChangedFile, PullRequestFacts
from pandagate.paths import PathKind, classify
from pandagate.rules.base import Outcome, Signal, register

DEFAULT_MAX_AREAS = 3
DEFAULT_AREA_DEPTH = 2


def area_of(path: str, depth: int) -> str:
    """The directory prefix that stands for this path's area of the tree."""
    parts = PurePosixPath(path).parts
    directories = parts[:-1]
    if not directories:
        return "(root)"
    return "/".join(directories[:depth])


def logic_areas(files: Sequence[ChangedFile], depth: int) -> tuple[str, ...]:
    """Distinct areas touched by logic files, ignoring pure renames."""
    areas = {
        area_of(f.path, depth)
        for f in files
        if not f.is_pure_rename and classify(f.path) is PathKind.LOGIC
    }
    return tuple(sorted(areas))


class DiffCohesionRule:
    """Reports how many distinct areas of the tree the logic change spans."""

    rule_id = "R3"
    title = "Diff cohesion"

    def evaluate(self, facts: PullRequestFacts, options: Mapping[str, Any]) -> Signal:
        if facts.files_truncated:
            return Signal(
                self.rule_id,
                self.title,
                Outcome.UNKNOWN,
                "the file list was truncated, so the spread cannot be measured",
            )

        depth = max(1, int(options.get("area_depth", DEFAULT_AREA_DEPTH)))
        maximum = max(1, int(options.get("max_areas", DEFAULT_MAX_AREAS)))
        areas = logic_areas(facts.changed_files, depth)

        if not areas:
            return Signal(
                self.rule_id, self.title, Outcome.NOT_APPLICABLE, "no logic files changed"
            )

        listed = ", ".join(areas)
        if len(areas) <= maximum:
            return Signal(
                self.rule_id,
                self.title,
                Outcome.PRESENT,
                f"{len(areas)} area(s) of logic touched: {listed}",
            )

        return Signal(
            self.rule_id,
            self.title,
            Outcome.ABSENT,
            f"{len(areas)} areas of logic touched, above the {maximum} area threshold: {listed}",
            "Is this one change, or several that would be easier to review "
            "as separate pull requests?",
        )


RULE = register(DiffCohesionRule())
