"""Tests for reading one pull request from the GitHub REST API."""

import json
import urllib.request
from collections.abc import Mapping
from typing import Any

import pytest

from pandagate import github
from pandagate.config import MAX_CONFIG_BYTES, Config, ConfigError, Mode
from pandagate.github import (
    API_ROOT,
    MAX_FILE_PAGES,
    PER_PAGE,
    Client,
    GitHubError,
    PullRequestRef,
    Response,
    load_pull_request,
    parse_pull_request_url,
)

REF = PullRequestRef("octocat", "example", 42)
REPO_URL = f"{API_ROOT}/repos/octocat/example"
PR_URL = f"{REPO_URL}/pulls/42"
CONFIG_URL = f"{REPO_URL}/contents/.pandagate.toml?ref=main"


def files_url(page: int) -> str:
    return f"{PR_URL}/files?per_page={PER_PAGE}&page={page}"


def ok(payload: Any) -> Response:
    return Response(200, json.dumps(payload).encode())


def file_entry(index: int = 0) -> dict[str, Any]:
    return {
        "filename": f"src/alpha/file{index}.py",
        "status": "modified",
        "additions": 10,
        "deletions": 2,
    }


def pr_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "number": 42,
        "title": "Add a thing",
        "body": "Fixes #7",
        "user": {"login": "contributor"},
        "author_association": "CONTRIBUTOR",
        "base": {"ref": "main", "repo": {"full_name": "octocat/example"}},
        "commits": 1,
        "additions": 10,
        "deletions": 2,
        "changed_files": 1,
    }
    payload.update(overrides)
    return payload


class FakeTransport:
    """Answers from a table of URLs and records what was asked."""

    def __init__(self, routes: dict[str, Response]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: Mapping[str, str]) -> Response:
        self.calls.append((url, dict(headers)))
        return self.routes.get(url, Response(404, b""))


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/octocat/example/pull/42",
        "https://github.com/octocat/example/pull/42/files",
        "https://GitHub.com/octocat/example/pull/42?diff=split#discussion",
    ],
)
def test_a_pull_request_url_is_parsed(url: str) -> None:
    assert parse_pull_request_url(url) == REF


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/octocat/example/pull/42",
        "https://gitlab.com/octocat/example/pull/42",
        "https://github.com.evil.example/octocat/example/pull/42",
        "https://github.com@evil.example/octocat/example/pull/42",
        "https://token@github.com/octocat/example/pull/42",
        "https://github.com:8443/octocat/example/pull/42",
        "https://github.com:port/octocat/example/pull/42",
        "https://github.com/octocat/example/issues/42",
        "https://github.com/octocat/example/pull/0",
        "https://github.com/octocat/example/pull/4x",
        "https://github.com/octo%2Fcat/example/pull/42",
        "https://github.com/octocat/../pull/42",
        "https://github.com/octocat/example",
        "not a url",
    ],
)
def test_anything_else_is_refused(url: str) -> None:
    with pytest.raises(GitHubError):
        parse_pull_request_url(url)


def test_a_reference_knows_its_slug() -> None:
    assert REF.slug == "octocat/example"


def test_requests_carry_the_token_and_the_api_headers() -> None:
    transport = FakeTransport({PR_URL: ok(pr_payload())})
    Client("s3cret", transport).pull_request(REF)
    url, headers = transport.calls[0]
    assert url == PR_URL
    assert headers["Authorization"] == "Bearer s3cret"
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert headers["User-Agent"].startswith("pandagate/")


@pytest.mark.parametrize("token", [None, ""])
def test_without_a_token_no_authorization_header_is_sent(token: str | None) -> None:
    transport = FakeTransport({PR_URL: ok(pr_payload())})
    Client(token, transport).pull_request(REF)
    assert "Authorization" not in transport.calls[0][1]


@pytest.mark.parametrize(
    "token", ["abc\r\nX-Injected: 1", "abc def", "\u0442\u043e\u043a\u0435\u043d"]
)
def test_a_token_that_cannot_be_a_header_is_refused_without_being_echoed(token: str) -> None:
    with pytest.raises(GitHubError) as caught:
        Client(token, FakeTransport({}))
    assert token not in str(caught.value)


@pytest.mark.parametrize("status", [301, 401, 403, 404, 429, 500])
def test_a_failed_request_reports_the_status_and_not_the_body(status: int) -> None:
    transport = FakeTransport({PR_URL: Response(status, b"upstream-detail")})
    with pytest.raises(GitHubError) as caught:
        Client(None, transport).pull_request(REF)
    assert str(status) in str(caught.value)
    assert "upstream-detail" not in str(caught.value)


def test_a_pull_request_that_is_not_json_is_an_error() -> None:
    transport = FakeTransport({PR_URL: Response(200, b"<html>")})
    with pytest.raises(GitHubError):
        Client(None, transport).pull_request(REF)


def test_a_pull_request_that_is_not_an_object_is_an_error() -> None:
    transport = FakeTransport({PR_URL: ok([])})
    with pytest.raises(GitHubError):
        Client(None, transport).pull_request(REF)


def test_a_short_first_page_is_the_whole_file_list() -> None:
    transport = FakeTransport({files_url(1): ok([file_entry()])})
    files, incomplete = Client(None, transport).changed_files(REF)
    assert files == [file_entry()]
    assert incomplete is False
    assert len(transport.calls) == 1


def test_pages_are_read_until_a_short_one() -> None:
    full = [file_entry(index) for index in range(PER_PAGE)]
    rest = [file_entry(index) for index in range(3)]
    transport = FakeTransport({files_url(1): ok(full), files_url(2): ok(rest)})
    files, incomplete = Client(None, transport).changed_files(REF)
    assert len(files) == PER_PAGE + 3
    assert incomplete is False
    assert len(transport.calls) == 2


def test_a_full_page_followed_by_an_empty_one_is_complete() -> None:
    full = [file_entry(index) for index in range(PER_PAGE)]
    transport = FakeTransport({files_url(1): ok(full), files_url(2): ok([])})
    files, incomplete = Client(None, transport).changed_files(REF)
    assert len(files) == PER_PAGE
    assert incomplete is False


def test_reaching_the_page_limit_reports_the_list_as_incomplete() -> None:
    full = ok([file_entry(index) for index in range(PER_PAGE)])
    routes = {files_url(page): full for page in range(1, MAX_FILE_PAGES + 1)}
    transport = FakeTransport(routes)
    files, incomplete = Client(None, transport).changed_files(REF)
    assert len(files) == PER_PAGE * MAX_FILE_PAGES
    assert incomplete is True
    assert len(transport.calls) == MAX_FILE_PAGES


def test_entries_that_are_not_objects_are_dropped_and_reported() -> None:
    transport = FakeTransport({files_url(1): ok([file_entry(), "junk", None])})
    files, incomplete = Client(None, transport).changed_files(REF)
    assert files == [file_entry()]
    assert incomplete is True


def test_a_file_list_that_is_not_a_list_is_an_error() -> None:
    transport = FakeTransport({files_url(1): ok({"message": "nope"})})
    with pytest.raises(GitHubError):
        Client(None, transport).changed_files(REF)


def test_a_missing_configuration_file_means_the_defaults() -> None:
    assert Client(None, FakeTransport({})).config(REF, "main") == Config()


def test_the_configuration_is_read_raw_from_the_base_branch() -> None:
    transport = FakeTransport({CONFIG_URL: Response(200, b'mode = "off"\n')})
    config = Client(None, transport).config(REF, "main")
    assert config.mode is Mode.OFF
    url, headers = transport.calls[0]
    assert url == CONFIG_URL
    assert headers["Accept"] == "application/vnd.github.raw+json"


def test_an_oversized_configuration_is_refused() -> None:
    body = b"#" * (MAX_CONFIG_BYTES + 1)
    transport = FakeTransport({CONFIG_URL: Response(200, body)})
    with pytest.raises(ConfigError):
        Client(None, transport).config(REF, "main")


def test_a_configuration_that_is_not_utf8_is_refused() -> None:
    transport = FakeTransport({CONFIG_URL: Response(200, b"\xff\xfe")})
    with pytest.raises(ConfigError):
        Client(None, transport).config(REF, "main")


def test_a_failed_configuration_request_is_an_error_not_the_defaults() -> None:
    transport = FakeTransport({CONFIG_URL: Response(500, b"")})
    with pytest.raises(GitHubError):
        Client(None, transport).config(REF, "main")


def test_a_branch_name_cannot_add_parameters_to_the_request() -> None:
    transport = FakeTransport({})
    Client(None, transport).config(REF, "release/1.x&mode=off")
    expected = f"{REPO_URL}/contents/.pandagate.toml?ref=release%2F1.x%26mode%3Doff"
    assert transport.calls[0][0] == expected


def test_loading_builds_the_facts_and_the_configuration() -> None:
    transport = FakeTransport(
        {
            PR_URL: ok(pr_payload()),
            files_url(1): ok([file_entry()]),
            CONFIG_URL: Response(200, b'enabled_rules = ["R1"]\n'),
        }
    )
    facts, config = load_pull_request(Client("s3cret", transport), REF)
    assert facts.repository == "octocat/example"
    assert facts.number == 42
    assert facts.paths == ("src/alpha/file0.py",)
    assert facts.files_truncated is False
    assert config.enabled_rules == ("R1",)


def test_loading_talks_to_one_host_only() -> None:
    transport = FakeTransport({PR_URL: ok(pr_payload()), files_url(1): ok([file_entry()])})
    load_pull_request(Client("s3cret", transport), REF)
    assert len(transport.calls) == 3
    assert all(url.startswith(f"{API_ROOT}/") for url, _ in transport.calls)


def test_fewer_files_listed_than_reported_means_a_truncated_list() -> None:
    transport = FakeTransport(
        {PR_URL: ok(pr_payload(changed_files=5)), files_url(1): ok([file_entry()])}
    )
    facts, _ = load_pull_request(Client(None, transport), REF)
    assert facts.files_truncated is True


def test_a_pull_request_without_a_base_branch_is_an_error() -> None:
    transport = FakeTransport({PR_URL: ok(pr_payload(base=None))})
    with pytest.raises(GitHubError):
        load_pull_request(Client(None, transport), REF)


def test_a_redirect_is_never_followed() -> None:
    handlers = [
        handler
        for handler in github._OPENER.handlers
        if isinstance(handler, urllib.request.HTTPRedirectHandler)
    ]
    assert [type(handler) for handler in handlers] == [github._NoRedirect]
    request = urllib.request.Request(API_ROOT)
    target = "https://evil.example/"
    assert handlers[0].redirect_request(request, None, 302, "Found", {}, target) is None
