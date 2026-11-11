import json
import re
import urllib.parse
from typing import Any

import pytest

from benchmarks import pick_sample
from benchmarks.pick_sample import SampleError, assemble, closed_pulls, main
from benchmarks.sampling import CUTOFF, PER_REPOSITORY, REPOSITORIES, RESERVE, Selection
from pandagate.github import API_ROOT, PER_PAGE, GitHubError, Response


def pull(number: int, **changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "number": number,
        "html_url": f"https://github.com/octo/demo/pull/{number}",
        "created_at": "2026-09-01T00:00:00Z",
        "merged_at": "2026-09-02T00:00:00Z",
        "author_association": "CONTRIBUTOR",
        "user": {"login": "someone", "type": "User"},
    }
    return base | changes


def full_page() -> list[dict[str, Any]]:
    return [pull(number) for number in range(PER_PAGE)]


def full_selection() -> Selection:
    return Selection(tuple(pull(number) for number in range(PER_REPOSITORY)), PER_REPOSITORY)


SHORT = Selection((), 1000)


class Pages:
    """A transport that serves prepared answers in order and records the requests."""

    def __init__(self, *answers: Any, repeat: bool = False) -> None:
        self.answers = answers
        self.repeat = repeat
        self.calls: list[tuple[str, dict[str, str], str, bytes | None]] = []

    def __call__(self, url, headers, method="GET", body=None) -> Response:
        self.calls.append((url, dict(headers), method, body))
        answer = self.answers[0 if self.repeat else len(self.calls) - 1]
        if isinstance(answer, Response):
            return answer
        return Response(200, json.dumps(answer).encode())


def query_of(url: str) -> dict[str, list[str]]:
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)


def test_closed_pulls_reads_until_a_short_page():
    transport = Pages(full_page(), [pull(1000)])

    found = list(closed_pulls("octo/demo", "t0ken", transport))

    assert len(found) == PER_PAGE + 1
    assert len(transport.calls) == 2
    first, second = transport.calls
    assert first[0].startswith(f"{API_ROOT}/repos/octo/demo/pulls?")
    assert query_of(first[0]) == {
        "state": ["closed"],
        "sort": ["created"],
        "direction": ["desc"],
        "per_page": [str(PER_PAGE)],
        "page": ["1"],
    }
    assert query_of(second[0])["page"] == ["2"]
    assert first[2:] == ("GET", None)


def test_closed_pulls_sends_the_token_only_when_there_is_one():
    with_token = Pages([])
    without = Pages([])

    list(closed_pulls("octo/demo", "t0ken", with_token))
    list(closed_pulls("octo/demo", None, without))

    assert with_token.calls[0][1]["Authorization"] == "Bearer t0ken"
    assert "Authorization" not in without.calls[0][1]


def test_closed_pulls_asks_for_no_more_pages_than_are_read():
    transport = Pages(full_page(), full_page())

    next(closed_pulls("octo/demo", "t0ken", transport))

    assert len(transport.calls) == 1


@pytest.mark.parametrize("answer", [Response(404, b""), Response(200, b"{"), Response(200, b"{}")])
def test_closed_pulls_refuses_an_unexpected_answer(answer):
    with pytest.raises(GitHubError, match="pull requests of octo/demo"):
        list(closed_pulls("octo/demo", "t0ken", Pages(answer)))


def test_closed_pulls_stops_at_the_page_limit(monkeypatch):
    monkeypatch.setattr(pick_sample, "MAX_PAGES", 2)
    transport = Pages(full_page(), full_page())

    with pytest.raises(GitHubError, match="more than 2 pages"):
        list(closed_pulls("octo/demo", "t0ken", transport))

    assert len(transport.calls) == 2


def test_closed_pulls_drops_entries_that_are_not_objects():
    found = list(closed_pulls("octo/demo", "t0ken", Pages([pull(1), "text", None])))

    assert [item["number"] for item in found] == [1]


def test_assemble_takes_every_repository_in_order():
    sample, visited = assemble(lambda repository: full_selection())

    assert len(sample) == len(REPOSITORIES) * PER_REPOSITORY
    assert [item["repository"] for item in sample[::PER_REPOSITORY]] == list(REPOSITORIES)
    assert [item["repository"] for item in visited] == list(REPOSITORIES)


def test_assemble_replaces_a_short_repository_with_the_reserve():
    short = REPOSITORIES[3]

    sample, visited = assemble(
        lambda repository: SHORT if repository == short else full_selection()
    )

    used = [item["repository"] for item in sample[::PER_REPOSITORY]]
    assert used == [*REPOSITORIES[:3], RESERVE[0], *REPOSITORIES[4:]]
    assert len(sample) == len(REPOSITORIES) * PER_REPOSITORY
    assert {"repository": short, "scanned": 1000, "picked": 0} in visited


def test_assemble_fails_when_the_reserve_runs_out():
    read: list[str] = []

    def always_short(repository: str) -> Selection:
        read.append(repository)
        return SHORT

    with pytest.raises(SampleError, match="reserve is used up"):
        assemble(always_short)

    assert read == [REPOSITORIES[0], *RESERVE]


def test_main_writes_the_sample(tmp_path):
    path = tmp_path / "sample.json"
    transport = Pages(full_page(), repeat=True)

    code = main(environ={"GH_TOKEN": "t0ken"}, transport=transport, path=path)

    assert code == 0
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["cutoff"] == CUTOFF
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", document["taken_at"])
    assert len(document["pull_requests"]) == len(REPOSITORIES) * PER_REPOSITORY
    assert [item["repository"] for item in document["repositories"]] == list(REPOSITORIES)
    assert len(transport.calls) == len(REPOSITORIES)


def test_main_needs_a_token(tmp_path):
    path = tmp_path / "sample.json"
    transport = Pages()

    assert main(environ={}, transport=transport, path=path) == 1
    assert not path.exists()
    assert transport.calls == []


def test_main_never_replaces_an_existing_sample(tmp_path):
    path = tmp_path / "sample.json"
    path.write_text("frozen", encoding="utf-8")
    transport = Pages()

    assert main(environ={"GH_TOKEN": "t0ken"}, transport=transport, path=path) == 1
    assert path.read_text(encoding="utf-8") == "frozen"
    assert transport.calls == []


def test_main_reports_an_api_failure_without_the_token(tmp_path, capsys):
    path = tmp_path / "sample.json"
    transport = Pages(Response(500, b""), repeat=True)

    assert main(environ={"GH_TOKEN": "t0ken"}, transport=transport, path=path) == 1

    stderr = capsys.readouterr().err
    assert "GitHub answered 500" in stderr
    assert "t0ken" not in stderr
    assert not path.exists()
