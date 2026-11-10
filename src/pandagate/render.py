"""Turning a report into the text of one comment.

Two kinds of text meet in a comment. A title and a question are written
by a rule and read the same on every pull request. A detail, a rule
identifier or a note about the run can carry text that came from the
pull request or from the configuration, such as a directory name, and
that text is data.

Data is always placed inside a code span. Nothing inside a code span is
read as markup, so a directory named after a team mentions nobody and a
line break in a file name starts no heading.

A report with nothing to ask about renders to no comment at all.
"""

import re
import unicodedata

from pandagate.config import CONFIG_FILENAME
from pandagate.rules.base import Outcome, Signal
from pandagate.score import Report

#: First line of every comment. The caller finds its own earlier comment
#: by this line and replaces it instead of posting a second one.
MARKER = "<!-- pandagate -->"

#: Longest piece of data shown in one code span. A comment has a size
#: limit, and a pull request decides how long its directory names are.
MAX_FRAGMENT_CHARS = 400

#: Most notes about the run shown in one comment.
MAX_NOTES = 20

_HEADING = "### Observations on this pull request"
_NOTES_SUMMARY = "Notes about this run"
_HOMEPAGE = "https://github.com/evkir/pandagate"
_CLIPPED = " …"
_EMPTY = "(empty)"

_BACKTICK_RUN = re.compile(r"`+")

#: Unicode categories that draw nothing: control, format and surrogate
#: characters. Format characters include the ones that reorder text.
_INVISIBLE = frozenset({"Cc", "Cf", "Cs"})


def render(report: Report) -> str | None:
    """The comment for this report, or None when there is nothing to ask about."""
    if not report.by_outcome(Outcome.ABSENT):
        return None
    lines = [MARKER, _HEADING, ""]
    for signal in report.signals:
        if signal.outcome is not Outcome.NOT_APPLICABLE:
            lines.extend(_signal_lines(signal))
    lines.extend(_note_lines(report.warnings))
    lines.extend(["", _footer()])
    return "\n".join(lines) + "\n"


def _signal_lines(signal: Signal) -> list[str]:
    """One list item for the observation, and one under it for its question."""
    head = f"- **{_flatten(signal.title)}** ({_code(signal.rule_id)})"
    lines = [f"{head}: {_code(signal.detail)}"]
    if signal.question:
        lines.append(f"  - {_flatten(signal.question)}")
    return lines


def _note_lines(warnings: tuple[str, ...]) -> list[str]:
    """A folded block of notes about the run, or nothing when there are none."""
    if not warnings:
        return []
    shown = warnings[:MAX_NOTES]
    lines = ["", "<details>", f"<summary>{_NOTES_SUMMARY}</summary>", ""]
    lines.extend(f"- {_code(warning)}" for warning in shown)
    hidden = len(warnings) - len(shown)
    if hidden:
        lines.append(f"- and {hidden} more")
    lines.extend(["", "</details>"])
    return lines


def _footer() -> str:
    return (
        f"<sub>[PandaGate]({_HOMEPAGE}) reports what it can observe and changes nothing "
        f"about this pull request. Rules are set in {_code(CONFIG_FILENAME)} on the base "
        "branch.</sub>"
    )


def _flatten(text: str) -> str:
    """The text as one line of visible characters."""
    kept = "".join(
        char for char in text if char.isspace() or unicodedata.category(char) not in _INVISIBLE
    )
    return " ".join(kept.split())


def _clip(text: str) -> str:
    if len(text) <= MAX_FRAGMENT_CHARS:
        return text
    return text[:MAX_FRAGMENT_CHARS].rstrip() + _CLIPPED


def _code(text: str) -> str:
    """The text as a code span that nothing inside it can close.

    The delimiter is one backtick longer than the longest run of
    backticks in the text, and the text is padded with a space on each
    side so that it may itself begin or end with a backtick.
    """
    flat = _clip(_flatten(text)) or _EMPTY
    longest = max((len(run) for run in _BACKTICK_RUN.findall(flat)), default=0)
    fence = "`" * (longest + 1)
    return f"{fence} {flat} {fence}"
