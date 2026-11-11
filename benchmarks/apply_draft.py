"""Move the verdicts of the labelling draft into labels.json.

The draft is the working copy and labels.json is rebuilt from it as a whole.
Lines without a verdict are skipped, so the command can run after every batch.
It refuses to write when the draft has lost a label that labels.json holds.
"""

import json
import sys
from collections.abc import Sequence
from pathlib import Path

from benchmarks.build_sheet import CACHE_DIRECTORY, DRAFT_NAME, RESULTS_PATH, draft_line
from benchmarks.labels import (
    LABELS_PATH,
    Key,
    Label,
    LabelError,
    Labels,
    absent_keys,
    check_against,
    dump_labels,
    load_labels,
    unlabelled,
)


class DraftError(ValueError):
    """The draft says something that cannot become labels."""


def parse_draft(text: str, keys: Sequence[Key]) -> list[Label]:
    """Labels out of the filled lines of a draft, in the order of the results."""
    expected = {draft_line(number, key): key for number, key in enumerate(keys, start=1)}
    order = {key: position for position, key in enumerate(keys)}
    labels: list[Label] = []
    for position, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        head, separator, answer = line.partition("=")
        key = expected.get(f"{head.rstrip()} =") if separator else None
        if key is None:
            raise DraftError(f"draft line {position}: not a line of the draft of this run")
        answer = answer.strip()
        if not answer:
            continue
        verdict, _, reason = answer.partition(" ")
        try:
            labels.append(Label(key[0], key[1], verdict, reason.strip()))
        except LabelError as error:
            raise DraftError(f"draft line {position}: {error}") from None
    return sorted(labels, key=lambda label: order[label.key])


def main(
    *,
    draft_path: Path = CACHE_DIRECTORY / DRAFT_NAME,
    results_path: Path = RESULTS_PATH,
    labels_path: Path = LABELS_PATH,
) -> int:
    """Rewrite labels.json from the draft and say how much is left."""
    try:
        results = json.loads(results_path.read_text(encoding="utf-8"))
        keys = absent_keys(results)
        draft = draft_path.read_text(encoding="utf-8")
        labels = Labels(str(results["pandagate_commit"]), tuple(parse_draft(draft, keys)))
        check_against(labels, results)
        if labels_path.is_file():
            kept = {label.key for label in labels.labels}
            dropped = [label for label in load_labels(labels_path).labels if label.key not in kept]
            if dropped:
                raise DraftError(
                    f"the draft would drop {len(dropped)} label(s) of {labels_path.name}, "
                    f"the first is {dropped[0].url} {dropped[0].rule_id}"
                )
    except (OSError, ValueError) as error:
        print(f"apply_draft: {error}", file=sys.stderr)
        return 1
    labels_path.write_text(dump_labels(labels), encoding="utf-8")
    wrong = sum(label.verdict == "wrong" for label in labels.labels)
    left = len(unlabelled(labels, results))
    print(f"apply_draft: {len(labels.labels)} of {len(keys)} labelled, {wrong} wrong, {left} left")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
