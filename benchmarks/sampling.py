"""Choosing the benchmark sample: which pull requests qualify and when to stop.

Nothing here touches the network. The rules are the ones fixed in README.md.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

CUTOFF = "2026-10-01T00:00:00Z"
OUTSIDE_ASSOCIATIONS = frozenset({"CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "NONE"})
PER_REPOSITORY = 20
SCAN_LIMIT = 1000

REPOSITORIES = (
    "pytest-dev/pytest",
    "pandas-dev/pandas",
    "astral-sh/ruff",
    "tokio-rs/tokio",
    "vitejs/vite",
    "withastro/astro",
    "prometheus/prometheus",
    "cli/cli",
    "neovim/neovim",
    "godotengine/godot",
)
RESERVE = ("helix-editor/helix", "home-assistant/core")

_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def created_before_cutoff(pull: Mapping[str, Any]) -> bool:
    """Whether the pull request was opened before the cutoff."""
    created = _text(pull.get("created_at"))
    # Timestamps of this one shape order the same way as the moments they name.
    return bool(_TIMESTAMP.fullmatch(created)) and created < CUTOFF


def qualifies(pull: Mapping[str, Any]) -> bool:
    """Whether a pull request is merged work by an outside user account."""
    user = pull.get("user")
    return (
        bool(_text(pull.get("merged_at")))
        and isinstance(user, Mapping)
        and user.get("type") == "User"
        and _text(pull.get("author_association")) in OUTSIDE_ASSOCIATIONS
    )


@dataclass(frozen=True)
class Selection:
    """What one repository gave: the chosen pull requests and how many were looked at."""

    picked: tuple[Mapping[str, Any], ...]
    scanned: int

    @property
    def complete(self) -> bool:
        return len(self.picked) == PER_REPOSITORY


def select(pulls: Iterable[Mapping[str, Any]]) -> Selection:
    """Take the first qualifying pull requests from a newest-first stream.

    Pull requests opened at or after the cutoff are passed over without being
    counted. Reading stops as soon as the quota is full or the scan limit is hit.
    """
    picked: list[Mapping[str, Any]] = []
    scanned = 0
    for pull in pulls:
        if not created_before_cutoff(pull):
            continue
        scanned += 1
        if qualifies(pull):
            picked.append(pull)
        if len(picked) == PER_REPOSITORY or scanned == SCAN_LIMIT:
            break
    return Selection(tuple(picked), scanned)


def entry(repository: str, pull: Mapping[str, Any]) -> dict[str, Any]:
    """The record kept in the committed sample for one pull request."""
    return {
        "repository": repository,
        "number": pull.get("number"),
        "url": _text(pull.get("html_url")),
        "created_at": _text(pull.get("created_at")),
        "merged_at": _text(pull.get("merged_at")),
        "author_association": _text(pull.get("author_association")),
    }
