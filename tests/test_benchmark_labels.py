"""Hand labels for metric C: format, ties to the run, order."""

import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.labels import (
    LABELS_PATH,
    MAX_REASON_CHARS,
    VERDICTS,
    Label,
    LabelError,
    Labels,
    absent_keys,
    check_against,
    dump_labels,
    load_labels,
    parse_labels,
    unlabelled,
)

COMMIT = "796b735c3b387874fe8e40ec7da0f1f17cc77003"
FIRST = "https://github.com/octo/demo/pull/1"
SECOND = "https://github.com/octo/demo/pull/2"
REASON = "no reference in the title or description"


def _signal(rule_id: str, outcome: str) -> dict[str, str]:
    return {"rule_id": rule_id, "outcome": outcome, "detail": "observed"}


def _results() -> dict[str, Any]:
    return {
        "pandagate_commit": COMMIT,
        "pull_requests": [
            {
                "repository": "octo/demo",
                "url": FIRST,
                "signals": [
                    _signal("R1", "ABSENT"),
                    _signal("R2", "ABSENT"),
                    _signal("R3", "PRESENT"),
                ],
                "warnings": [],
            },
            {
                "repository": "octo/demo",
                "url": SECOND,
                "signals": [
                    _signal("R1", "PRESENT"),
                    _signal("R2", "ABSENT"),
                    _signal("R3", "NOT_APPLICABLE"),
                ],
                "warnings": [],
            },
        ],
    }


def _entry(url: str = FIRST, rule_id: str = "R1", verdict: str = "correct") -> dict[str, Any]:
    return {"url": url, "rule_id": rule_id, "verdict": verdict, "reason": REASON}


def _payload(*entries: Any) -> dict[str, Any]:
    return {"pandagate_commit": COMMIT, "labels": list(entries)}


def _labels(*keys: tuple[str, str], commit: str = COMMIT) -> Labels:
    return Labels(commit, tuple(Label(url, rule_id, "correct", REASON) for url, rule_id in keys))


BROKEN_PAYLOADS = [
    [],
    {"labels": []},
    {"pandagate_commit": COMMIT},
    {"pandagate_commit": 7, "labels": []},
    {"pandagate_commit": COMMIT, "labels": {}},
    {"pandagate_commit": COMMIT, "labels": [], "note": "extra"},
    _payload("text"),
    _payload({"url": FIRST, "rule_id": "R1", "verdict": "correct"}),
    _payload({**_entry(), "note": "extra"}),
    _payload({**_entry(), "reason": 5}),
]


def test_verdicts_are_the_two_of_the_protocol() -> None:
    assert VERDICTS == ("correct", "wrong")


def test_labels_file_sits_next_to_the_results() -> None:
    assert LABELS_PATH.name == "labels.json"
    assert LABELS_PATH.with_name("results.json").is_file()


def test_absent_keys_follow_the_order_of_the_results() -> None:
    assert absent_keys(_results()) == [(FIRST, "R1"), (FIRST, "R2"), (SECOND, "R2")]


def test_absent_keys_of_the_baseline_match_its_summary() -> None:
    results = json.loads(LABELS_PATH.with_name("results.json").read_text(encoding="utf-8"))
    keys = absent_keys(results)
    assert len(keys) == len(set(keys))
    assert len(keys) == sum(rule["absent"] for rule in results["summary"]["rules"].values())


def test_parse_reads_labels() -> None:
    labels = parse_labels(_payload(_entry(), _entry(SECOND, "R2", "wrong")))
    assert labels.pandagate_commit == COMMIT
    assert [label.key for label in labels.labels] == [(FIRST, "R1"), (SECOND, "R2")]
    assert [label.verdict for label in labels.labels] == ["correct", "wrong"]
    assert labels.labels[0].reason == REASON


@pytest.mark.parametrize("payload", BROKEN_PAYLOADS)
def test_parse_refuses_a_broken_file(payload: Any) -> None:
    with pytest.raises(LabelError):
        parse_labels(payload)


@pytest.mark.parametrize("verdict", ["", "Correct", "unsure", "wrong "])
def test_label_refuses_an_unknown_verdict(verdict: str) -> None:
    with pytest.raises(LabelError):
        Label(FIRST, "R1", verdict, REASON)


@pytest.mark.parametrize(
    "reason",
    ["", " padded", "padded ", "two\nlines", "two\rlines", "x" * (MAX_REASON_CHARS + 1)],
)
def test_label_refuses_a_bad_reason(reason: str) -> None:
    with pytest.raises(LabelError):
        Label(FIRST, "R1", "wrong", reason)


def test_label_accepts_a_reason_of_the_maximum_length() -> None:
    assert Label(FIRST, "R1", "wrong", "x" * MAX_REASON_CHARS).verdict == "wrong"


@pytest.mark.parametrize(("url", "rule_id"), [("", "R1"), (FIRST, "")])
def test_label_needs_a_url_and_a_rule(url: str, rule_id: str) -> None:
    with pytest.raises(LabelError):
        Label(url, rule_id, "correct", REASON)


def test_labels_need_the_commit_of_the_run() -> None:
    with pytest.raises(LabelError):
        Labels("", ())


def test_labels_refuse_a_signal_labelled_twice() -> None:
    with pytest.raises(LabelError, match="more than once"):
        _labels((FIRST, "R1"), (FIRST, "R1"))


def test_dump_round_trips() -> None:
    labels = _labels((FIRST, "R1"), (SECOND, "R2"))
    text = dump_labels(labels)
    assert text.endswith("}\n")
    assert parse_labels(json.loads(text)) == labels


def test_dump_keeps_text_readable() -> None:
    labels = Labels(COMMIT, (Label(FIRST, "R2", "wrong", "tests-dir: тесты в testing/"),))
    assert "tests-dir: тесты в testing/" in dump_labels(labels)


def test_load_reads_a_file(tmp_path: Path) -> None:
    path = tmp_path / "labels.json"
    path.write_text(dump_labels(_labels((FIRST, "R1"))), encoding="utf-8")
    assert load_labels(path) == _labels((FIRST, "R1"))


def test_load_refuses_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(LabelError, match="labels.json"):
        load_labels(tmp_path / "labels.json")


def test_load_refuses_text_that_is_not_json(tmp_path: Path) -> None:
    path = tmp_path / "labels.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(LabelError, match="labels.json"):
        load_labels(path)


def test_check_accepts_partial_labels_in_order() -> None:
    check_against(_labels((FIRST, "R1"), (SECOND, "R2")), _results())
    check_against(_labels(), _results())


def test_check_refuses_labels_of_another_commit() -> None:
    with pytest.raises(LabelError, match="commit"):
        check_against(_labels((FIRST, "R1"), commit="0" * 40), _results())


@pytest.mark.parametrize(
    "key",
    [(FIRST, "R3"), (SECOND, "R1"), (SECOND, "R3"), ("https://github.com/octo/demo/pull/9", "R1")],
)
def test_check_refuses_what_is_not_an_absent_signal(key: tuple[str, str]) -> None:
    with pytest.raises(LabelError, match="not an ABSENT signal"):
        check_against(_labels(key), _results())


def test_check_refuses_labels_out_of_order() -> None:
    with pytest.raises(LabelError, match="order"):
        check_against(_labels((SECOND, "R2"), (FIRST, "R1")), _results())


def test_unlabelled_lists_what_remains_in_order() -> None:
    assert unlabelled(_labels((FIRST, "R2")), _results()) == [(FIRST, "R1"), (SECOND, "R2")]
    assert unlabelled(_labels(), _results()) == absent_keys(_results())


def test_unlabelled_is_empty_when_everything_is_labelled() -> None:
    assert unlabelled(_labels((FIRST, "R1"), (FIRST, "R2"), (SECOND, "R2")), _results()) == []
