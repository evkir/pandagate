"""R1 - is an issue linked from the pull request.

The rule reads the title and the body only. It does not fetch the issue,
and it does not judge whether the issue is a good one.
"""

import re
from collections.abc import Mapping
from typing import Any

from pandagate.facts import PullRequestFacts
from pandagate.rules.base import Outcome, Signal, register

MAINTAINER_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})

_FENCED_CODE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_HASH_REFERENCE = re.compile(r"(?<![\w/])#(\d+)\b")
_GH_REFERENCE = re.compile(r"(?<![\w/])GH-(\d+)\b", re.IGNORECASE)
_URL_REFERENCE = re.compile(
    r"https?://github\.com/([\w.-]+)/([\w.-]+)/(?:issues|pull)/(\d+)\b", re.IGNORECASE
)
_REPOSITORY = r"([A-Za-z0-9][A-Za-z0-9-]{0,38})/([\w.-]{1,100})"
_QUALIFIED_REFERENCE = re.compile(rf"(?<![\w./-]){_REPOSITORY}#(\d+)\b")
_CLOSING_KEYWORD = re.compile(
    rf"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+(?:{_REPOSITORY})?#(\d+)\b", re.IGNORECASE
)


def strip_code(text: str) -> str:
    """Drop fenced and inline code so that code samples do not count as links."""
    return _INLINE_CODE.sub(" ", _FENCED_CODE.sub(" ", text))


def find_references(text: str, repository: str, own_number: int) -> tuple[int, ...]:
    """Issue or pull request numbers referenced for this same repository.

    A reference to the pull request's own number is not a link to anything.
    References to other repositories are found by find_external_references.
    """
    found: set[int] = set()
    for pattern in (_HASH_REFERENCE, _GH_REFERENCE):
        found.update(int(match.group(1)) for match in pattern.finditer(text))
    for pattern in (_QUALIFIED_REFERENCE, _URL_REFERENCE):
        for owner, name, number in pattern.findall(text):
            if f"{owner}/{name}".casefold() == repository.casefold():
                found.add(int(number))
    found.discard(own_number)
    return tuple(sorted(found))


def find_external_references(text: str, repository: str) -> tuple[str, ...]:
    """References to issues or pull requests in other repositories.

    They are written as owner/name#N or as a full URL. Each one is returned
    once, as owner/name#N, ordered by repository and number.
    """
    found: dict[tuple[str, int], str] = {}
    for pattern in (_QUALIFIED_REFERENCE, _URL_REFERENCE):
        for owner, name, number in pattern.findall(text):
            slug = f"{owner}/{name}"
            if slug.casefold() != repository.casefold():
                found.setdefault((slug.casefold(), int(number)), f"{slug}#{int(number)}")
    return tuple(found[key] for key in sorted(found))


def find_closing_references(text: str, repository: str, own_number: int) -> tuple[int, ...]:
    """Numbers tied to a closing keyword, such as "fixes #411".

    The number may be qualified with this repository, as in
    "closes evkir/pandagate#411".
    """
    found: set[int] = set()
    for owner, name, number in _CLOSING_KEYWORD.findall(text):
        if not owner or f"{owner}/{name}".casefold() == repository.casefold():
            found.add(int(number))
    found.discard(own_number)
    return tuple(sorted(found))


class IssueLinkRule:
    """Reports whether the pull request points at an issue, here or elsewhere."""

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
            numbers = find_closing_references(text, facts.repository, facts.number)
            external: tuple[str, ...] = ()
            missing = "no closing keyword and issue reference"
        else:
            numbers = find_references(text, facts.repository, facts.number)
            external = find_external_references(text, facts.repository)
            missing = "no issue reference"

        if numbers or external:
            listed = ", ".join([*(f"#{number}" for number in numbers), *external])
            return Signal(self.rule_id, self.title, Outcome.PRESENT, f"references {listed}")

        return Signal(
            self.rule_id,
            self.title,
            Outcome.ABSENT,
            f"{missing} in the title or body",
            "Which issue does this address? If there is none, what did you observe "
            "that made this change necessary?",
        )


RULE = register(IssueLinkRule())
