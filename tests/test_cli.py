"""Tests for the command line."""

import json
import subprocess
import sys
from collections.abc import Mapping
from typing import Any

import pytest

from pandagate import __version__
from pandagate.cli import EXIT_FAILURE, EXIT_OK, main
from pandagate.github import API_ROOT, PER_PAGE, Response
from pandagate.render import MARKER

PAGE = "https://github.com/octocat/example/pull/42"
REPO_URL = f"{API_ROOT}/repos/octocat/example"
PR_URL = f"{REPO_URL}/pulls/42"
FILES_URL = f"{PR_URL}/files?per_page={PER_PAGE}&page=1"
CONFIG_URL = f"{REPO_URL}/contents/.pandagate.toml?ref=main"

Outcome = tuple[int, str, str, "FakeTransport"]


class FakeTransport:
    """Answers from a table of URLs and records what was asked."""

    def __init__(self, table: dict[str, Response]) -> None:
        self.table = table
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: Mapping[str, str]) -> Response:
        self.calls.append((url, dict(headers)))
        return self.table.get(url, Response(404, b""))


def ok(payload: Any) -> Response:
    return Response(200, json.dumps(payload).encode())


def file_entry(path: str) -> dict[str, Any]:
    return {"filename": path, "status": "modified", "additions": 10, "deletions": 2}


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


def routes(
    payload: dict[str, Any] | None = None,
    files: list[dict[str, Any]] | None = None,
    config: bytes | None = None,
) -> dict[str, Response]:
    listed = [file_entry("src/alpha/engine.py")] if files is None else files
    table = {PR_URL: ok(pr_payload() if payload is None else payload), FILES_URL: ok(listed)}
    if config is not None:
        table[CONFIG_URL] = Response(200, config)
    return table


def run(
    capsys: pytest.CaptureFixture[str],
    table: dict[str, Response],
    url: str = PAGE,
    environ: Mapping[str, str] | None = None,
) -> Outcome:
    transport = FakeTransport(table)
    status = main(["check", url], environ=environ or {}, transport=transport)
    captured = capsys.readouterr()
    return status, captured.out, captured.err, transport


def test_check_prints_the_comment_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    status, out, err, _ = run(capsys, routes())
    assert status == EXIT_OK
    assert out.startswith(MARKER + "\n")
    assert err == ""


def test_nothing_to_ask_prints_no_comment(capsys: pytest.CaptureFixture[str]) -> None:
    payload = pr_payload(body="Fixes #7", changed_files=2)
    files = [file_entry("src/alpha/engine.py"), file_entry("tests/test_engine.py")]
    status, out, err, _ = run(capsys, routes(payload, files))
    assert status == EXIT_OK
    assert out == ""
    assert "nothing to ask about" in err


def test_mode_off_prints_no_comment(capsys: pytest.CaptureFixture[str]) -> None:
    status, out, err, _ = run(capsys, routes(config=b'mode = "off"\n'))
    assert status == EXIT_OK
    assert out == ""
    assert "nothing to ask about" in err


def test_notes_go_to_standard_error(capsys: pytest.CaptureFixture[str]) -> None:
    status, out, err, _ = run(capsys, routes(config=b"verdict = true\n"))
    assert status == EXIT_OK
    assert "pandagate: note: unknown key: verdict" in err.splitlines()
    assert "unknown key: verdict" in out


def test_a_url_on_another_host_fails_before_any_request(
    capsys: pytest.CaptureFixture[str],
) -> None:
    url = "https://gitlab.com/octocat/example/pull/42"
    status, out, err, transport = run(capsys, routes(), url=url)
    assert status == EXIT_FAILURE
    assert out == ""
    assert err.startswith("pandagate: error: ")
    assert transport.calls == []


def test_an_api_failure_is_reported_with_its_status(capsys: pytest.CaptureFixture[str]) -> None:
    status, out, err, _ = run(capsys, {})
    assert status == EXIT_FAILURE
    assert out == ""
    assert "404" in err


def test_an_unusable_configuration_is_an_error(capsys: pytest.CaptureFixture[str]) -> None:
    status, out, err, _ = run(capsys, routes(config=b'mode = "block"\n'))
    assert status == EXIT_FAILURE
    assert out == ""
    assert err.startswith("pandagate: error: mode:")


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({"GITHUB_TOKEN": "aaa\n"}, "Bearer aaa"),
        ({"GH_TOKEN": "bbb"}, "Bearer bbb"),
        ({"GITHUB_TOKEN": "aaa", "GH_TOKEN": "bbb"}, "Bearer aaa"),
    ],
)
def test_the_token_comes_from_the_environment(
    capsys: pytest.CaptureFixture[str], environ: dict[str, str], expected: str
) -> None:
    _, _, _, transport = run(capsys, routes(), environ=environ)
    assert [headers["Authorization"] for _, headers in transport.calls] == [expected] * 3


def test_without_a_token_the_requests_are_anonymous(capsys: pytest.CaptureFixture[str]) -> None:
    _, _, _, transport = run(capsys, routes())
    assert all("Authorization" not in headers for _, headers in transport.calls)


def test_an_unusable_token_is_an_error_and_is_not_echoed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, out, err, transport = run(capsys, routes(), environ={"GITHUB_TOKEN": "abc def"})
    assert status == EXIT_FAILURE
    assert "abc def" not in out + err
    assert transport.calls == []


def test_control_characters_never_reach_the_terminal(capsys: pytest.CaptureFixture[str]) -> None:
    status, out, err, _ = run(capsys, routes(config=b'"\\u001b[31mred" = 1\n'))
    assert status == EXIT_OK
    assert "\x1b" not in out + err
    assert "pandagate: note: unknown key: ?[31mred" in err.splitlines()


def test_no_line_of_output_can_pass_for_a_runner_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = pr_payload(title="::error::injected")
    files = [file_entry("::warning::x/alpha/engine.py")]
    table = routes(payload, files, config=b'"::error::boom" = 1\n')
    _, out, err, _ = run(capsys, table)
    assert out
    assert err
    assert not any(line.startswith("::") for line in out.splitlines())
    assert all(line.startswith("pandagate: ") for line in err.splitlines())


def test_a_missing_command_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as caught:
        main([])
    assert caught.value.code == 2


def test_the_version_is_printed(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--version"])
    assert caught.value.code == 0
    assert capsys.readouterr().out.strip() == f"pandagate {__version__}"


def test_the_package_runs_as_a_module() -> None:
    command = [sys.executable, "-m", "pandagate", "--version"]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    assert done.returncode == 0
    assert done.stdout.strip() == f"pandagate {__version__}"
