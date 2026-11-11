"""Published results: metric C, the rendered file, the criterion."""

import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.labels import LABELS_PATH, Label, LabelError, Labels, dump_labels
from benchmarks.report import CRITERION, error_summary, main, render

COMMIT = "796b735c3b387874fe8e40ec7da0f1f17cc77003"
FIRST = "https://github.com/octo/demo/pull/1"
SECOND = "https://github.com/octo/demo/pull/2"


def _signal(rule_id: str, outcome: str) -> dict[str, str]:
    return {"rule_id": rule_id, "outcome": outcome, "detail": "observed"}


def _counts(present: int, absent: int, not_applicable: int) -> dict[str, Any]:
    return {"present": present, "absent": absent, "not_applicable": not_applicable, "unknown": 0}


def _results() -> dict[str, Any]:
    return {
        "pandagate_commit": COMMIT,
        "sample_taken_at": "2026-11-11T08:39:04Z",
        "run_at": "2026-11-11T08:48:18Z",
        "summary": {
            "pull_requests": 2,
            "commented": 2,
            "rules": {"R1": _counts(1, 1, 0), "R2": _counts(0, 2, 0), "R3": _counts(1, 0, 1)},
        },
        "pull_requests": [
            {
                "repository": "octo/demo",
                "url": FIRST,
                "signals": [
                    _signal("R1", "ABSENT"),
                    _signal("R2", "ABSENT"),
                    _signal("R3", "PRESENT"),
                ],
            },
            {
                "repository": "octo/demo",
                "url": SECOND,
                "signals": [
                    _signal("R1", "PRESENT"),
                    _signal("R2", "ABSENT"),
                    _signal("R3", "NOT_APPLICABLE"),
                ],
            },
        ],
    }


def _labels(first: str, second: str, third: str, commit: str = COMMIT) -> Labels:
    reasons = {"correct": "nothing found", "wrong": "tests-dir: a | b"}
    return Labels(
        commit,
        (
            Label(FIRST, "R1", first, reasons[first]),
            Label(FIRST, "R2", second, reasons[second]),
            Label(SECOND, "R2", third, "plain reason"),
        ),
    )


def test_criterion_is_the_one_of_the_protocol() -> None:
    protocol = LABELS_PATH.with_name("README.md").read_text(encoding="utf-8")
    assert f"C is at most {CRITERION:.0%}." in protocol


def test_error_summary_counts_wrong_signals_per_rule() -> None:
    errors = error_summary(_results(), _labels("correct", "wrong", "wrong"))
    assert (errors["wrong"], errors["absent"]) == (2, 3)
    assert errors["error_rate"] == pytest.approx(2 / 3)
    assert errors["rules"] == {
        "R1": {"absent": 1, "wrong": 0},
        "R2": {"absent": 2, "wrong": 2},
    }


def test_error_summary_refuses_incomplete_labels() -> None:
    labels = Labels(COMMIT, (Label(FIRST, "R1", "correct", "nothing found"),))
    with pytest.raises(LabelError, match="2 ABSENT signal.s. are not labelled"):
        error_summary(_results(), labels)


def test_error_summary_refuses_labels_of_another_run() -> None:
    with pytest.raises(LabelError, match="commit"):
        error_summary(_results(), _labels("correct", "wrong", "wrong", commit="0" * 40))


def test_render_states_every_metric() -> None:
    lines = render(_results(), _labels("correct", "wrong", "wrong")).splitlines()
    assert lines[0] == "# Benchmark results"
    assert f"- PandaGate commit: `{COMMIT}`" in lines
    assert "2 of 2 pull requests (100.0%) would have received a comment." in lines
    assert "| R1 | 1 | 1 | 50.0% | 0 | 0 |" in lines
    assert "| R3 | 0 | 1 | 0.0% | 1 | 0 |" in lines
    assert "2 of 3 `ABSENT` signals are wrong (66.7%)." in lines
    assert "The criterion is at most 5%: **not met**." in lines
    assert "| R1 | 1 | 0 | 0.0% |" in lines
    assert "| R2 | 2 | 2 | 100.0% |" in lines
    assert "| R3 | 0 | 0 | n/a |" in lines
    assert "| octo/demo | 2 | 3 | 2 |" in lines
    assert "| other | 1 |" in lines
    assert "| tests-dir | 1 |" in lines
    assert f"| [octo/demo#1]({FIRST}) | R2 | tests-dir: a \\| b |" in lines
    assert f"| [octo/demo#2]({SECOND}) | R2 | plain reason |" in lines


def test_render_says_when_the_criterion_is_met() -> None:
    text = render(_results(), _labels("correct", "correct", "correct"))
    assert "0 of 3 `ABSENT` signals are wrong (0.0%)." in text
    assert "The criterion is at most 5%: **met**." in text
    assert text.endswith("No `ABSENT` signal was labelled wrong.\n")


def _paths(tmp_path: Path, labels: Labels) -> dict[str, Path]:
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(_results()), encoding="utf-8")
    labels_path = tmp_path / "labels.json"
    labels_path.write_text(dump_labels(labels), encoding="utf-8")
    return {
        "results_path": results_path,
        "labels_path": labels_path,
        "report_path": tmp_path / "RESULTS.md",
    }


def test_main_writes_the_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    labels = _labels("correct", "wrong", "wrong")
    paths = _paths(tmp_path, labels)
    assert main(**paths) == 0
    assert paths["report_path"].read_text(encoding="utf-8") == render(_results(), labels)
    assert "C = 2/3 (66.7%)" in capsys.readouterr().out


def test_main_writes_nothing_for_incomplete_labels(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _paths(tmp_path, Labels(COMMIT, (Label(FIRST, "R1", "correct", "nothing found"),)))
    assert main(**paths) == 1
    assert "not labelled" in capsys.readouterr().err
    assert not paths["report_path"].exists()
