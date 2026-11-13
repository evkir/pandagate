"""The Marketplace listing name, which GitHub requires to be unique."""

from pathlib import Path

ACTION = Path(__file__).resolve().parent.parent / "action.yml"

LISTING_NAME = "PandaGate PR Facts"


def test_listing_name_is_the_one_the_marketplace_accepted() -> None:
    # GitHub refuses a listing name equal to an existing user or organization
    # login, and the login `pandagate` belongs to someone else.
    first_line = ACTION.read_text(encoding="utf-8").splitlines()[0]
    assert first_line == f"name: {LISTING_NAME}"
