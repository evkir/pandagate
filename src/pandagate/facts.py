"""Observable facts about a pull request.

Every field here is something GitHub reports directly. Nothing in this
module infers intent, quality or authorship.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ChangedFile:
    """One file touched by a pull request."""

    path: str
    status: str
    additions: int
    deletions: int

    @property
    def top_dir(self) -> str:
        """Top-level directory, or "" for a file at the repository root."""
        head, sep, _ = self.path.partition("/")
        return head if sep else ""

    @property
    def is_pure_rename(self) -> bool:
        """A move that changed no lines - nothing new to review in it."""
        return self.status == "renamed" and self.additions == 0 and self.deletions == 0


@dataclass(frozen=True, slots=True)
class PullRequestFacts:
    """What GitHub reports about one pull request."""

    repository: str
    number: int
    title: str
    body: str
    author: str
    author_association: str
    base_ref: str
    commits: int
    additions: int
    deletions: int
    changed_files: tuple[ChangedFile, ...]
    files_truncated: bool = False

    @property
    def total_changed_lines(self) -> int:
        return self.additions + self.deletions

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(f.path for f in self.changed_files)

    @property
    def touched_top_dirs(self) -> tuple[str, ...]:
        return tuple(sorted({f.top_dir for f in self.changed_files}))


def _as_int(value: Any) -> int:
    return int(value) if isinstance(value, int) else 0


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def changed_file_from_api(payload: Mapping[str, Any]) -> ChangedFile:
    """Build a ChangedFile from one entry of the pull request files endpoint."""
    return ChangedFile(
        path=_as_str(payload.get("filename")),
        status=_as_str(payload.get("status")),
        additions=_as_int(payload.get("additions")),
        deletions=_as_int(payload.get("deletions")),
    )


def facts_from_api(
    pull_request: Mapping[str, Any],
    files: Sequence[Mapping[str, Any]],
    *,
    files_truncated: bool = False,
) -> PullRequestFacts:
    """Build PullRequestFacts from GitHub API responses.

    `files_truncated` must be True when the caller could not read the whole
    file list. Rules that depend on the file list then report UNKNOWN rather
    than drawing a conclusion from a partial diff.
    """
    user = pull_request.get("user")
    base = pull_request.get("base")
    repo = base.get("repo") if isinstance(base, Mapping) else None
    return PullRequestFacts(
        repository=_as_str(repo.get("full_name")) if isinstance(repo, Mapping) else "",
        number=_as_int(pull_request.get("number")),
        title=_as_str(pull_request.get("title")),
        body=_as_str(pull_request.get("body")),
        author=_as_str(user.get("login")) if isinstance(user, Mapping) else "",
        author_association=_as_str(pull_request.get("author_association")),
        base_ref=_as_str(base.get("ref")) if isinstance(base, Mapping) else "",
        commits=_as_int(pull_request.get("commits")),
        additions=_as_int(pull_request.get("additions")),
        deletions=_as_int(pull_request.get("deletions")),
        changed_files=tuple(changed_file_from_api(entry) for entry in files),
        files_truncated=files_truncated,
    )
