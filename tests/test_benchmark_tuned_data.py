"""Gates for the published data of the second benchmark run."""

import json
from collections import Counter
from pathlib import Path
from typing import Any

from benchmarks.carry_over import TUNED_LABELS_PATH, TUNED_RESULTS_PATH, carry_over
from benchmarks.labels import LABELS_PATH, check_against, dump_labels, load_labels, unlabelled
from benchmarks.run_benchmark import RESULTS_PATH


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _urls(results: dict[str, Any]) -> list[str]:
    return [pull["url"] for pull in results["pull_requests"]]


def test_the_second_run_scored_the_same_pull_requests() -> None:
    base, tuned = _load(RESULTS_PATH), _load(TUNED_RESULTS_PATH)
    assert _urls(tuned) == _urls(base)
    assert tuned["sample_taken_at"] == base["sample_taken_at"]
    assert tuned["pandagate_commit"] != base["pandagate_commit"]


def test_every_absent_signal_of_the_second_run_is_labelled() -> None:
    labels, results = load_labels(TUNED_LABELS_PATH), _load(TUNED_RESULTS_PATH)
    check_against(labels, results)
    assert unlabelled(labels, results) == []


def test_the_labels_of_the_second_run_are_the_carried_baseline_labels() -> None:
    labels, pending = carry_over(
        load_labels(LABELS_PATH), _load(RESULTS_PATH), _load(TUNED_RESULTS_PATH)
    )
    assert pending == []
    assert dump_labels(labels) == TUNED_LABELS_PATH.read_text(encoding="utf-8")


def test_metric_c_of_the_second_run() -> None:
    labels = load_labels(TUNED_LABELS_PATH).labels
    assert dict(Counter(label.rule_id for label in labels)) == {"R1": 70, "R2": 31}
    assert [label.key for label in labels if label.verdict == "wrong"] == []
