"""Hand labels for the ABSENT signals of a benchmark run.

Metric C of the protocol in README.md: every ABSENT signal is checked by hand
against the pull request page and labelled correct or wrong with a one-line
reason. This module reads and writes those labels and ties them to a run.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LABELS_PATH = Path(__file__).with_name("labels.json")
VERDICTS = ("correct", "wrong")
MAX_REASON_CHARS = 200

Key = tuple[str, str]

_TOP_FIELDS = frozenset({"pandagate_commit", "labels"})
_LABEL_FIELDS = frozenset({"url", "rule_id", "verdict", "reason"})


class LabelError(ValueError):
    """The labels do not say what the protocol needs them to say."""


@dataclass(frozen=True)
class Label:
    """One hand-checked ABSENT signal."""

    url: str
    rule_id: str
    verdict: str
    reason: str

    def __post_init__(self) -> None:
        if not self.url or not self.rule_id:
            raise LabelError("a label needs a pull request URL and a rule id")
        where = f"{self.url} {self.rule_id}"
        if self.verdict not in VERDICTS:
            raise LabelError(f"{where}: the verdict is not one of {', '.join(VERDICTS)}")
        if not self.reason or self.reason != self.reason.strip():
            raise LabelError(f"{where}: the reason is empty or padded with spaces")
        if len(self.reason.splitlines()) != 1:
            raise LabelError(f"{where}: the reason has to fit on one line")
        if len(self.reason) > MAX_REASON_CHARS:
            raise LabelError(f"{where}: the reason is longer than {MAX_REASON_CHARS} characters")

    @property
    def key(self) -> Key:
        return (self.url, self.rule_id)


@dataclass(frozen=True)
class Labels:
    """The labels of one run, tied to the PandaGate commit that produced it."""

    pandagate_commit: str
    labels: tuple[Label, ...]

    def __post_init__(self) -> None:
        if not self.pandagate_commit:
            raise LabelError("the labels do not name the PandaGate commit of the run")
        seen: set[Key] = set()
        for label in self.labels:
            if label.key in seen:
                raise LabelError(f"{label.url} {label.rule_id}: labelled more than once")
            seen.add(label.key)


def parse_labels(payload: Any) -> Labels:
    """Labels out of the decoded content of a labels file."""
    if not isinstance(payload, dict) or set(payload) != _TOP_FIELDS:
        raise LabelError(f"expected an object with exactly {', '.join(sorted(_TOP_FIELDS))}")
    commit, entries = payload["pandagate_commit"], payload["labels"]
    if not isinstance(commit, str) or not isinstance(entries, list):
        raise LabelError("pandagate_commit has to be a string and labels a list")
    labels: list[Label] = []
    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or set(entry) != _LABEL_FIELDS:
            fields = ", ".join(sorted(_LABEL_FIELDS))
            raise LabelError(f"label {position}: expected an object with exactly {fields}")
        if not all(isinstance(value, str) for value in entry.values()):
            raise LabelError(f"label {position}: every field has to be a string")
        labels.append(Label(entry["url"], entry["rule_id"], entry["verdict"], entry["reason"]))
    return Labels(commit, tuple(labels))


def load_labels(path: Path = LABELS_PATH) -> Labels:
    """Labels from a file on disk."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise LabelError(f"{path.name}: not readable as JSON ({type(error).__name__})") from None
    return parse_labels(payload)


def dump_labels(labels: Labels) -> str:
    """The text of a labels file."""
    payload = {
        "pandagate_commit": labels.pandagate_commit,
        "labels": [
            {
                "url": label.url,
                "rule_id": label.rule_id,
                "verdict": label.verdict,
                "reason": label.reason,
            }
            for label in labels.labels
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def absent_keys(results: Mapping[str, Any]) -> list[Key]:
    """Every ABSENT signal of a run, in the order of the results."""
    return [
        (str(pull["url"]), str(signal["rule_id"]))
        for pull in results["pull_requests"]
        for signal in pull["signals"]
        if signal["outcome"] == "ABSENT"
    ]


def check_against(labels: Labels, results: Mapping[str, Any]) -> None:
    """Refuse labels that are not about this run or do not follow its order."""
    commit = str(results["pandagate_commit"])
    if labels.pandagate_commit != commit:
        raise LabelError(
            f"the labels are for commit {labels.pandagate_commit}, the results for {commit}"
        )
    order = {key: position for position, key in enumerate(absent_keys(results))}
    last = -1
    for label in labels.labels:
        position = order.get(label.key)
        if position is None:
            raise LabelError(f"{label.url} {label.rule_id}: not an ABSENT signal of this run")
        if position < last:
            raise LabelError(f"{label.url} {label.rule_id}: out of the order of the results")
        last = position


def unlabelled(labels: Labels, results: Mapping[str, Any]) -> list[Key]:
    """ABSENT signals of the run that have no label yet, in the order of the results."""
    done = {label.key for label in labels.labels}
    return [key for key in absent_keys(results) if key not in done]
