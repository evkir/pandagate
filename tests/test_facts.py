"""Tests for the observable facts model."""

from pandagate.facts import ChangedFile, changed_file_from_api, facts_from_api


def _pr_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "number": 412,
        "title": "Fix crash on empty config",
        "body": "Closes #411",
        "user": {"login": "contributor"},
        "author_association": "FIRST_TIME_CONTRIBUTOR",
        "base": {"ref": "main", "repo": {"full_name": "evkir/pandagate"}},
        "commits": 2,
        "additions": 40,
        "deletions": 3,
    }
    payload.update(overrides)
    return payload


def test_changed_file_top_dir_for_nested_path() -> None:
    assert ChangedFile("src/pandagate/cli.py", "modified", 1, 0).top_dir == "src"


def test_changed_file_top_dir_is_empty_at_repository_root() -> None:
    assert ChangedFile("README.md", "modified", 1, 0).top_dir == ""


def test_facts_from_api_reads_declared_fields() -> None:
    facts = facts_from_api(
        _pr_payload(),
        [{"filename": "src/app.py", "status": "modified", "additions": 40, "deletions": 3}],
    )
    assert facts.repository == "evkir/pandagate"
    assert facts.number == 412
    assert facts.author == "contributor"
    assert facts.author_association == "FIRST_TIME_CONTRIBUTOR"
    assert facts.base_ref == "main"
    assert facts.total_changed_lines == 43
    assert facts.paths == ("src/app.py",)


def test_null_body_becomes_empty_string() -> None:
    facts = facts_from_api(_pr_payload(body=None), [])
    assert facts.body == ""


def test_missing_nested_objects_do_not_raise() -> None:
    facts = facts_from_api({"number": 1}, [])
    assert facts.author == ""
    assert facts.repository == ""
    assert facts.base_ref == ""


def test_touched_top_dirs_are_sorted_and_deduplicated() -> None:
    files = [
        {"filename": "src/a.py", "status": "modified", "additions": 1, "deletions": 0},
        {"filename": "src/b.py", "status": "modified", "additions": 1, "deletions": 0},
        {"filename": "docs/c.md", "status": "added", "additions": 5, "deletions": 0},
        {"filename": "LICENSE", "status": "modified", "additions": 1, "deletions": 1},
    ]
    facts = facts_from_api(_pr_payload(), files)
    assert facts.touched_top_dirs == ("", "docs", "src")


def test_files_truncated_defaults_to_false_and_is_carried() -> None:
    assert facts_from_api(_pr_payload(), []).files_truncated is False
    assert facts_from_api(_pr_payload(), [], files_truncated=True).files_truncated is True


def test_changed_file_from_api_tolerates_missing_counts() -> None:
    changed = changed_file_from_api({"filename": "x.py"})
    assert changed.additions == 0
    assert changed.deletions == 0
    assert changed.status == ""


def test_pure_rename_is_a_move_with_no_line_changes() -> None:
    assert ChangedFile("src/b.py", "renamed", 0, 0).is_pure_rename is True


def test_rename_that_edits_lines_is_not_pure() -> None:
    assert ChangedFile("src/b.py", "renamed", 12, 3).is_pure_rename is False


def test_modified_file_is_never_a_pure_rename() -> None:
    assert ChangedFile("src/b.py", "modified", 0, 0).is_pure_rename is False
