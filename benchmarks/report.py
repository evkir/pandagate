"""The published results of a benchmark run: metrics A, B and C in one file.

RESULTS.md is generated and never edited by hand: the baseline part from
results.json and labels.json, and after it one section per later run. The
second run is read from results-tuned.json and labels-tuned.json, the
third from results-defaults.json and labels-defaults.json. Adding a run
does not change a byte of what was published before it. Metric C is
computed only when every ABSENT signal of a run is labelled.
"""

import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.labels import (
    LABELS_PATH,
    Key,
    LabelError,
    Labels,
    check_against,
    load_labels,
    unlabelled,
)
from pandagate.github import parse_pull_request_url

RESULTS_PATH = LABELS_PATH.with_name("results.json")
REPORT_PATH = LABELS_PATH.with_name("RESULTS.md")
RERUN_RESULTS_PATH = LABELS_PATH.with_name("results-tuned.json")
RERUN_LABELS_PATH = LABELS_PATH.with_name("labels-tuned.json")
DEFAULTS_RESULTS_PATH = LABELS_PATH.with_name("results-defaults.json")
DEFAULTS_LABELS_PATH = LABELS_PATH.with_name("labels-defaults.json")
CRITERION = 0.05


def error_summary(results: Mapping[str, Any], labels: Labels) -> dict[str, Any]:
    """Metric C: wrong ABSENT signals over all ABSENT signals, in total and per rule."""
    check_against(labels, results)
    left = unlabelled(labels, results)
    if left:
        raise LabelError(
            f"{len(left)} ABSENT signal(s) are not labelled, the first is {left[0][0]} {left[0][1]}"
        )
    rules: dict[str, dict[str, int]] = {}
    for label in labels.labels:
        counts = rules.setdefault(label.rule_id, {"absent": 0, "wrong": 0})
        counts["absent"] += 1
        counts["wrong"] += label.verdict == "wrong"
    absent = len(labels.labels)
    wrong = sum(counts["wrong"] for counts in rules.values())
    return {
        "absent": absent,
        "wrong": wrong,
        "error_rate": wrong / absent if absent else None,
        "rules": dict(sorted(rules.items())),
    }


def _percent(part: int, whole: int) -> str:
    return f"{part / whole:.1%}" if whole else "n/a"


def _slug(url: str) -> str:
    ref = parse_pull_request_url(url)
    return f"{ref.slug}#{ref.number}"


def _cause(reason: str) -> str:
    head, separator, _ = reason.partition(":")
    return head if separator and " " not in head else "other"


def _table(header: Sequence[str], rows: Iterable[Sequence[object]]) -> list[str]:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    return lines


def _metrics(results: Mapping[str, Any], labels: Labels) -> list[str]:
    """Sections A, B and C with their tables for one labelled run."""
    errors = error_summary(results, labels)
    summary = results["summary"]
    total, commented = int(summary["pull_requests"]), int(summary["commented"])
    absent, wrong = errors["absent"], errors["wrong"]
    share = _percent(commented, total)
    met = wrong <= CRITERION * absent
    verdicts = {label.key: label.verdict for label in labels.labels}
    mistakes = [label for label in labels.labels if label.verdict == "wrong"]

    rule_rows = []
    error_rows = []
    for rule_id, counts in summary["rules"].items():
        present, missing = int(counts["present"]), int(counts["absent"])
        rate = _percent(missing, present + missing)
        rule_rows.append(
            [rule_id, missing, present, rate, counts["not_applicable"], counts["unknown"]]
        )
        checked = errors["rules"].get(rule_id, {"absent": 0, "wrong": 0})
        error_rows.append(
            [
                rule_id,
                checked["absent"],
                checked["wrong"],
                _percent(checked["wrong"], checked["absent"]),
            ]
        )

    repositories: dict[str, list[int]] = {}
    for pull in results["pull_requests"]:
        row = repositories.setdefault(str(pull["repository"]), [0, 0, 0])
        keys = [
            (str(pull["url"]), str(signal["rule_id"]))
            for signal in pull["signals"]
            if signal["outcome"] == "ABSENT"
        ]
        row[0] += bool(keys)
        row[1] += len(keys)
        row[2] += sum(verdicts[key] == "wrong" for key in keys)

    causes = Counter(_cause(label.reason) for label in mistakes)
    cause_rows = sorted(causes.items(), key=lambda item: (-item[1], item[0]))

    lines = [
        "### A. Comment rate",
        "",
        f"{commented} of {total} pull requests ({share}) would have received a comment.",
        "",
        "### B. Per-rule rate",
        "",
        *_table(
            ["Rule", "`ABSENT`", "`PRESENT`", "Rate", "`NOT_APPLICABLE`", "`UNKNOWN`"], rule_rows
        ),
        "",
        "### C. Factual error rate",
        "",
        f"{wrong} of {absent} `ABSENT` signals are wrong ({_percent(wrong, absent)}).",
        f"The criterion is at most {CRITERION:.0%}: **{'met' if met else 'not met'}**.",
        "",
        *_table(["Rule", "`ABSENT` checked", "Wrong", "Rate"], error_rows),
        "",
        "### By repository",
        "",
        *_table(
            ["Repository", "Pull requests with a comment", "`ABSENT` signals", "Wrong"],
            ([name, *row] for name, row in repositories.items()),
        ),
        "",
        "### Wrong signals",
        "",
    ]
    if mistakes:
        lines.extend(_table(["Cause", "Signals"], cause_rows))
        lines.append("")
        lines.extend(
            _table(
                ["Pull request", "Rule", "Reason"],
                (
                    [
                        f"[{_slug(label.url)}]({label.url})",
                        label.rule_id,
                        label.reason.replace("|", "\\|"),
                    ]
                    for label in mistakes
                ),
            )
        )
    else:
        lines.append("No `ABSENT` signal was labelled wrong.")
    return lines


def _run_facts(results: Mapping[str, Any]) -> list[str]:
    return [
        f"- PandaGate commit: `{results['pandagate_commit']}`",
        f"- Sample taken at: {results['sample_taken_at']}",
        f"- Run at: {results['run_at']}",
        f"- Pull requests: {int(results['summary']['pull_requests'])}",
    ]


def render(results: Mapping[str, Any], labels: Labels) -> str:
    """The baseline part of RESULTS.md."""
    lines = [
        "# Benchmark results",
        "",
        "Generated by `python -m benchmarks.report` from `results.json` and `labels.json`.",
        "The protocol, fixed before the first run, is in [README.md](README.md).",
        "",
        "## Baseline",
        "",
        *_run_facts(results),
        "- This is the first run: no rule was tuned on the sample before it.",
        "",
        *_metrics(results, labels),
    ]
    return "\n".join(lines) + "\n"


def _outcomes(results: Mapping[str, Any]) -> dict[Key, str]:
    return {
        (str(pull["url"]), str(signal["rule_id"])): str(signal["outcome"])
        for pull in results["pull_requests"]
        for signal in pull["signals"]
    }


def render_rerun(
    base_results: Mapping[str, Any],
    base_labels: Labels,
    results: Mapping[str, Any],
    labels: Labels,
) -> str:
    """The section of RESULTS.md for a run of the same sample after rule fixes."""
    before, after = _outcomes(base_results), _outcomes(results)
    if list(before) != list(after):
        raise LabelError("the second run did not score the same signals as the baseline")
    base_by_key = {label.key: label for label in base_labels.labels}
    changed = [key for key in before if before[key] != after[key]]
    left = [base_by_key[key] for key in changed if before[key] == "ABSENT"]
    fixed = sum(label.verdict == "wrong" for label in left)
    base_wrong = sum(label.verdict == "wrong" for label in base_labels.labels)
    appeared = sum(after[key] == "ABSENT" for key in changed)
    by_hand = sum(base_by_key.get(label.key) != label for label in labels.labels)
    summary, base_summary = results["summary"], base_results["summary"]
    total, commented = int(summary["pull_requests"]), int(summary["commented"])
    base_total = int(base_summary["pull_requests"])
    base_commented = int(base_summary["commented"])
    rows = [
        [
            f"[{_slug(key[0])}]({key[0]})",
            key[1],
            f"`{before[key]}`",
            f"`{after[key]}`",
            base_by_key[key].verdict if key in base_by_key else "not labelled",
        ]
        for key in changed
    ]
    lines = [
        "## Second run, on the sample the rules were tuned on",
        "",
        "Generated from `results-tuned.json` and `labels-tuned.json`.",
        "",
        *_run_facts(results),
        "- **The rules were tuned on this sample.** The fixes made between the two runs were",
        "  written from the wrong signals of the baseline above. This run shows that those",
        "  errors are gone. It does not show how the rules do on pull requests they have not",
        "  seen: that takes a fresh sample.",
        "- A label is carried over from the baseline when the signal is `ABSENT` in both runs",
        "  with the same detail (`python -m benchmarks.carry_over`). Signals labelled by hand",
        f"  for this run: {by_hand}.",
        "",
        "### Against the baseline",
        "",
        f"- Comment rate: {commented} of {total} ({_percent(commented, total)}), "
        f"baseline {base_commented} of {base_total} ({_percent(base_commented, base_total)}).",
        f"- Labelled wrong in the baseline and no longer `ABSENT`: {fixed} of {base_wrong}.",
        f"- Labelled correct in the baseline and no longer `ABSENT`: {len(left) - fixed}. "
        "Such a question was right to ask and is not asked any more.",
        f"- `ABSENT` only in this run: {appeared}.",
        "",
        *_table(["Pull request", "Rule", "Baseline", "This run", "Baseline label"], rows),
        "",
        *_metrics(results, labels),
    ]
    return "\n".join(lines) + "\n"


def _details(results: Mapping[str, Any]) -> dict[Key, str]:
    return {
        (str(pull["url"]), str(signal["rule_id"])): str(signal["detail"])
        for pull in results["pull_requests"]
        for signal in pull["signals"]
    }


def _scope_reason(detail: str) -> str:
    if detail == "no logic files changed":
        return detail
    if "below the" in detail:
        return "logic below the threshold"
    return "other"


def render_defaults(
    previous_results: Mapping[str, Any],
    previous_labels: Labels,
    results: Mapping[str, Any],
    labels: Labels,
) -> str:
    """The section of RESULTS.md for the run after the defaults were made quieter."""
    before, after = _outcomes(previous_results), _outcomes(results)
    if list(before) != list(after):
        raise LabelError("the third run did not score the same signals as the second run")
    details = _details(results)
    previous_by_key = {label.key: label for label in previous_labels.labels}
    changed = [key for key in before if before[key] != after[key]]
    silenced = [key for key in changed if before[key] == "ABSENT"]
    wrong = sum(previous_by_key[key].verdict == "wrong" for key in silenced)
    correct = len(silenced) - wrong
    appeared = sum(after[key] == "ABSENT" for key in changed)
    other = len(changed) - len(silenced) - appeared
    by_hand = sum(previous_by_key.get(label.key) != label for label in labels.labels)
    summary, previous_summary = results["summary"], previous_results["summary"]
    total, commented = int(summary["pull_requests"]), int(summary["commented"])
    previous_total = int(previous_summary["pull_requests"])
    previous_commented = int(previous_summary["commented"])
    reasons = Counter(_scope_reason(details[key]) for key in silenced)
    reason_rows = sorted(reasons.items(), key=lambda item: (-item[1], item[0]))
    rows = [
        [
            f"[{_slug(key[0])}]({key[0]})",
            key[1],
            f"`{after[key]}`",
            f"`{details[key]}`",
            previous_by_key[key].verdict,
        ]
        for key in silenced
    ]
    lines = [
        "## Third run, with quieter defaults",
        "",
        "Generated from `results-defaults.json` and `labels-defaults.json`.",
        "",
        *_run_facts(results),
        "- **The default was chosen on this sample.** Between the second run and this one,",
        "  R1 was taken out of scope for pull requests that change fewer than five lines of",
        "  logic. The threshold was picked by looking at where the second run asked its",
        "  questions, so the comment rate below is not a measurement on pull requests the",
        "  rules have not seen: that takes a fresh sample.",
        "- The change lowers the comment rate by asking less. It corrects no wrong signal, and",
        "  every question that is no longer asked is listed below with the label it had.",
        "- A label is carried over from the second run when the signal is `ABSENT` in both",
        "  runs with the same detail (`python -m benchmarks.carry_over`). Signals labelled by",
        f"  hand for this run: {by_hand}.",
        "",
        "### Against the second run",
        "",
        f"- Comment rate: {commented} of {total} ({_percent(commented, total)}), "
        f"second run {previous_commented} of {previous_total} "
        f"({_percent(previous_commented, previous_total)}).",
        f"- Labelled correct in the second run and no longer `ABSENT`: {correct}. "
        "Such a question was right to ask and is not asked any more.",
        f"- Labelled wrong in the second run and no longer `ABSENT`: {wrong}.",
        f"- `ABSENT` only in this run: {appeared}.",
        f"- Changed between outcomes other than `ABSENT`: {other}.",
        "",
        "### Questions no longer asked",
        "",
        *_table(["Why out of scope", "Signals"], reason_rows),
        "",
        *_table(["Pull request", "Rule", "This run", "Detail", "Second-run label"], rows),
        "",
        *_metrics(results, labels),
    ]
    return "\n".join(lines) + "\n"


def main(
    *,
    results_path: Path = RESULTS_PATH,
    labels_path: Path = LABELS_PATH,
    report_path: Path = REPORT_PATH,
    rerun_results_path: Path | None = None,
    rerun_labels_path: Path | None = None,
    defaults_results_path: Path | None = None,
    defaults_labels_path: Path | None = None,
) -> int:
    """Write RESULTS.md, or say why it cannot be written."""
    try:
        results = json.loads(results_path.read_text(encoding="utf-8"))
        labels = load_labels(labels_path)
        text = render(results, labels)
        errors = error_summary(results, labels)
        rerun = None
        third = None
        if defaults_results_path is not None and rerun_results_path is None:
            raise ValueError("the third run is reported after the second, which is not given")
        if rerun_results_path is not None and rerun_labels_path is not None:
            rerun_results = json.loads(rerun_results_path.read_text(encoding="utf-8"))
            rerun_labels = load_labels(rerun_labels_path)
            text += "\n" + render_rerun(results, labels, rerun_results, rerun_labels)
            rerun = error_summary(rerun_results, rerun_labels)
            if defaults_results_path is not None and defaults_labels_path is not None:
                defaults_results = json.loads(defaults_results_path.read_text(encoding="utf-8"))
                defaults_labels = load_labels(defaults_labels_path)
                text += "\n" + render_defaults(
                    rerun_results, rerun_labels, defaults_results, defaults_labels
                )
                third = error_summary(defaults_results, defaults_labels)
    except (OSError, ValueError, KeyError) as error:
        print(f"report: {error}", file=sys.stderr)
        return 1
    report_path.write_text(text, encoding="utf-8")
    rate = _percent(errors["wrong"], errors["absent"])
    print(f"report: C = {errors['wrong']}/{errors['absent']} ({rate}), wrote {report_path}")
    if rerun is not None:
        again = _percent(rerun["wrong"], rerun["absent"])
        print(f"report: second run C = {rerun['wrong']}/{rerun['absent']} ({again})")
    if third is not None:
        last = _percent(third["wrong"], third["absent"])
        print(f"report: third run C = {third['wrong']}/{third['absent']} ({last})")
    return 0


if __name__ == "__main__":
    raise SystemExit(
        main(
            rerun_results_path=RERUN_RESULTS_PATH,
            rerun_labels_path=RERUN_LABELS_PATH,
            defaults_results_path=DEFAULTS_RESULTS_PATH,
            defaults_labels_path=DEFAULTS_LABELS_PATH,
        )
    )
