"""Gates for the third benchmark run: its data and its section of the results."""

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from benchmarks.carry_over import carry_over
from benchmarks.labels import (
    LABELS_PATH,
    LabelError,
    check_against,
    dump_labels,
    load_labels,
    unlabelled,
)
from benchmarks.report import (
    DEFAULTS_LABELS_PATH,
    DEFAULTS_RESULTS_PATH,
    REPORT_PATH,
    RERUN_LABELS_PATH,
    RERUN_RESULTS_PATH,
    RESULTS_PATH,
    error_summary,
    main,
    render,
    render_defaults,
    render_rerun,
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _outcomes(results: dict[str, Any]) -> dict[tuple[str, str], str]:
    return {
        (pull["url"], signal["rule_id"]): signal["outcome"]
        for pull in results["pull_requests"]
        for signal in pull["signals"]
    }


def _section() -> str:
    return render_defaults(
        _load(RERUN_RESULTS_PATH),
        load_labels(RERUN_LABELS_PATH),
        _load(DEFAULTS_RESULTS_PATH),
        load_labels(DEFAULTS_LABELS_PATH),
    )


def _earlier_parts() -> str:
    base_results, base_labels = _load(RESULTS_PATH), load_labels(LABELS_PATH)
    second = render_rerun(
        base_results, base_labels, _load(RERUN_RESULTS_PATH), load_labels(RERUN_LABELS_PATH)
    )
    return render(base_results, base_labels) + "\n" + second


def test_the_third_run_scored_the_same_pull_requests() -> None:
    second, third = _load(RERUN_RESULTS_PATH), _load(DEFAULTS_RESULTS_PATH)
    assert list(_outcomes(third)) == list(_outcomes(second))
    assert third["sample_taken_at"] == second["sample_taken_at"]
    assert third["pandagate_commit"] != second["pandagate_commit"]


def test_every_absent_signal_of_the_third_run_is_labelled() -> None:
    labels, results = load_labels(DEFAULTS_LABELS_PATH), _load(DEFAULTS_RESULTS_PATH)
    check_against(labels, results)
    assert unlabelled(labels, results) == []


def test_the_labels_of_the_third_run_are_the_carried_second_run_labels() -> None:
    labels, pending = carry_over(
        load_labels(RERUN_LABELS_PATH), _load(RERUN_RESULTS_PATH), _load(DEFAULTS_RESULTS_PATH)
    )
    assert pending == []
    assert dump_labels(labels) == DEFAULTS_LABELS_PATH.read_text(encoding="utf-8")


def test_metric_a_of_the_third_run_is_pinned() -> None:
    summary = _load(DEFAULTS_RESULTS_PATH)["summary"]
    assert (summary["commented"], summary["pull_requests"]) == (50, 200)


def test_metric_c_of_the_third_run_is_pinned() -> None:
    errors = error_summary(_load(DEFAULTS_RESULTS_PATH), load_labels(DEFAULTS_LABELS_PATH))
    assert (errors["wrong"], errors["absent"]) == (0, 61)
    assert errors["rules"] == {
        "R1": {"absent": 30, "wrong": 0},
        "R2": {"absent": 31, "wrong": 0},
    }


def test_only_r1_changed_and_only_by_going_out_of_scope() -> None:
    before = _outcomes(_load(RERUN_RESULTS_PATH))
    after = _outcomes(_load(DEFAULTS_RESULTS_PATH))
    changed = [key for key in before if before[key] != after[key]]
    assert {rule_id for _, rule_id in changed} == {"R1"}
    assert {after[key] for key in changed} == {"NOT_APPLICABLE"}
    assert Counter(before[key] for key in changed)["ABSENT"] == 40


def test_the_published_report_is_the_three_parts_in_order() -> None:
    assert REPORT_PATH.read_text(encoding="utf-8") == _earlier_parts() + "\n" + _section()


def test_the_section_says_the_default_was_chosen_on_this_sample() -> None:
    section = _section()
    for expected in (
        "## Third run, with quieter defaults",
        "**The default was chosen on this sample.**",
        "It corrects no wrong signal",
        "hand for this run: 0.",
        "- Comment rate: 50 of 200 (25.0%), second run 90 of 200 (45.0%).",
        "- Labelled correct in the second run and no longer `ABSENT`: 40. Such a question",
        "- Labelled wrong in the second run and no longer `ABSENT`: 0.",
        "- `ABSENT` only in this run: 0.",
        "| no logic files changed | 20 |",
        "| logic below the threshold | 20 |",
        "0 of 61 `ABSENT` signals are wrong (0.0%).",
    ):
        assert expected in section


def test_a_third_run_of_another_sample_is_refused() -> None:
    other = _load(DEFAULTS_RESULTS_PATH)
    other["pull_requests"] = other["pull_requests"][1:]
    with pytest.raises(LabelError):
        render_defaults(
            _load(RERUN_RESULTS_PATH),
            load_labels(RERUN_LABELS_PATH),
            other,
            load_labels(DEFAULTS_LABELS_PATH),
        )


def test_main_writes_all_three_parts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "RESULTS.md"
    code = main(
        report_path=target,
        rerun_results_path=RERUN_RESULTS_PATH,
        rerun_labels_path=RERUN_LABELS_PATH,
        defaults_results_path=DEFAULTS_RESULTS_PATH,
        defaults_labels_path=DEFAULTS_LABELS_PATH,
    )
    assert code == 0
    assert target.read_text(encoding="utf-8") == REPORT_PATH.read_text(encoding="utf-8")
    assert "report: third run C = 0/61 (0.0%)" in capsys.readouterr().out


def test_main_refuses_a_third_run_without_the_second(tmp_path: Path) -> None:
    target = tmp_path / "RESULTS.md"
    code = main(
        report_path=target,
        defaults_results_path=DEFAULTS_RESULTS_PATH,
        defaults_labels_path=DEFAULTS_LABELS_PATH,
    )
    assert code == 1
    assert not target.exists()
