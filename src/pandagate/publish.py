"""Keeping one comment on a pull request, or none.

A run ends in one of three states: the comment is there and current, it
was there and is gone because nothing is left to ask, or it was never
needed. There is never a second comment.

A comment counts as this action's own only when it begins with the
marker and was written by the account the token acts as. The marker
alone proves nothing: anyone who can comment can type it.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pandagate.github import Client, PullRequestRef
from pandagate.render import MARKER


class Change(StrEnum):
    """What one run did to the comment."""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    DELETED = "deleted"
    NOTHING = "nothing"


def publish(client: Client, ref: PullRequestRef, comment: str | None, author: str) -> Change:
    """Bring the pull request to the state this comment describes.

    A comment of None means there is nothing to ask about, and an earlier
    comment is removed. Earlier duplicates are reduced to the first one.
    """
    own = [entry for entry in client.comments(ref) if _is_own(entry, author)]
    ids = [entry["id"] for entry in own]

    if comment is None:
        for comment_id in ids:
            client.delete_comment(ref, comment_id)
        return Change.DELETED if ids else Change.NOTHING

    if not own:
        client.create_comment(ref, comment)
        return Change.CREATED

    for comment_id in ids[1:]:
        client.delete_comment(ref, comment_id)
    if _normalised(own[0]["body"]) == _normalised(comment):
        return Change.UNCHANGED
    client.update_comment(ref, ids[0], comment)
    return Change.UPDATED


def _is_own(entry: Mapping[str, Any], author: str) -> bool:
    comment_id, body, user = entry.get("id"), entry.get("body"), entry.get("user")
    login = user.get("login") if isinstance(user, Mapping) else None
    return (
        isinstance(comment_id, int)
        and not isinstance(comment_id, bool)
        and isinstance(body, str)
        and body.startswith(MARKER)
        and isinstance(login, str)
        and login.casefold() == author.casefold()
    )


def _normalised(text: str) -> str:
    """The text as it compares after a round trip through the API."""
    return text.replace("\r\n", "\n").strip()
