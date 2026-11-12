"""Gates for the second-run section of the published results."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.carry_over import TUNED_LABELS_PATH, TUNED_RESULTS_PATH
from benchmarks.labels import LABELS_PATH, LabelError, load_labels
from benchmarks.report import (
    REPORT_PATH,
    RERUN_LABELS_PATH,
    RERUN_RESULTS_PATH,
    RESULTS_PATH,
    error_summary,
    main,
    render,
    render_rerun,
)

BASELINE_SHA256 = "797558dc1f2509153efa8d28d37be3a82ec459f3baa0becb0900bacce6a14a79"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _baseline() -> str:
    return render(_load(RESULTS_PATH), load_labels(LABELS_PATH))


def _section() -> str:
    return render_rerun(
        _load(RESULTS_PATH),
        load_labels(LABELS_PATH),
        _load(RERUN_RESULTS_PATH),
        load_labels(RERUN_LABELS_PATH),
    )


def test_the_report_reads_the_files_the_carry_over_writes() -> None:
    assert (RERUN_RESULTS_PATH, RERUN_LABELS_PATH) == (TUNED_RESULTS_PATH, TUNED_LABELS_PATH)


def test_the_baseline_part_is_the_text_first_published() -> None:
    assert hashlib.sha256(_baseline().encode("utf-8")).hexdigest() == BASELINE_SHA256


def test_the_published_report_is_the_baseline_and_then_the_second_run() -> None:
    published = REPORT_PATH.read_text(encoding="utf-8")
    assert published.startswith(_baseline() + "\n" + _section())


def test_metric_c_of_the_second_run_is_pinned() -> None:
    errors = error_summary(_load(RERUN_RESULTS_PATH), load_labels(RERUN_LABELS_PATH))
    assert (errors["wrong"], errors["absent"]) == (0, 101)
    assert errors["rules"] == {
        "R1": {"absent": 70, "wrong": 0},
        "R2": {"absent": 31, "wrong": 0},
    }


def test_the_section_says_what_changed_and_that_the_rules_were_tuned() -> None:
    section = _section()
    row = (
        "| [vitejs/vite#23513](https://github.com/vitejs/vite/pull/23513) "
        "| R1 | `ABSENT` | `PRESENT` | correct |"
    )
    for expected in (
        "## Second run, on the sample the rules were tuned on",
        "**The rules were tuned on this sample.**",
        "for this run: 0.",
        "- Comment rate: 90 of 200 (45.0%), baseline 100 of 200 (50.0%).",
        "- Labelled wrong in the baseline and no longer `ABSENT`: 17 of 17.",
        "- Labelled correct in the baseline and no longer `ABSENT`: 1. Such a question",
        "- `ABSENT` only in this run: 0.",
        "0 of 101 `ABSENT` signals are wrong (0.0%).",
        row,
    ):
        assert expected in section


def test_a_run_of_another_sample_is_refused() -> None:
    other = _load(RERUN_RESULTS_PATH)
    other["pull_requests"] = other["pull_requests"][1:]
    with pytest.raises(LabelError):
        render_rerun(
            _load(RESULTS_PATH), load_labels(LABELS_PATH), other, load_labels(RERUN_LABELS_PATH)
        )


def test_main_writes_both_parts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "RESULTS.md"
    code = main(
        report_path=target,
        rerun_results_path=RERUN_RESULTS_PATH,
        rerun_labels_path=RERUN_LABELS_PATH,
    )
    assert code == 0
    assert target.read_text(encoding="utf-8") == _baseline() + "\n" + _section()
    assert "report: second run C = 0/101 (0.0%)" in capsys.readouterr().out


def test_main_without_a_second_run_writes_the_baseline_alone(tmp_path: Path) -> None:
    target = tmp_path / "RESULTS.md"
    assert main(report_path=target) == 0
    assert target.read_text(encoding="utf-8") == _baseline()
