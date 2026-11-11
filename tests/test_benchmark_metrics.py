from typing import Any

from benchmarks.metrics import format_summary, summarise


def pr(repository: str = "octo/demo", **outcomes: str) -> dict[str, Any]:
    return {
        "repository": repository,
        "signals": [
            {"rule_id": rule_id, "outcome": outcome, "detail": ""}
            for rule_id, outcome in outcomes.items()
        ],
    }


def test_pull_request_with_two_absent_signals_counts_once():
    summary = summarise([pr(R1="ABSENT", R2="ABSENT"), pr(R1="PRESENT", R2="PRESENT")])

    assert summary["pull_requests"] == 2
    assert summary["commented"] == 1
    assert summary["comment_rate"] == 0.5


def test_rule_rate_leaves_out_not_applicable_and_unknown():
    pulls = [pr(R1="ABSENT"), pr(R1="PRESENT"), pr(R1="NOT_APPLICABLE"), pr(R1="UNKNOWN")]

    assert summarise(pulls)["rules"]["R1"] == {
        "present": 1,
        "absent": 1,
        "not_applicable": 1,
        "unknown": 1,
        "absent_rate": 0.5,
    }


def test_rule_rate_is_missing_when_the_rule_never_applied():
    summary = summarise([pr(R1="NOT_APPLICABLE"), pr(R1="UNKNOWN")])

    assert summary["rules"]["R1"]["absent_rate"] is None
    assert summary["commented"] == 0


def test_rules_are_listed_in_identifier_order():
    summary = summarise([pr(R3="PRESENT", R1="PRESENT", R2="PRESENT")])

    assert list(summary["rules"]) == ["R1", "R2", "R3"]


def test_breakdown_by_repository_keeps_first_seen_order():
    pulls = [pr("c/d", R1="ABSENT"), pr("a/b", R1="PRESENT"), pr("c/d", R1="PRESENT")]

    assert summarise(pulls)["by_repository"] == {
        "c/d": {"pull_requests": 2, "commented": 1},
        "a/b": {"pull_requests": 1, "commented": 0},
    }
    assert list(summarise(pulls)["by_repository"]) == ["c/d", "a/b"]


def test_empty_run_has_no_rates():
    assert summarise([]) == {
        "pull_requests": 0,
        "commented": 0,
        "comment_rate": None,
        "rules": {},
        "by_repository": {},
    }


def test_format_summary_shows_counts_and_rates():
    text = format_summary(summarise([pr(R1="ABSENT", R2="UNKNOWN"), pr(R1="PRESENT")]))

    assert "A. comment rate: 1/2 (50.0%)" in text
    assert "  R1: absent 1, present 1, not applicable 0, unknown 0, absent rate 50.0%" in text
    assert "  R2: absent 0, present 0, not applicable 0, unknown 1, absent rate n/a" in text
    assert "  octo/demo: 1/2" in text
