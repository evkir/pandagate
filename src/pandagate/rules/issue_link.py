"""R1 - is an issue linked from the pull request.

The rule reads the title and the body only. It does not fetch the issue,
and it does not judge whether the issue is a good one.
"""

import re
from collections.abc import Mapping
from typing import Any

from pandagate.facts import PullRequestFacts
from pandagate.rules.base import Outcome, Signal

MAINTAINER_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})

_FENCED_CODE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_HASH_REFERENCE = re.compile(r"(?<![\w/])#(\d+)\b")
_GH_REFERENCE = re.compile(r"(?<![\w/])GH-(\d+)\b", re.IGNORECASE)
_URL_REFERENCE = re.compile(
    r"https?://github\.com/([\w.-]+)/([\w.-]+)/(?:issues|pull)/(\d+)\b", re.IGNORECASE
)
_CLOSING_KEYWORD = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b", re.IGNORECASE
)


def strip_code(text: str) -> str:
    """Drop fenced and inline code so that code samples do not count as links."""
    return _INLINE_CODE.sub(" ", _FENCED_CODE.sub(" ", text))


def find_references(text: str, repository: str, own_number: int) -> tuple[int, ...]:
    """Issue or pull request numbers referenced for this same repository.

    A reference to the pull request's own number is not a link to anything,
    and a full URL pointing at another repository is a mention of that
    repository, not a link in this one.
    """
    found: set[int] = set()
    for pattern in (_HASH_REFERENCE, _GH_REFERENCE):
        found.update(int(match.group(1)) for match in pattern.finditer(text))
    for owner, name, number in _URL_REFERENCE.findall(text):
        if f"{owner}/{name}".casefold() == repository.casefold():
            found.add(int(number))
    found.discard(own_number)
    return tuple(sorted(found))


def find_closing_references(text: str, own_number: int) -> tuple[int, ...]:
    """Numbers tied to a closing keyword, such as "fixes #411"."""
    found = {int(number) for number in _CLOSING_KEYWORD.findall(text)}
    found.discard(own_number)
    return tuple(sorted(found))


class IssueLinkRule:
    """Reports whether the pull request points at an issue in this repository."""

    rule_id = "R1"
    title = "Linked issue"

    def evaluate(self, facts: PullRequestFacts, options: Mapping[str, Any]) -> Signal:
        associations = frozenset(
            str(value).upper()
            for value in options.get("maintainer_associations", MAINTAINER_ASSOCIATIONS)
        )
        if facts.author_association.upper() in associations:
            return Signal(
                self.rule_id,
                self.title,
                Outcome.NOT_APPLICABLE,
                "author is a maintainer of this repository",
            )

        text = strip_code(f"{facts.title}\n{facts.body}")
        if options.get("require_closing_keyword", False):
            numbers = find_closing_references(text, facts.number)
            missing = "no closing keyword and issue reference"
        else:
            numbers = find_references(text, facts.repository, facts.number)
            missing = "no issue reference"

        if numbers:
            listed = ", ".join(f"#{number}" for number in numbers)
            return Signal(self.rule_id, self.title, Outcome.PRESENT, f"references {listed}")

        return Signal(
            self.rule_id,
            self.title,
            Outcome.ABSENT,
            f"{missing} in the title or body",
            "Which issue does this address? If there is none, what did you observe "
            "that made this change necessary?",
        )


RULE = IssueLinkRule()
