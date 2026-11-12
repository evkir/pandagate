"""Tests for the patch text carried by a changed file."""

from pandagate.facts import ChangedFile, changed_file_from_api, facts_from_api

ENTRY = {
    "filename": "src/lib.rs",
    "status": "modified",
    "additions": 2,
    "deletions": 0,
    "patch": "@@ -1,2 +1,4 @@\n fn a() {}\n+#[test]\n+fn t() {}",
}


def test_patch_is_read_from_the_api_entry() -> None:
    assert changed_file_from_api(ENTRY).patch == ENTRY["patch"]


def test_missing_patch_is_none() -> None:
    entry = {key: value for key, value in ENTRY.items() if key != "patch"}
    assert changed_file_from_api(entry).patch is None


def test_non_string_patch_is_none() -> None:
    assert changed_file_from_api({**ENTRY, "patch": 7}).patch is None


def test_patch_defaults_to_none_for_positional_construction() -> None:
    assert ChangedFile("src/b.py", "modified", 1, 0).patch is None


def test_patch_is_kept_out_of_the_repr() -> None:
    assert "#[test]" not in repr(changed_file_from_api(ENTRY))


def test_facts_carry_the_patch_of_every_file() -> None:
    facts = facts_from_api({}, [ENTRY])
    assert facts.changed_files[0].patch == ENTRY["patch"]
