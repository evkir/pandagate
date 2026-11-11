"""Applying the labelling draft: what is read, what is refused, what is written."""

import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.apply_draft import DraftError, main, parse_draft
from benchmarks.build_sheet import DRAFT_HEADER, draft_line
from benchmarks.labels import load_labels

COMMIT = "796b735c3b387874fe8e40ec7da0f1f17cc77003"
FIRST = "https://github.com/octo/demo/pull/1"
SECOND = "https://github.com/octo/demo/pull/2"
KEYS = [(FIRST, "R1"), (FIRST, "R2"), (SECOND, "R2")]


def _signal(rule_id: str, outcome: str) -> dict[str, str]:
    return {"rule_id": rule_id, "outcome": outcome, "detail": "observed"}


def _results() -> dict[str, Any]:
    return {
        "pandagate_commit": COMMIT,
        "pull_requests": [
            {"url": FIRST, "signals": [_signal("R1", "ABSENT"), _signal("R2", "ABSENT")]},
            {"url": SECOND, "signals": [_signal("R1", "PRESENT"), _signal("R2", "ABSENT")]},
        ],
    }


def _draft(*answers: str) -> str:
    lines = [*DRAFT_HEADER, ""]
    for number, (key, answer) in enumerate(zip(KEYS, answers, strict=True), start=1):
        lines.append(f"{draft_line(number, key)} {answer}".rstrip())
    return "\n".join(lines) + "\n"


def _paths(tmp_path: Path, draft: str | None) -> dict[str, Path]:
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(_results()), encoding="utf-8")
    draft_path = tmp_path / "draft.txt"
    if draft is not None:
        draft_path.write_text(draft, encoding="utf-8")
    return {
        "draft_path": draft_path,
        "results_path": results_path,
        "labels_path": tmp_path / "labels.json",
    }


def test_an_empty_draft_gives_no_labels() -> None:
    assert parse_draft(_draft("", "", ""), KEYS) == []


def test_parse_reads_the_filled_lines() -> None:
    text = _draft("correct nothing in the text", "", "wrong inline-tests: #[test] added = yes")
    labels = parse_draft(text, KEYS)
    assert [label.key for label in labels] == [(FIRST, "R1"), (SECOND, "R2")]
    assert [label.verdict for label in labels] == ["correct", "wrong"]
    assert labels[1].reason == "inline-tests: #[test] added = yes"


def test_parse_puts_labels_in_the_order_of_the_results() -> None:
    text = "003 R2 octo/demo#2 = correct later\n001 R1 octo/demo#1 = correct earlier\n"
    assert [label.key for label in parse_draft(text, KEYS)] == [(FIRST, "R1"), (SECOND, "R2")]


def test_parse_tolerates_extra_spaces() -> None:
    labels = parse_draft("  001 R1 octo/demo#1   =   correct   spaced out  \n", KEYS)
    assert labels[0].reason == "spaced out"


@pytest.mark.parametrize(
    "line",
    [
        "001 R1 octo/demo#1 correct no separator",
        "002 R1 octo/demo#1 = correct number of another signal",
        "004 R2 octo/demo#2 = correct number past the end",
        "1 R1 octo/demo#1 = correct number without padding",
    ],
)
def test_parse_refuses_a_line_that_is_not_of_this_draft(line: str) -> None:
    with pytest.raises(DraftError, match="draft line 1"):
        parse_draft(f"{line}\n", KEYS)


@pytest.mark.parametrize("answer", ["maybe not sure", "correct", "wrong"])
def test_parse_refuses_a_bad_answer(answer: str) -> None:
    with pytest.raises(DraftError, match="draft line 5"):
        parse_draft(_draft(answer, "", ""), KEYS)


def test_main_writes_the_labels_and_reports_progress(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _paths(tmp_path, _draft("correct nothing in the text", "wrong tests-dir: x", ""))
    assert main(**paths) == 0
    labels = load_labels(paths["labels_path"])
    assert labels.pandagate_commit == COMMIT
    assert [label.key for label in labels.labels] == [(FIRST, "R1"), (FIRST, "R2")]
    assert "2 of 3 labelled, 1 wrong, 1 left" in capsys.readouterr().out


def test_main_lets_a_verdict_change(tmp_path: Path) -> None:
    paths = _paths(tmp_path, _draft("correct nothing in the text", "", ""))
    assert main(**paths) == 0
    paths["draft_path"].write_text(_draft("wrong sidebar-link: x", "", ""), encoding="utf-8")
    assert main(**paths) == 0
    assert load_labels(paths["labels_path"]).labels[0].verdict == "wrong"


def test_main_refuses_to_drop_a_label(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = _paths(tmp_path, _draft("correct nothing in the text", "correct no tests", ""))
    assert main(**paths) == 0
    before = paths["labels_path"].read_text(encoding="utf-8")
    paths["draft_path"].write_text(_draft("correct nothing in the text", "", ""), encoding="utf-8")
    assert main(**paths) == 1
    assert "drop 1 label(s)" in capsys.readouterr().err
    assert paths["labels_path"].read_text(encoding="utf-8") == before


def test_main_refuses_a_signal_answered_twice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    line = "001 R1 octo/demo#1 = correct nothing in the text\n"
    paths = _paths(tmp_path, line + line)
    assert main(**paths) == 1
    assert "more than once" in capsys.readouterr().err
    assert not paths["labels_path"].exists()


def test_main_fails_without_a_draft(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = _paths(tmp_path, None)
    assert main(**paths) == 1
    assert capsys.readouterr().err.startswith("apply_draft: ")


def test_main_reports_the_line_of_a_bad_answer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _paths(tmp_path, _draft("", "unsure about this one", ""))
    assert main(**paths) == 1
    assert "draft line 6" in capsys.readouterr().err
    assert not paths["labels_path"].exists()
