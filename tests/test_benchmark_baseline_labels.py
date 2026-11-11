"""The committed labels of the baseline run."""

import json
from typing import Any

from benchmarks.labels import LABELS_PATH, check_against, load_labels


def _results() -> dict[str, Any]:
    return json.loads(LABELS_PATH.with_name("results.json").read_text(encoding="utf-8"))


def test_committed_labels_belong_to_the_baseline_run() -> None:
    check_against(load_labels(), _results())
