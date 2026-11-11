"""Metrics A and B of the protocol, computed from the outcomes of a run.

A pull request is a mapping with "repository" and "signals"; a signal is a
mapping with "rule_id" and "outcome", the outcome being the name of the member.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

PRESENT = "PRESENT"
ABSENT = "ABSENT"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNKNOWN = "UNKNOWN"


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _commented(pull: Mapping[str, Any]) -> bool:
    return any(signal["outcome"] == ABSENT for signal in pull["signals"])


def summarise(pulls: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Comment rate, per-rule counts and a breakdown by repository."""
    commented = sum(1 for pull in pulls if _commented(pull))

    counts: dict[str, Counter[str]] = {}
    for pull in pulls:
        for signal in pull["signals"]:
            counts.setdefault(signal["rule_id"], Counter())[signal["outcome"]] += 1
    rules = {
        rule_id: {
            "present": counts[rule_id][PRESENT],
            "absent": counts[rule_id][ABSENT],
            "not_applicable": counts[rule_id][NOT_APPLICABLE],
            "unknown": counts[rule_id][UNKNOWN],
            "absent_rate": _rate(
                counts[rule_id][ABSENT], counts[rule_id][PRESENT] + counts[rule_id][ABSENT]
            ),
        }
        for rule_id in sorted(counts)
    }

    by_repository: dict[str, dict[str, int]] = {}
    for pull in pulls:
        row = by_repository.setdefault(pull["repository"], {"pull_requests": 0, "commented": 0})
        row["pull_requests"] += 1
        row["commented"] += int(_commented(pull))

    return {
        "pull_requests": len(pulls),
        "commented": commented,
        "comment_rate": _rate(commented, len(pulls)),
        "rules": rules,
        "by_repository": by_repository,
    }


def _percent(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate:.1%}"


def format_summary(summary: Mapping[str, Any]) -> str:
    """The summary as plain text for the terminal."""
    total = summary["pull_requests"]
    rate = _percent(summary["comment_rate"])
    lines = [f"A. comment rate: {summary['commented']}/{total} ({rate})", "B. per rule:"]
    for rule_id, row in summary["rules"].items():
        lines.append(
            f"  {rule_id}: absent {row['absent']}, present {row['present']}, "
            f"not applicable {row['not_applicable']}, unknown {row['unknown']}, "
            f"absent rate {_percent(row['absent_rate'])}"
        )
    lines.append("By repository:")
    for name, row in summary["by_repository"].items():
        lines.append(f"  {name}: {row['commented']}/{row['pull_requests']}")
    return "\n".join(lines)
