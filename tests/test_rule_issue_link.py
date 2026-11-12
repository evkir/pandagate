"""Tests for R1, the linked issue rule."""

from pandagate.facts import ChangedFile, PullRequestFacts
from pandagate.rules.base import Outcome
from pandagate.rules.issue_link import (
    DEFAULT_MIN_LOGIC_LINES,
    RULE,
    find_external_references,
    find_references,
    strip_code,
)
from pandagate.rules.tests_with_code import DEFAULT_MIN_LOGIC_LINES as R2_MIN_LOGIC_LINES

_LOGIC = (ChangedFile("src/pandagate/score.py", "modified", 9, 1),)


def _facts(
    title: str = "",
    body: str = "",
    *,
    association: str = "NONE",
    files: tuple[ChangedFile, ...] = _LOGIC,
    truncated: bool = False,
) -> PullRequestFacts:
    return PullRequestFacts(
        repository="evkir/pandagate",
        number=412,
        title=title,
        body=body,
        author="contributor",
        author_association=association,
        base_ref="main",
        commits=1,
        additions=10,
        deletions=1,
        changed_files=files,
        files_truncated=truncated,
    )


def test_hash_reference_in_the_body_is_present() -> None:
    signal = RULE.evaluate(_facts(body="Closes #411"), {})
    assert signal.outcome is Outcome.PRESENT
    assert signal.detail == "references #411"
    assert signal.question is None


def test_reference_in_the_title_counts() -> None:
    assert RULE.evaluate(_facts(title="Fix parser (#77)"), {}).outcome is Outcome.PRESENT


def test_gh_prefixed_reference_counts() -> None:
    assert RULE.evaluate(_facts(body="see GH-88"), {}).outcome is Outcome.PRESENT


def test_full_url_for_this_repository_counts() -> None:
    body = "https://github.com/evkir/pandagate/issues/99"
    assert RULE.evaluate(_facts(body=body), {}).outcome is Outcome.PRESENT


def test_full_url_for_another_repository_counts() -> None:
    body = "inspired by https://github.com/other/project/issues/99"
    signal = RULE.evaluate(_facts(body=body), {})
    assert signal.outcome is Outcome.PRESENT
    assert signal.detail == "references other/project#99"


def test_reference_inside_a_fenced_code_block_does_not_count() -> None:
    body = "example output:\n```\nerror at line #411\n```\n"
    assert RULE.evaluate(_facts(body=body), {}).outcome is Outcome.ABSENT


def test_reference_inside_inline_code_does_not_count() -> None:
    assert RULE.evaluate(_facts(body="prints `#411` on failure"), {}).outcome is Outcome.ABSENT


def test_own_number_is_not_a_link() -> None:
    assert RULE.evaluate(_facts(body="supersedes #412"), {}).outcome is Outcome.ABSENT


def test_hex_colour_is_not_a_reference() -> None:
    assert RULE.evaluate(_facts(body="use #1a2b3c for the border"), {}).outcome is Outcome.ABSENT


def test_markdown_heading_is_not_a_reference() -> None:
    assert RULE.evaluate(_facts(body="# Summary\n\nrefactor only"), {}).outcome is Outcome.ABSENT


def test_empty_description_is_absent_with_a_question() -> None:
    signal = RULE.evaluate(_facts(), {})
    assert signal.outcome is Outcome.ABSENT
    assert signal.question is not None


def test_maintainer_author_is_out_of_scope() -> None:
    signal = RULE.evaluate(_facts(association="OWNER"), {})
    assert signal.outcome is Outcome.NOT_APPLICABLE
    assert signal.question is None


def test_maintainer_associations_are_configurable() -> None:
    options = {"maintainer_associations": ["CONTRIBUTOR"]}
    assert RULE.evaluate(_facts(association="CONTRIBUTOR"), options).outcome is (
        Outcome.NOT_APPLICABLE
    )


def test_closing_keyword_can_be_required() -> None:
    options = {"require_closing_keyword": True}
    assert RULE.evaluate(_facts(body="related to #411"), options).outcome is Outcome.ABSENT
    assert RULE.evaluate(_facts(body="fixes #411"), options).outcome is Outcome.PRESENT


def test_several_references_are_listed_in_order() -> None:
    signal = RULE.evaluate(_facts(body="closes #9, closes #411"), {})
    assert signal.detail == "references #9, #411"


def test_strip_code_removes_both_code_forms() -> None:
    assert "#1" not in strip_code("a `#1` b")
    assert "#2" not in strip_code("a\n```\n#2\n```\nb")


def test_find_references_is_case_insensitive_about_the_repository() -> None:
    body = "https://github.com/EvKir/PandaGate/issues/5"
    assert find_references(body, "evkir/pandagate", 412) == (5,)


def test_reference_qualified_with_this_repository_counts() -> None:
    signal = RULE.evaluate(_facts(body="Closes EvKir/PandaGate#411"), {})
    assert signal.outcome is Outcome.PRESENT
    assert signal.detail == "references #411"


def test_closing_keyword_accepts_a_qualified_reference() -> None:
    options = {"require_closing_keyword": True}
    body = "Closes evkir/pandagate#411"
    assert RULE.evaluate(_facts(body=body), options).outcome is Outcome.PRESENT


def test_own_number_qualified_with_this_repository_is_not_a_link() -> None:
    assert RULE.evaluate(_facts(body="see evkir/pandagate#412"), {}).outcome is Outcome.ABSENT


def test_reference_qualified_with_another_repository_counts() -> None:
    signal = RULE.evaluate(_facts(body="Fixes astral-sh/ty#1234"), {})
    assert signal.outcome is Outcome.PRESENT
    assert signal.detail == "references astral-sh/ty#1234"


def test_external_references_follow_own_numbers_and_are_listed_once() -> None:
    body = "closes #9, see Other/Project#3 and https://github.com/other/project/issues/3"
    assert RULE.evaluate(_facts(body=body), {}).detail == "references #9, Other/Project#3"


def test_own_number_in_another_repository_is_a_link() -> None:
    assert RULE.evaluate(_facts(body="port of other/project#412"), {}).outcome is Outcome.PRESENT


def test_external_reference_inside_inline_code_does_not_count() -> None:
    assert RULE.evaluate(_facts(body="run `other/project#3`"), {}).outcome is Outcome.ABSENT


def test_a_longer_path_is_not_a_qualified_reference() -> None:
    assert RULE.evaluate(_facts(body="see src/a/b#3"), {}).outcome is Outcome.ABSENT


def test_find_external_references_orders_and_deduplicates() -> None:
    text = "a/b#2 a/b#1 A/B#2 evkir/pandagate#7"
    assert find_external_references(text, "evkir/pandagate") == ("a/b#1", "a/b#2")


def test_closing_keyword_accepts_other_repositories_and_urls() -> None:
    options = {"require_closing_keyword": True}
    expected = {
        "Fixes astral-sh/ty#1234": "references astral-sh/ty#1234",
        "Closes https://github.com/evkir/pandagate/issues/411": "references #411",
        "Resolves https://github.com/other/project/issues/7": "references other/project#7",
    }
    for body, detail in expected.items():
        signal = RULE.evaluate(_facts(body=body), options)
        assert signal.outcome is Outcome.PRESENT
        assert signal.detail == detail


def test_required_closing_keyword_ignores_plain_mentions_and_own_number() -> None:
    options = {"require_closing_keyword": True}
    bodies = [
        "see other/project#7 and https://github.com/other/project/issues/8",
        "closes https://github.com/evkir/pandagate/pull/412",
    ]
    for body in bodies:
        assert RULE.evaluate(_facts(body=body), options).outcome is Outcome.ABSENT


def test_change_without_logic_files_is_out_of_scope() -> None:
    files = (ChangedFile("docs/guide.md", "modified", 40, 2),)
    signal = RULE.evaluate(_facts(files=files), {})
    assert signal.outcome is Outcome.NOT_APPLICABLE
    assert signal.detail == "no logic files changed"


def test_pull_request_without_files_is_out_of_scope() -> None:
    signal = RULE.evaluate(_facts(files=()), {})
    assert signal.outcome is Outcome.NOT_APPLICABLE
    assert signal.detail == "no logic files changed"


def test_logic_below_the_threshold_is_out_of_scope() -> None:
    files = (ChangedFile("src/pandagate/score.py", "modified", 3, 1),)
    signal = RULE.evaluate(_facts(files=files), {})
    assert signal.outcome is Outcome.NOT_APPLICABLE
    assert signal.detail == "4 line(s) of logic changed, below the 5 line threshold"


def test_logic_at_the_threshold_is_in_scope() -> None:
    files = (ChangedFile("src/pandagate/score.py", "modified", 4, 1),)
    signal = RULE.evaluate(_facts(files=files), {})
    assert signal.outcome is Outcome.ABSENT


def test_small_change_is_out_of_scope_even_with_a_link() -> None:
    files = (ChangedFile("src/pandagate/score.py", "modified", 1, 1),)
    signal = RULE.evaluate(_facts(body="Closes #411", files=files), {})
    assert signal.outcome is Outcome.NOT_APPLICABLE


def test_test_files_do_not_count_as_logic() -> None:
    files = (ChangedFile("tests/test_score.py", "modified", 50, 0),)
    signal = RULE.evaluate(_facts(files=files), {})
    assert signal.outcome is Outcome.NOT_APPLICABLE
    assert signal.detail == "no logic files changed"


def test_pure_rename_does_not_count_as_logic() -> None:
    files = (ChangedFile("src/pandagate/scoring.py", "renamed", 0, 0),)
    signal = RULE.evaluate(_facts(files=files), {})
    assert signal.outcome is Outcome.NOT_APPLICABLE
    assert signal.detail == "no logic files changed"


def test_threshold_is_configurable() -> None:
    signal = RULE.evaluate(_facts(), {"min_logic_lines": 20})
    assert signal.outcome is Outcome.NOT_APPLICABLE
    assert signal.detail == "10 line(s) of logic changed, below the 20 line threshold"


def test_zero_threshold_asks_about_every_pull_request() -> None:
    signal = RULE.evaluate(_facts(files=()), {"min_logic_lines": 0})
    assert signal.outcome is Outcome.ABSENT


def test_truncated_file_list_below_the_threshold_is_unknown() -> None:
    signal = RULE.evaluate(_facts(files=(), truncated=True), {})
    assert signal.outcome is Outcome.UNKNOWN
    assert "truncated" in signal.detail


def test_truncated_file_list_with_enough_logic_is_read() -> None:
    signal = RULE.evaluate(_facts(body="Closes #411", truncated=True), {})
    assert signal.outcome is Outcome.PRESENT


def test_maintainer_is_out_of_scope_before_size_is_read() -> None:
    signal = RULE.evaluate(_facts(association="OWNER", files=()), {})
    assert signal.outcome is Outcome.NOT_APPLICABLE
    assert signal.detail == "author is a maintainer of this repository"


def test_both_rules_share_the_default_threshold() -> None:
    assert DEFAULT_MIN_LOGIC_LINES == R2_MIN_LOGIC_LINES
