"""Tests for keeping one comment on a pull request, or none."""

import json
from collections.abc import Mapping
from typing import Any

import pytest

from pandagate.cli import ACTIONS_LOGIN, EXIT_FAILURE, EXIT_OK, main
from pandagate.github import API_ROOT, PER_PAGE, Client, GitHubError, PullRequestRef, Response
from pandagate.publish import Change, publish
from pandagate.render import MARKER

REF = PullRequestRef("octocat", "example", 42)
PAGE = "https://github.com/octocat/example/pull/42"
REPO_URL = f"{API_ROOT}/repos/octocat/example"
PR_URL = f"{REPO_URL}/pulls/42"
FILES_URL = f"{PR_URL}/files?per_page={PER_PAGE}&page=1"
USER_URL = f"{API_ROOT}/user"
COMMENTS_URL = f"{REPO_URL}/issues/42/comments"
LISTING_URL = f"{COMMENTS_URL}?per_page={PER_PAGE}&page=1"

OLD = f"{MARKER}\nold text\n"
NEW = f"{MARKER}\nnew text\n"

Table = dict[tuple[str, str], Response]


def item_url(comment_id: int) -> str:
    return f"{REPO_URL}/issues/comments/{comment_id}"


def ok(payload: Any) -> Response:
    return Response(200, json.dumps(payload).encode())


def comment(comment_id: int = 7, body: str = OLD, login: str = "panda-app") -> dict[str, Any]:
    return {"id": comment_id, "body": body, "user": {"login": login}}


class StubClient:
    """Stands in for the client and records what it was asked to write."""

    def __init__(self, existing: list[dict[str, Any]]) -> None:
        self.existing = existing
        self.actions: list[tuple[Any, ...]] = []

    def comments(self, ref: PullRequestRef) -> list[dict[str, Any]]:
        return self.existing

    def create_comment(self, ref: PullRequestRef, body: str) -> None:
        self.actions.append(("create", body))

    def update_comment(self, ref: PullRequestRef, comment_id: int, body: str) -> None:
        self.actions.append(("update", comment_id, body))

    def delete_comment(self, ref: PullRequestRef, comment_id: int) -> None:
        self.actions.append(("delete", comment_id))


class FakeApi:
    """Answers from a table of methods and URLs and records what was asked."""

    def __init__(self, table: Table) -> None:
        self.table = table
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def __call__(
        self,
        url: str,
        headers: Mapping[str, str],
        method: str = "GET",
        body: bytes | None = None,
    ) -> Response:
        self.calls.append((method, url, dict(headers), body))
        return self.table.get((method, url), Response(404, b""))

    def writes(self) -> list[tuple[str, str]]:
        return [(method, url) for method, url, _, _ in self.calls if method != "GET"]


def test_a_first_comment_is_created() -> None:
    stub = StubClient([])
    assert publish(stub, REF, NEW, "panda-app") is Change.CREATED
    assert stub.actions == [("create", NEW)]


def test_an_earlier_comment_is_updated_in_place() -> None:
    stub = StubClient([comment()])
    assert publish(stub, REF, NEW, "panda-app") is Change.UPDATED
    assert stub.actions == [("update", 7, NEW)]


def test_an_unchanged_comment_is_left_alone() -> None:
    stored = NEW.replace("\n", "\r\n").strip()
    stub = StubClient([comment(body=stored)])
    assert publish(stub, REF, NEW, "panda-app") is Change.UNCHANGED
    assert stub.actions == []


def test_nothing_left_to_ask_removes_the_comment() -> None:
    stub = StubClient([comment()])
    assert publish(stub, REF, None, "panda-app") is Change.DELETED
    assert stub.actions == [("delete", 7)]


def test_nothing_to_ask_and_no_comment_does_nothing() -> None:
    stub = StubClient([])
    assert publish(stub, REF, None, "panda-app") is Change.NOTHING
    assert stub.actions == []


def test_a_marker_typed_by_someone_else_is_not_touched() -> None:
    removing = StubClient([comment(login="contributor")])
    assert publish(removing, REF, None, "panda-app") is Change.NOTHING
    assert removing.actions == []
    posting = StubClient([comment(login="contributor")])
    assert publish(posting, REF, NEW, "panda-app") is Change.CREATED
    assert posting.actions == [("create", NEW)]


def test_a_comment_without_the_marker_is_not_touched() -> None:
    stub = StubClient([comment(body="plain words")])
    assert publish(stub, REF, None, "panda-app") is Change.NOTHING
    assert stub.actions == []


def test_a_marker_that_does_not_open_the_comment_does_not_count() -> None:
    stub = StubClient([comment(body=f"> quoted\n{MARKER}\n")])
    assert publish(stub, REF, None, "panda-app") is Change.NOTHING
    assert stub.actions == []


def test_duplicates_are_reduced_to_the_first() -> None:
    stub = StubClient([comment(7), comment(9)])
    assert publish(stub, REF, NEW, "panda-app") is Change.UPDATED
    assert stub.actions == [("delete", 9), ("update", 7, NEW)]


def test_the_login_is_compared_without_case() -> None:
    stub = StubClient([comment(login="Panda-App")])
    assert publish(stub, REF, None, "panda-app") is Change.DELETED


def test_malformed_entries_are_ignored() -> None:
    stub = StubClient(
        [
            {"id": "7", "body": OLD, "user": {"login": "panda-app"}},
            {"id": 8, "body": OLD, "user": None},
            {"id": 9, "body": None, "user": {"login": "panda-app"}},
            {"id": True, "body": OLD, "user": {"login": "panda-app"}},
        ]
    )
    assert publish(stub, REF, None, "panda-app") is Change.NOTHING
    assert stub.actions == []


def test_the_identity_is_the_login_of_the_token() -> None:
    api = FakeApi({("GET", USER_URL): ok({"login": "panda-app"})})
    assert Client("t0ken", api).identity() == "panda-app"


@pytest.mark.parametrize("answer", [Response(403, b""), ok({"login": ""}), ok([])])
def test_an_identity_the_api_will_not_give_is_none(answer: Response) -> None:
    api = FakeApi({("GET", USER_URL): answer})
    assert Client("t0ken", api).identity() is None


def test_comments_are_read_page_by_page() -> None:
    full = [comment(index) for index in range(PER_PAGE)]
    second = f"{COMMENTS_URL}?per_page={PER_PAGE}&page=2"
    api = FakeApi({("GET", LISTING_URL): ok(full), ("GET", second): ok([comment(), "junk"])})
    assert len(Client("t0ken", api).comments(REF)) == PER_PAGE + 1
    assert len(api.calls) == 2


def test_creating_a_comment_posts_json_with_the_token() -> None:
    api = FakeApi({("POST", COMMENTS_URL): Response(201, b"{}")})
    Client("t0ken", api).create_comment(REF, NEW)
    method, url, headers, body = api.calls[0]
    assert (method, url) == ("POST", COMMENTS_URL)
    assert headers["Content-Type"] == "application/json"
    assert headers["Authorization"] == "Bearer t0ken"
    assert body is not None
    assert json.loads(body) == {"body": NEW}


def test_a_refused_write_is_an_error() -> None:
    api = FakeApi({("POST", COMMENTS_URL): Response(403, b"")})
    with pytest.raises(GitHubError) as caught:
        Client("t0ken", api).create_comment(REF, NEW)
    assert "403" in str(caught.value)


def test_updating_a_comment_patches_it_by_identifier() -> None:
    api = FakeApi({("PATCH", item_url(7)): ok({})})
    Client("t0ken", api).update_comment(REF, 7, NEW)
    assert api.writes() == [("PATCH", item_url(7))]


def test_deleting_a_comment_deletes_it_by_identifier() -> None:
    api = FakeApi({("DELETE", item_url(7)): Response(204, b"")})
    Client("t0ken", api).delete_comment(REF, 7)
    assert api.writes() == [("DELETE", item_url(7))]


def test_a_read_sends_no_body() -> None:
    api = FakeApi({("GET", USER_URL): ok({"login": "panda-app"})})
    Client("t0ken", api).identity()
    _, _, headers, body = api.calls[0]
    assert body is None
    assert "Content-Type" not in headers


def pr_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "number": 42,
        "title": "Add a thing",
        "body": "",
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


def file_entry(path: str) -> dict[str, Any]:
    return {"filename": path, "status": "modified", "additions": 10, "deletions": 2}


def with_questions() -> Table:
    files = [file_entry("src/alpha/engine.py")]
    return {("GET", PR_URL): ok(pr_payload()), ("GET", FILES_URL): ok(files)}


def without_questions() -> Table:
    payload = pr_payload(body="Fixes #7", changed_files=2)
    files = [file_entry("src/alpha/engine.py"), file_entry("tests/test_engine.py")]
    return {("GET", PR_URL): ok(payload), ("GET", FILES_URL): ok(files)}


def post(
    capsys: pytest.CaptureFixture[str],
    table: Table,
    *extra: str,
    environ: Mapping[str, str] | None = None,
) -> tuple[int, str, str, FakeApi]:
    api = FakeApi(table)
    env = {"GITHUB_TOKEN": "t0ken"} if environ is None else environ
    status = main(["check", "--post", *extra, PAGE], environ=env, transport=api)
    captured = capsys.readouterr()
    return status, captured.out, captured.err, api


def test_post_without_a_token_is_refused_before_any_request(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, _, err, api = post(capsys, with_questions(), environ={})
    assert status == EXIT_FAILURE
    assert "--post needs a token" in err
    assert api.calls == []


def test_post_creates_the_comment(capsys: pytest.CaptureFixture[str]) -> None:
    table = with_questions() | {
        ("GET", USER_URL): ok({"login": "panda-app"}),
        ("GET", LISTING_URL): ok([]),
        ("POST", COMMENTS_URL): Response(201, b"{}"),
    }
    status, out, err, api = post(capsys, table)
    assert status == EXIT_OK
    assert out == ""
    assert err.splitlines() == ["pandagate: comment posted"]
    assert api.writes() == [("POST", COMMENTS_URL)]
    sent = api.calls[-1][3]
    assert sent is not None
    assert json.loads(sent)["body"].startswith(MARKER)


def test_a_workflow_token_is_recognised_by_its_environment(
    capsys: pytest.CaptureFixture[str],
) -> None:
    table = without_questions() | {
        ("GET", LISTING_URL): ok([comment(login=ACTIONS_LOGIN)]),
        ("DELETE", item_url(7)): Response(204, b""),
    }
    environ = {"GITHUB_TOKEN": "t0ken", "GITHUB_ACTIONS": "true"}
    status, _, err, api = post(capsys, table, environ=environ)
    assert status == EXIT_OK
    assert api.writes() == [("DELETE", item_url(7))]
    assert err.splitlines() == ["pandagate: nothing to ask about; comment removed"]


def test_an_unknown_identity_writes_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    table = with_questions() | {("GET", LISTING_URL): ok([])}
    status, _, err, api = post(capsys, table)
    assert status == EXIT_FAILURE
    assert "--author" in err
    assert api.writes() == []


def test_author_names_the_account_and_skips_the_lookup(
    capsys: pytest.CaptureFixture[str],
) -> None:
    table = with_questions() | {
        ("GET", LISTING_URL): ok([comment(login="my-app[bot]")]),
        ("PATCH", item_url(7)): ok({}),
    }
    status, _, err, api = post(capsys, table, "--author", "my-app[bot]")
    assert status == EXIT_OK
    assert err.splitlines() == ["pandagate: comment updated"]
    assert USER_URL not in [url for _, url, _, _ in api.calls]


def test_an_author_that_is_not_a_login_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["check", "--post", "--author", "a b", PAGE])
    assert caught.value.code == 2


def test_a_refused_post_is_a_failure(capsys: pytest.CaptureFixture[str]) -> None:
    table = with_questions() | {
        ("GET", USER_URL): ok({"login": "panda-app"}),
        ("GET", LISTING_URL): ok([]),
    }
    status, _, err, _ = post(capsys, table)
    assert status == EXIT_FAILURE
    assert "404" in err


def test_without_post_only_the_pull_request_is_read(capsys: pytest.CaptureFixture[str]) -> None:
    api = FakeApi(with_questions())
    status = main(["check", PAGE], environ={"GITHUB_TOKEN": "t0ken"}, transport=api)
    capsys.readouterr()
    assert status == EXIT_OK
    assert api.writes() == []
    assert USER_URL not in [url for _, url, _, _ in api.calls]
