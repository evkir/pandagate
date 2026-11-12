"""The committed labels and published results of the baseline run."""

import json
from typing import Any

from benchmarks.labels import LABELS_PATH, check_against, load_labels, unlabelled
from benchmarks.report import REPORT_PATH, error_summary, render


def _results() -> dict[str, Any]:
    return json.loads(LABELS_PATH.with_name("results.json").read_text(encoding="utf-8"))


def test_committed_labels_belong_to_the_baseline_run() -> None:
    check_against(load_labels(), _results())


def test_every_absent_signal_of_the_baseline_is_labelled() -> None:
    assert unlabelled(load_labels(), _results()) == []


def test_baseline_error_rate_is_the_published_one() -> None:
    errors = error_summary(_results(), load_labels())
    assert (errors["wrong"], errors["absent"]) == (17, 119)
    assert errors["rules"] == {
        "R1": {"absent": 76, "wrong": 5},
        "R2": {"absent": 43, "wrong": 12},
    }


def test_published_results_are_generated_from_the_data() -> None:
    assert REPORT_PATH.read_text(encoding="utf-8").startswith(render(_results(), load_labels()))
