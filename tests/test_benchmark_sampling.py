from pathlib import Path
from typing import Any

import pytest

from benchmarks.sampling import (
    CUTOFF,
    OUTSIDE_ASSOCIATIONS,
    PER_REPOSITORY,
    REPOSITORIES,
    RESERVE,
    SCAN_LIMIT,
    created_before_cutoff,
    entry,
    qualifies,
    select,
)

PROTOCOL = Path(__file__).resolve().parent.parent / "benchmarks" / "README.md"


def pull(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "number": 7,
        "html_url": "https://github.com/octo/demo/pull/7",
        "created_at": "2026-09-30T23:59:59Z",
        "merged_at": "2026-10-02T10:00:00Z",
        "author_association": "CONTRIBUTOR",
        "user": {"login": "someone", "type": "User"},
    }
    return base | changes


def test_merged_pull_request_from_an_outside_user_qualifies():
    assert qualifies(pull())


@pytest.mark.parametrize("association", sorted(OUTSIDE_ASSOCIATIONS))
def test_every_outside_association_qualifies(association):
    assert qualifies(pull(author_association=association))


@pytest.mark.parametrize("association", ["OWNER", "MEMBER", "COLLABORATOR", "MANNEQUIN", None])
def test_other_associations_do_not_qualify(association):
    assert not qualifies(pull(author_association=association))


def test_unmerged_pull_request_does_not_qualify():
    assert not qualifies(pull(merged_at=None))


@pytest.mark.parametrize("user", [{"login": "dependabot[bot]", "type": "Bot"}, None, {}, "ghost"])
def test_only_user_accounts_qualify(user):
    assert not qualifies(pull(user=user))


@pytest.mark.parametrize(
    ("created_at", "expected"),
    [
        ("2026-09-30T23:59:59Z", True),
        (CUTOFF, False),
        ("2026-09-30", False),
        ("", False),
        (None, False),
    ],
)
def test_created_before_cutoff(created_at, expected):
    assert created_before_cutoff(pull(created_at=created_at)) is expected


def test_select_stops_reading_once_the_quota_is_full():
    seen = []

    def stream():
        for number in range(100):
            seen.append(number)
            yield pull(number=number)

    chosen = select(stream())

    assert chosen.complete
    assert chosen.scanned == PER_REPOSITORY
    assert seen == list(range(PER_REPOSITORY))


def test_select_keeps_the_order_of_the_stream():
    stream = [pull(number=3), pull(number=2, merged_at=None), pull(number=1)]

    chosen = select(stream)

    assert [picked["number"] for picked in chosen.picked] == [3, 1]
    assert chosen.scanned == 3
    assert not chosen.complete


def test_select_does_not_count_pull_requests_opened_after_the_cutoff():
    late = [pull(created_at=CUTOFF) for _ in range(SCAN_LIMIT)]

    chosen = select([*late, pull(number=1)])

    assert [picked["number"] for picked in chosen.picked] == [1]
    assert chosen.scanned == 1


def test_select_gives_up_at_the_scan_limit():
    stream = [pull(merged_at=None) for _ in range(SCAN_LIMIT)] + [pull(number=1)]

    chosen = select(stream)

    assert chosen.picked == ()
    assert chosen.scanned == SCAN_LIMIT


def test_entry_keeps_only_what_the_sample_needs():
    assert entry("octo/demo", pull()) == {
        "repository": "octo/demo",
        "number": 7,
        "url": "https://github.com/octo/demo/pull/7",
        "created_at": "2026-09-30T23:59:59Z",
        "merged_at": "2026-10-02T10:00:00Z",
        "author_association": "CONTRIBUTOR",
    }


def test_sample_size_matches_the_protocol():
    assert len(REPOSITORIES) * PER_REPOSITORY == 200
    assert len(set(REPOSITORIES)) == len(REPOSITORIES)
    assert not set(REPOSITORIES) & set(RESERVE)


def test_protocol_names_what_the_code_uses():
    text = PROTOCOL.read_text(encoding="utf-8")

    for repository in (*REPOSITORIES, *RESERVE):
        assert f"`{repository}`" in text
    for association in OUTSIDE_ASSOCIATIONS:
        assert f"`{association}`" in text
    assert f"`{CUTOFF}`" in text
    assert f"first {PER_REPOSITORY} pull requests" in text
    assert f"its {SCAN_LIMIT} most recent closed pull" in text
