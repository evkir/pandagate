"""Carry the hand labels of one run over to a later run of the same sample.

Run from the repository root:

    python -m benchmarks.carry_over

Without arguments the labels of the baseline go to the second run. A later
run takes its labels from the run before it, and all four files are named
with --base-results, --base-labels, --results and --output.

A signal that is ABSENT in both runs with the same detail is the same
observation about the same pull request, so its label still stands. An
ABSENT signal that is new, or whose detail changed, has no label yet: it
is listed and has to be checked by hand. Labels of signals that are no
longer ABSENT are left behind.
"""

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.labels import (
    LABELS_PATH,
    Key,
    Labels,
    absent_keys,
    check_against,
    dump_labels,
    load_labels,
)
from benchmarks.run_benchmark import RESULTS_PATH

TUNED_RESULTS_PATH = RESULTS_PATH.with_name("results-tuned.json")
TUNED_LABELS_PATH = LABELS_PATH.with_name("labels-tuned.json")


def _absent_details(results: Mapping[str, Any]) -> dict[Key, str]:
    return {
        (str(pull["url"]), str(signal["rule_id"])): str(signal["detail"])
        for pull in results["pull_requests"]
        for signal in pull["signals"]
        if signal["outcome"] == "ABSENT"
    }


def carry_over(
    base_labels: Labels, base_results: Mapping[str, Any], later_results: Mapping[str, Any]
) -> tuple[Labels, list[Key]]:
    """Labels for the later run, and its ABSENT signals that still need one."""
    check_against(base_labels, base_results)
    before = _absent_details(base_results)
    after = _absent_details(later_results)
    by_key = {label.key: label for label in base_labels.labels}
    carried = []
    pending: list[Key] = []
    for key in absent_keys(later_results):
        label = by_key.get(key)
        if label is not None and before.get(key) == after[key]:
            carried.append(label)
        else:
            pending.append(key)
    return Labels(str(later_results["pandagate_commit"]), tuple(carried)), pending


def main(
    *,
    base_results_path: Path = RESULTS_PATH,
    base_labels_path: Path = LABELS_PATH,
    later_results_path: Path = TUNED_RESULTS_PATH,
    later_labels_path: Path = TUNED_LABELS_PATH,
) -> int:
    if later_labels_path.exists():
        print(f"error: {later_labels_path} already exists; it is not overwritten", file=sys.stderr)
        return 1
    try:
        base_results = json.loads(base_results_path.read_text(encoding="utf-8"))
        later_results = json.loads(later_results_path.read_text(encoding="utf-8"))
        labels, pending = carry_over(load_labels(base_labels_path), base_results, later_results)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    later_labels_path.write_text(dump_labels(labels), encoding="utf-8")
    print(f"carried over {len(labels.labels)} label(s), {len(pending)} signal(s) need a hand label")
    for url, rule_id in pending:
        print(f"  {rule_id} {url}")
    return 0


def cli(argv: Sequence[str] | None = None, *, run: Callable[..., int] = main) -> int:
    """Parse the command line: which run hands its labels to which."""
    parser = argparse.ArgumentParser(
        prog="python -m benchmarks.carry_over",
        description="Carry hand labels over to a later run of the same sample.",
    )
    parser.add_argument(
        "--base-results",
        type=Path,
        default=RESULTS_PATH,
        help="outcomes of the run that is already labelled",
    )
    parser.add_argument("--base-labels", type=Path, default=LABELS_PATH, help="labels of that run")
    parser.add_argument(
        "--results", type=Path, default=TUNED_RESULTS_PATH, help="outcomes of the later run"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=TUNED_LABELS_PATH,
        help="file to write the labels of the later run to; it must not exist yet",
    )
    arguments = parser.parse_args(argv)
    return run(
        base_results_path=arguments.base_results,
        base_labels_path=arguments.base_labels,
        later_results_path=arguments.results,
        later_labels_path=arguments.output,
    )


if __name__ == "__main__":
    sys.exit(cli())
