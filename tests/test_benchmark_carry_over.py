"""Tests for carrying baseline labels over to a later run."""

import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.carry_over import TUNED_LABELS_PATH, TUNED_RESULTS_PATH, carry_over, cli, main
from benchmarks.labels import LABELS_PATH, Label, LabelError, Labels, dump_labels, load_labels
from benchmarks.run_benchmark import RESULTS_PATH

FIRST = "https://github.com/octo/demo/pull/1"
SECOND = "https://github.com/octo/demo/pull/2"
ASKED = ("ABSENT", "no issue reference in the title or body")
UNTESTED = ("ABSENT", "1 logic file(s) changed, 9 line(s), no test file changed")
TESTED = ("PRESENT", "1 test file(s) changed alongside 1 logic file(s)")


def _run(commit: str, outcomes: dict[tuple[str, str], tuple[str, str]]) -> dict[str, Any]:
    pulls: dict[str, list[dict[str, str]]] = {}
    for (url, rule_id), (outcome, detail) in outcomes.items():
        pulls.setdefault(url, []).append({"rule_id": rule_id, "outcome": outcome, "detail": detail})
    return {
        "pandagate_commit": commit,
        "pull_requests": [{"url": url, "signals": signals} for url, signals in pulls.items()],
    }


BASE = _run("aaa", {(FIRST, "R1"): ASKED, (FIRST, "R2"): UNTESTED, (SECOND, "R1"): ASKED})
BASE_LABELS = Labels(
    "aaa",
    (
        Label(FIRST, "R1", "correct", "no reference anywhere"),
        Label(FIRST, "R2", "wrong", "tests-dir: testing/ holds the tests"),
        Label(SECOND, "R1", "correct", "no reference anywhere"),
    ),
)


def _keys(labels: Labels) -> list[tuple[str, str]]:
    return [label.key for label in labels.labels]


def test_a_signal_absent_in_both_runs_keeps_its_label() -> None:
    later = _run("bbb", {(FIRST, "R1"): ASKED, (SECOND, "R1"): ASKED})
    labels, pending = carry_over(BASE_LABELS, BASE, later)
    assert labels.pandagate_commit == "bbb"
    assert _keys(labels) == [(FIRST, "R1"), (SECOND, "R1")]
    assert pending == []


def test_a_signal_that_is_no_longer_absent_leaves_its_label_behind() -> None:
    later = _run("bbb", {(FIRST, "R1"): ASKED, (FIRST, "R2"): TESTED, (SECOND, "R1"): ASKED})
    labels, pending = carry_over(BASE_LABELS, BASE, later)
    assert _keys(labels) == [(FIRST, "R1"), (SECOND, "R1")]
    assert pending == []


def test_a_new_absent_signal_waits_for_a_hand_label() -> None:
    later = _run("bbb", {(FIRST, "R1"): ASKED, (SECOND, "R1"): ASKED, (SECOND, "R2"): UNTESTED})
    labels, pending = carry_over(BASE_LABELS, BASE, later)
    assert _keys(labels) == [(FIRST, "R1"), (SECOND, "R1")]
    assert pending == [(SECOND, "R2")]


def test_a_changed_detail_waits_for_a_hand_label() -> None:
    changed = ("ABSENT", "no closing keyword and issue reference in the title or body")
    later = _run("bbb", {(FIRST, "R1"): changed, (SECOND, "R1"): ASKED})
    labels, pending = carry_over(BASE_LABELS, BASE, later)
    assert _keys(labels) == [(SECOND, "R1")]
    assert pending == [(FIRST, "R1")]


def test_labels_of_another_run_are_refused() -> None:
    with pytest.raises(LabelError):
        carry_over(Labels("zzz", BASE_LABELS.labels), BASE, BASE)


def _write(tmp_path: Path, later: dict[str, Any]) -> dict[str, Path]:
    paths = {
        "base_results_path": tmp_path / "results.json",
        "base_labels_path": tmp_path / "labels.json",
        "later_results_path": tmp_path / "results-tuned.json",
        "later_labels_path": tmp_path / "labels-tuned.json",
    }
    paths["base_results_path"].write_text(json.dumps(BASE), encoding="utf-8")
    paths["base_labels_path"].write_text(dump_labels(BASE_LABELS), encoding="utf-8")
    paths["later_results_path"].write_text(json.dumps(later), encoding="utf-8")
    return paths


def test_main_writes_the_labels_of_the_later_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _write(tmp_path, _run("bbb", {(FIRST, "R1"): ASKED, (SECOND, "R2"): UNTESTED}))
    assert main(**paths) == 0
    written = load_labels(paths["later_labels_path"])
    assert written.pandagate_commit == "bbb"
    assert _keys(written) == [(FIRST, "R1")]
    out = capsys.readouterr().out
    assert "carried over 1 label(s), 1 signal(s) need a hand label" in out
    assert f"R2 {SECOND}" in out


def test_main_never_writes_over_existing_labels(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _write(tmp_path, BASE)
    paths["later_labels_path"].write_text("kept", encoding="utf-8")
    assert main(**paths) == 1
    assert paths["later_labels_path"].read_text(encoding="utf-8") == "kept"
    assert "already exists" in capsys.readouterr().err


def test_main_fails_without_the_later_results(tmp_path: Path) -> None:
    paths = _write(tmp_path, BASE)
    paths["later_results_path"].unlink()
    assert main(**paths) == 1
    assert not paths["later_labels_path"].exists()


def test_cli_without_arguments_carries_the_baseline_to_the_second_run() -> None:
    seen: dict[str, Path] = {}

    def run(**paths: Path) -> int:
        seen.update(paths)
        return 0

    assert cli([], run=run) == 0
    assert seen == {
        "base_results_path": RESULTS_PATH,
        "base_labels_path": LABELS_PATH,
        "later_results_path": TUNED_RESULTS_PATH,
        "later_labels_path": TUNED_LABELS_PATH,
    }


def test_cli_takes_every_file_from_the_command_line(tmp_path: Path) -> None:
    paths = _write(tmp_path, _run("bbb", {(FIRST, "R1"): ASKED}))
    target = tmp_path / "labels-third.json"
    argv = [
        "--base-results",
        str(paths["base_results_path"]),
        "--base-labels",
        str(paths["base_labels_path"]),
        "--results",
        str(paths["later_results_path"]),
        "--output",
        str(target),
    ]
    assert cli(argv) == 0
    written = load_labels(target)
    assert written.pandagate_commit == "bbb"
    assert _keys(written) == [(FIRST, "R1")]
    assert not paths["later_labels_path"].exists()


def test_cli_passes_the_exit_code_of_the_run_through() -> None:
    assert cli([], run=lambda **paths: 1) == 1
