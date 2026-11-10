"""Tests for turning a report into the text of one comment."""

import inspect
import re
from typing import Any

import pytest

from pandagate.config import CONFIG_FILENAME, Config
from pandagate.facts import ChangedFile, PullRequestFacts
from pandagate.render import MARKER, MAX_FRAGMENT_CHARS, MAX_NOTES, render
from pandagate.rules import diff_cohesion, issue_link, tests_with_code
from pandagate.rules.base import Outcome, Signal
from pandagate.score import Report, score

#: Words the comment must never say in its own voice. The action reports
#: what it observes about a pull request and says nothing about its origin.
FORBIDDEN_WORDS = ("ai", "llm", "generated", "bot", "authorship")

GITHUB_COMMENT_LIMIT = 65_536

_FORBIDDEN = re.compile(r"(?<![a-z])(?:" + "|".join(FORBIDDEN_WORDS) + r")(?![a-z])", re.IGNORECASE)
_CODE_SPAN = re.compile(r"(`+) .*? \1(?!`)")

SHIPPED_RULES = {
    rule.rule_id: rule for rule in (issue_link.RULE, tests_with_code.RULE, diff_cohesion.RULE)
}


def forbidden_in(text: str) -> list[str]:
    return [match.group(0).lower() for match in _FORBIDDEN.finditer(text)]


def outside_code(text: str) -> str:
    return _CODE_SPAN.sub("", text)


def make_facts(**overrides: Any) -> PullRequestFacts:
    fields: dict[str, Any] = {
        "repository": "octocat/example",
        "number": 42,
        "title": "Add a thing",
        "body": "",
        "author": "contributor",
        "author_association": "CONTRIBUTOR",
        "base_ref": "main",
        "commits": 1,
        "additions": 10,
        "deletions": 2,
        "changed_files": (),
    }
    fields.update(overrides)
    return PullRequestFacts(**fields)


def changed(path: str) -> ChangedFile:
    return ChangedFile(path, "modified", 20, 3)


def absent(rule_id: str = "R1", detail: str = "no issue reference") -> Signal:
    question = f"Question of {rule_id}?"
    return Signal(rule_id, f"Title of {rule_id}", Outcome.ABSENT, detail, question)


def other(rule_id: str, outcome: Outcome, detail: str = "observed") -> Signal:
    return Signal(rule_id, f"Title of {rule_id}", outcome, detail)


def rendered(report: Report) -> str:
    text = render(report)
    assert text is not None
    return text


FACT_MATRIX = {
    "nothing_found": make_facts(
        changed_files=tuple(
            changed(f"src/{area}/engine.py") for area in ("alpha", "beta", "gamma", "delta")
        ),
    ),
    "everything_found": make_facts(
        title="Fix the parser",
        body="Fixes #7",
        changed_files=(changed("src/alpha/engine.py"), changed("tests/test_engine.py")),
    ),
    "truncated": make_facts(
        changed_files=(changed("src/alpha/engine.py"),),
        files_truncated=True,
    ),
    "docs_only": make_facts(changed_files=(changed("README.md"), changed("docs/guide.md"))),
    "maintainer": make_facts(
        author_association="OWNER",
        changed_files=(changed("src/alpha/engine.py"),),
    ),
}


def test_a_report_with_nothing_to_ask_renders_no_comment() -> None:
    report = Report(
        (
            other("R1", Outcome.PRESENT),
            other("R2", Outcome.NOT_APPLICABLE),
            other("R3", Outcome.UNKNOWN),
        )
    )
    assert render(report) is None


def test_an_empty_report_renders_no_comment() -> None:
    assert render(Report()) is None


def test_notes_alone_render_no_comment() -> None:
    assert render(Report((), ("unknown key: verdict",))) is None


def test_a_comment_starts_with_the_marker() -> None:
    assert rendered(Report((absent(),))).startswith(MARKER + "\n")


def test_an_absent_signal_shows_its_detail_and_its_question() -> None:
    lines = rendered(Report((absent(),))).splitlines()
    assert "- **Title of R1** (` R1 `): ` no issue reference `" in lines
    assert "  - Question of R1?" in lines


def test_only_absent_signals_carry_a_question_and_not_applicable_is_left_out() -> None:
    report = Report(
        (
            absent("R1"),
            other("R2", Outcome.PRESENT, "tests changed"),
            other("R3", Outcome.NOT_APPLICABLE, "no logic files changed"),
            other("R4", Outcome.UNKNOWN, "the file list was truncated"),
        )
    )
    lines = rendered(report).splitlines()
    assert "- **Title of R2** (` R2 `): ` tests changed `" in lines
    assert "- **Title of R4** (` R4 `): ` the file list was truncated `" in lines
    assert not any("Title of R3" in line for line in lines)
    assert sum(line.startswith("  - ") for line in lines) == 1


def test_signals_keep_report_order() -> None:
    text = rendered(Report((absent("R1"), absent("R2"), absent("R3"))))
    positions = [text.index(f"Title of {rule_id}") for rule_id in ("R1", "R2", "R3")]
    assert positions == sorted(positions)


def test_backticks_in_data_cannot_close_the_code_span() -> None:
    text = rendered(Report((absent(detail="a ``` b"),)))
    assert "```` a ``` b ````" in text


def test_line_breaks_in_data_cannot_start_a_new_block() -> None:
    text = rendered(Report((absent(detail="x\n\n## Heading\n- item"),)))
    assert "` x ## Heading - item `" in text
    assert not any(line.startswith("## Heading") for line in text.splitlines())


def test_a_mention_in_data_stays_inside_a_code_span() -> None:
    text = rendered(Report((absent(detail="2 area(s) touched: @everyone/core"),)))
    assert "@everyone/core" in text
    assert "@" not in outside_code(text)


def test_invisible_characters_are_dropped() -> None:
    text = rendered(Report((absent(detail="safe\u202egnp.exe\u200b"),)))
    assert "` safegnp.exe `" in text
    assert "\u202e" not in text
    assert "\u200b" not in text


def test_a_lone_surrogate_cannot_make_the_comment_unencodable() -> None:
    text = rendered(Report((absent(detail="a\ud800b"),)))
    assert "` ab `" in text
    assert text.encode("utf-8")


def test_a_blank_detail_is_shown_as_empty() -> None:
    text = rendered(Report((absent(detail="  \n "),)))
    assert "` (empty) `" in text


def test_a_long_detail_is_clipped() -> None:
    text = rendered(Report((absent(detail="x" * 5000),)))
    assert "x" * MAX_FRAGMENT_CHARS + " \u2026" in text
    assert "x" * (MAX_FRAGMENT_CHARS + 1) not in text


def test_notes_about_the_run_are_folded_away() -> None:
    lines = rendered(Report((absent(),), ("unknown key: verdict",))).splitlines()
    assert "<details>" in lines
    assert "</details>" in lines
    assert "- ` unknown key: verdict `" in lines


def test_no_notes_means_no_folded_block() -> None:
    assert "<details>" not in rendered(Report((absent(),)))


def test_notes_are_capped() -> None:
    warnings = tuple(f"unknown key: k{index}" for index in range(MAX_NOTES + 7))
    lines = rendered(Report((absent(),), warnings)).splitlines()
    assert f"- ` unknown key: k{MAX_NOTES - 1} `" in lines
    assert f"- ` unknown key: k{MAX_NOTES} `" not in lines
    assert "- and 7 more" in lines


def test_a_pathological_report_fits_in_one_comment() -> None:
    signals = tuple(absent(f"R{index}", "d" * 10_000) for index in range(40))
    warnings = tuple("w" * 10_000 for _ in range(500))
    assert len(rendered(Report(signals, warnings))) < GITHUB_COMMENT_LIMIT


def test_the_footer_names_the_configuration_file() -> None:
    last = rendered(Report((absent(),))).splitlines()[-1]
    assert last.startswith("<sub>")
    assert CONFIG_FILENAME in last


def test_words_in_data_do_not_leak_outside_code_spans() -> None:
    report = Report(
        (absent("R3", "2 area(s) of logic touched: src/ai, src/bot"),),
        ("unknown key: llm",),
    )
    text = rendered(report)
    assert forbidden_in(text) == ["ai", "bot", "llm"]
    assert forbidden_in(outside_code(text)) == []


def test_the_module_source_stays_inside_the_vocabulary() -> None:
    source = inspect.getsource(inspect.getmodule(render))
    assert forbidden_in(source) == []


@pytest.mark.parametrize("facts", list(FACT_MATRIX.values()), ids=list(FACT_MATRIX))
def test_the_shipped_rules_stay_inside_the_vocabulary(facts: PullRequestFacts) -> None:
    report = score(facts, Config(), SHIPPED_RULES)
    assert len(report.signals) == 3
    assert report.warnings == ()
    for signal in report.signals:
        spoken = f"{signal.title}\n{signal.detail}\n{signal.question or ''}"
        assert forbidden_in(spoken) == []
    text = render(report)
    if text is not None:
        assert forbidden_in(text) == []


def test_the_shipped_rules_render_three_questions_when_nothing_is_found() -> None:
    report = score(FACT_MATRIX["nothing_found"], Config(), SHIPPED_RULES)
    assert [signal.outcome for signal in report.signals] == [Outcome.ABSENT] * 3
    lines = rendered(report).splitlines()
    assert sum(line.startswith("  - ") for line in lines) == 3


def test_text_from_the_pull_request_only_ever_lands_inside_code_spans() -> None:
    facts = make_facts(
        title="@evil-team take a look",
        body="@evil-team [click](https://example.invalid)",
        changed_files=(
            changed("@evil-team/alpha/engine.py"),
            changed("@evil-team/beta/engine.py"),
        ),
    )
    report = score(facts, Config(), SHIPPED_RULES)
    assert any("evil-team" in signal.detail for signal in report.signals)
    for signal in report.signals:
        assert "evil-team" not in signal.title
        assert "evil-team" not in (signal.question or "")
    assert "@" not in outside_code(rendered(report))
