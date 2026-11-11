import json
import urllib.parse
from pathlib import Path
from typing import Any

from benchmarks.run_benchmark import CachedTransport, RunError, main
from pandagate.github import Response
from pandagate.rules.base import Outcome, Signal
from pandagate.score import Report

PULL_URL = "https://api.github.com/repos/octo/demo/pulls/7"
FILES_URL = "https://api.github.com/repos/octo/demo/pulls/7/files?per_page=100&page=1"

PULL = {
    "number": 7,
    "title": "Fix the parser",
    "body": "Fixes #1",
    "state": "closed",
    "merged": True,
    "author_association": "CONTRIBUTOR",
    "user": {"login": "someone", "type": "User"},
    "base": {"ref": "main", "repo": {"full_name": "octo/demo"}},
    "head": {"ref": "fix", "sha": "0" * 40},
    "additions": 3,
    "deletions": 1,
    "changed_files": 1,
}
FILE = {"filename": "src/app.py", "status": "modified", "additions": 3, "deletions": 1}


class Network:
    """A transport that answers like the API and records the requests."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.calls: list[tuple[str, str]] = []

    def __call__(self, url, headers, method="GET", body=None) -> Response:
        self.calls.append((method, url))
        if self.status != 200:
            return Response(self.status, b"")
        if urllib.parse.urlsplit(url).path.endswith("/files"):
            return Response(200, json.dumps([FILE]).encode())
        return Response(200, json.dumps(PULL).encode())


def asks(facts: Any) -> Report:
    signal = Signal(
        rule_id="R9",
        title="Example",
        outcome=Outcome.ABSENT,
        detail="nothing found",
        question="Why?",
    )
    return Report(signals=(signal,))


def write_sample(directory: Path) -> Path:
    path = directory / "sample.json"
    document = {
        "cutoff": "2026-10-01T00:00:00Z",
        "taken_at": "2026-11-11T08:39:04Z",
        "repositories": [],
        "pull_requests": [
            {"repository": "octo/demo", "url": f"https://github.com/octo/demo/pull/{number}"}
            for number in (7, 8)
        ],
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def run(directory: Path, network: Network, **changes: Any) -> int:
    options: dict[str, Any] = {
        "environ": {},
        "transport": network,
        "sample_path": write_sample(directory),
        "results_path": directory / "results.json",
        "cache_dir": directory / "cache",
        "commit": lambda: "abc123",
        "judge": asks,
    }
    return main(**(options | changes))


def test_cache_answers_the_second_request(tmp_path):
    network = Network()
    transport = CachedTransport(tmp_path / "cache", network)

    first = transport(PULL_URL, {})
    second = transport(PULL_URL, {})

    assert first == second
    assert len(network.calls) == 1
    assert (transport.hits, transport.misses) == (1, 1)


def test_cache_does_not_keep_failures(tmp_path):
    network = Network(500)
    transport = CachedTransport(tmp_path / "cache", network)

    assert transport(PULL_URL, {}).status == 500
    assert transport(PULL_URL, {}).status == 500
    assert len(network.calls) == 2
    assert not (tmp_path / "cache").exists()


def test_cache_passes_other_methods_through(tmp_path):
    network = Network()
    transport = CachedTransport(tmp_path / "cache", network)

    transport(PULL_URL, {}, "DELETE")
    transport(PULL_URL, {}, "DELETE")

    assert network.calls == [("DELETE", PULL_URL), ("DELETE", PULL_URL)]
    assert transport.hits == 0


def test_cache_keeps_each_url_apart(tmp_path):
    transport = CachedTransport(tmp_path / "cache", Network())
    transport(PULL_URL, {})
    transport(FILES_URL, {})

    assert json.loads(transport(PULL_URL, {}).body) == PULL
    assert json.loads(transport(FILES_URL, {}).body) == [FILE]
    assert transport.hits == 2


def test_main_writes_the_outcomes_and_the_summary(tmp_path):
    network = Network()

    assert run(tmp_path, network) == 0

    document = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert document["pandagate_commit"] == "abc123"
    assert document["sample_taken_at"] == "2026-11-11T08:39:04Z"
    assert document["summary"]["commented"] == 2
    assert document["summary"]["comment_rate"] == 1.0
    assert document["pull_requests"][0] == {
        "repository": "octo/demo",
        "url": "https://github.com/octo/demo/pull/7",
        "signals": [{"rule_id": "R9", "outcome": "ABSENT", "detail": "nothing found"}],
        "warnings": [],
    }
    assert len(network.calls) == 4


def test_main_sends_nothing_on_the_second_run(tmp_path):
    assert run(tmp_path, Network()) == 0
    offline = Network(500)

    assert run(tmp_path, offline) == 0
    assert offline.calls == []


def test_main_fails_without_a_sample(tmp_path):
    network = Network()

    assert run(tmp_path, network, sample_path=tmp_path / "missing.json") == 1
    assert network.calls == []
    assert not (tmp_path / "results.json").exists()


def test_main_fails_when_a_pull_request_cannot_be_read(tmp_path, capsys):
    assert run(tmp_path, Network(500)) == 1

    assert "GitHub answered 500" in capsys.readouterr().err
    assert not (tmp_path / "results.json").exists()


def test_main_fails_when_no_rule_reports(tmp_path, capsys):
    assert run(tmp_path, Network(), judge=lambda facts: Report()) == 1

    assert "no rule reported anything" in capsys.readouterr().err
    assert not (tmp_path / "results.json").exists()


def test_main_measures_nothing_when_the_commit_is_refused(tmp_path, capsys):
    network = Network()

    def refuse() -> str:
        raise RunError("src has uncommitted changes; commit them before measuring")

    assert run(tmp_path, network, commit=refuse) == 1
    assert "uncommitted changes" in capsys.readouterr().err
    assert network.calls == []
