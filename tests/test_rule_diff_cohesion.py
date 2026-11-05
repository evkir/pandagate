"""Tests for R3, diff cohesion."""

from pandagate.facts import ChangedFile, PullRequestFacts
from pandagate.rules.base import Outcome
from pandagate.rules.diff_cohesion import RULE, area_of


def _file(path: str, status: str = "modified", additions: int = 10) -> ChangedFile:
    return ChangedFile(path=path, status=status, additions=additions, deletions=0)


def _facts(*files: ChangedFile, truncated: bool = False) -> PullRequestFacts:
    return PullRequestFacts(
        repository="evkir/pandagate",
        number=412,
        title="Change",
        body="",
        author="contributor",
        author_association="NONE",
        base_ref="main",
        commits=1,
        additions=sum(f.additions for f in files),
        deletions=0,
        changed_files=files,
        files_truncated=truncated,
    )


def test_area_is_the_first_two_segments_by_default() -> None:
    assert area_of("src/pandagate/rules/base.py", 2) == "src/pandagate"


def test_area_of_a_root_file_is_named() -> None:
    assert area_of("main.py", 2) == "(root)"


def test_shallow_path_keeps_what_it_has() -> None:
    assert area_of("src/main.py", 2) == "src"


def test_truncated_file_list_is_unknown() -> None:
    signal = RULE.evaluate(_facts(_file("src/app/a.py"), truncated=True), {})
    assert signal.outcome is Outcome.UNKNOWN


def test_single_area_is_present() -> None:
    files = [_file("src/app/a.py"), _file("src/app/sub/b.py")]
    signal = RULE.evaluate(_facts(*files), {})
    assert signal.outcome is Outcome.PRESENT
    assert signal.detail == "1 area(s) of logic touched: src/app"


def test_tests_docs_and_config_do_not_count_as_areas() -> None:
    files = [
        _file("src/app/a.py"),
        _file("tests/test_a.py"),
        _file("docs/guide.md"),
        _file("CHANGELOG.md"),
        _file(".github/workflows/ci.yml"),
    ]
    signal = RULE.evaluate(_facts(*files), {})
    assert signal.outcome is Outcome.PRESENT
    assert signal.detail == "1 area(s) of logic touched: src/app"


def test_four_areas_exceed_the_default_threshold() -> None:
    files = [_file(f"src/mod{n}/a.py") for n in range(4)]
    signal = RULE.evaluate(_facts(*files), {})
    assert signal.outcome is Outcome.ABSENT
    assert "above the 3 area threshold" in signal.detail
    assert signal.question is not None


def test_monorepo_packages_are_distinct_areas() -> None:
    files = [_file(f"packages/p{n}/index.ts") for n in range(4)]
    assert RULE.evaluate(_facts(*files), {}).outcome is Outcome.ABSENT


def test_depth_one_treats_a_monorepo_as_one_area() -> None:
    files = [_file(f"packages/p{n}/index.ts") for n in range(4)]
    signal = RULE.evaluate(_facts(*files), {"area_depth": 1})
    assert signal.outcome is Outcome.PRESENT
    assert signal.detail == "1 area(s) of logic touched: packages"


def test_threshold_is_configurable() -> None:
    files = [_file(f"src/mod{n}/a.py") for n in range(4)]
    assert RULE.evaluate(_facts(*files), {"max_areas": 10}).outcome is Outcome.PRESENT
    assert RULE.evaluate(_facts(*files), {"max_areas": 1}).outcome is Outcome.ABSENT


def test_a_wide_pure_rename_is_not_scattered() -> None:
    files = [_file(f"src/mod{n}/a.py", status="renamed", additions=0) for n in range(6)]
    assert RULE.evaluate(_facts(*files), {}).outcome is Outcome.NOT_APPLICABLE


def test_documentation_only_change_is_out_of_scope() -> None:
    assert RULE.evaluate(_facts(_file("README.md")), {}).outcome is Outcome.NOT_APPLICABLE


def test_degenerate_options_are_clamped() -> None:
    files = [_file("src/app/a.py")]
    assert RULE.evaluate(_facts(*files), {"area_depth": 0}).outcome is Outcome.PRESENT
    assert RULE.evaluate(_facts(*files), {"max_areas": 0}).outcome is Outcome.PRESENT
