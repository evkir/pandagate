"""Labelling sheet for metric C: hints, the Development query, the files it writes."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from benchmarks.build_sheet import (
    DEVELOPMENT_NAME,
    DRAFT_HEADER,
    DRAFT_NAME,
    MAX_BODY_CHARS,
    RESULTS_PATH,
    SHEET_NAME,
    SheetError,
    absent_signals,
    build,
    describe_file,
    development_query,
    draft_line,
    fetch_development,
    find_hints,
    load_development,
    main,
    offline,
    path_hints,
    pull_slug,
    read_development,
    render_entry,
    scan_patch,
)
from benchmarks.labels import absent_keys
from benchmarks.run_benchmark import CachedTransport
from pandagate.github import API_ROOT, Client, Response, parse_pull_request_url

FIRST = "https://github.com/octo/demo/pull/1"
SECOND = "https://github.com/octo/demo/pull/2"
PATCH = "@@ -1,3 +1,8 @@ mod tests {\n context\n+    #[test]\n+    fn parses() {}\n-old"


def _pull(number: int, title: str, body: str | None) -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "body": body,
        "author_association": "CONTRIBUTOR",
        "user": {"login": "mona"},
        "base": {"ref": "main", "repo": {"full_name": "octo/demo"}},
    }


PULLS = {
    1: _pull(1, "Speed up the parser", "Follow-up to octo/other#7.\n\nSecond line."),
    2: _pull(2, "Add a runner", None),
}
FILES = {
    1: [
        {
            "filename": "src/parser.rs",
            "status": "modified",
            "additions": 6,
            "deletions": 1,
            "patch": PATCH,
        },
        {
            "filename": "crates/demo/resources/mdtest/case.md",
            "status": "added",
            "additions": 3,
            "deletions": 0,
        },
    ],
    2: [
        {
            "filename": "lib/run.py",
            "status": "modified",
            "additions": 9,
            "deletions": 0,
            "patch": "@@ -1 +1,9 @@\n+value = 1",
        }
    ],
}
GRAPHQL = {
    "data": {
        "p0": {
            "pullRequest": {
                "all": {"nodes": [{"number": 7, "repository": {"nameWithOwner": "octo/other"}}]},
                "manual": {"nodes": []},
            }
        }
    }
}
LINKED = {FIRST: {"all": ["octo/other#7"], "manual": []}}


def _signal(rule_id: str, outcome: str) -> dict[str, str]:
    return {"rule_id": rule_id, "outcome": outcome, "detail": f"{rule_id} observed"}


def _results() -> dict[str, Any]:
    return {
        "pandagate_commit": "796b735c3b387874fe8e40ec7da0f1f17cc77003",
        "pull_requests": [
            {"url": FIRST, "signals": [_signal("R1", "ABSENT"), _signal("R2", "ABSENT")]},
            {"url": SECOND, "signals": [_signal("R1", "PRESENT"), _signal("R2", "ABSENT")]},
        ],
    }


class _GitHub:
    """Answers like the API for the two pull requests above and records every POST."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.posts: list[tuple[str, Mapping[str, str], bytes | None]] = []

    def __call__(
        self,
        url: str,
        headers: Mapping[str, str],
        method: str = "GET",
        body: bytes | None = None,
    ) -> Response:
        if method == "POST":
            self.posts.append((url, headers, body))
            return Response(self.status, json.dumps(GRAPHQL).encode())
        number = 1 if "/pulls/1" in url else 2
        payload = FILES[number] if "/files" in url else PULLS[number]
        return Response(200, json.dumps(payload).encode())


def _forbidden(
    url: str,
    headers: Mapping[str, str],
    method: str = "GET",
    body: bytes | None = None,
) -> Response:
    raise AssertionError(f"no request expected, got {method} {url}")


def _warm(directory: Path) -> None:
    client = Client(None, CachedTransport(directory, _GitHub()))
    for url in (FIRST, SECOND):
        ref = parse_pull_request_url(url)
        client.pull_request(ref)
        client.changed_files(ref)


def _prepare(tmp_path: Path) -> tuple[Path, Path]:
    directory = tmp_path / "cache"
    _warm(directory)
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(_results()), encoding="utf-8")
    return directory, results_path


def test_offline_transport_refuses_every_request() -> None:
    with pytest.raises(SheetError, match="not in the cache"):
        offline(f"{API_ROOT}/rate_limit", {})


def test_pull_slug() -> None:
    assert pull_slug(FIRST) == "octo/demo#1"


def test_absent_signals_carry_the_detail_in_order() -> None:
    assert absent_signals(_results()) == [
        ((FIRST, "R1"), "R1 observed"),
        ((FIRST, "R2"), "R2 observed"),
        ((SECOND, "R2"), "R2 observed"),
    ]


def test_absent_signals_of_the_baseline_match_the_label_keys() -> None:
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    assert [key for key, _ in absent_signals(results)] == absent_keys(results)


def test_hints_find_references_to_any_repository() -> None:
    text = (
        "Fixes #12, see astral-sh/ty#4629 and GH-7.\n"
        "https://github.com/octo/demo/issues/3#issuecomment-9 again #12"
    )
    assert find_hints(text) == (
        "#12",
        "astral-sh/ty#4629",
        "GH-7",
        "https://github.com/octo/demo/issues/3",
    )


def test_hints_find_nothing_in_plain_text() -> None:
    assert find_hints("Speed up the parser by 12 percent") == ()


def test_scan_separates_changed_lines_from_context() -> None:
    patch = "@@ -1,2 +1,4 @@ mod tests {\n     #[test]\n+    #[tokio::test]\n-    #[test]\n same"
    scan = scan_patch(patch)
    assert scan.changed == {"#[test]": 2}
    assert scan.nearby == {"#[test]": 1, "mod tests": 1}
    assert scan.headings == ("mod tests {",)


def test_scan_reads_javascript_tests_and_skips_method_calls() -> None:
    patch = (
        "@@ -1 +1,3 @@\n"
        "+it('works', () => {})\n"
        "+describe.each(rows)('x', fn)\n"
        "+if (pattern.test(value)) {}"
    )
    scan = scan_patch(patch)
    assert scan.changed == {"it/describe/test(": 2}
    assert scan.nearby == {}
    assert scan.headings == ()


def test_scan_reads_python_go_and_cpp_tests() -> None:
    patch = '+def test_parse():\n+func TestRun(t *testing.T) {\n+TEST_CASE("[Node] Tree") {'
    assert scan_patch(patch).changed == {"def test_": 1, "func Test": 1, "TEST_CASE": 1}


@pytest.mark.parametrize(
    ("path", "hints"),
    [
        ("testing/python/fixtures.py", ("testing",)),
        ("crates/ty/resources/mdtest/snapshots/a.snap", ("mdtest", "snapshots", ".snap")),
        ("src/main.rs", ()),
    ],
)
def test_path_hints(path: str, hints: tuple[str, ...]) -> None:
    assert path_hints(path) == hints


def test_describe_file_shows_markers_and_hunks_of_logic() -> None:
    assert describe_file(FILES[1][0]) == [
        "- logic +6 -1 src/parser.rs",
        "    test markers on changed lines: #[test] x1",
        "    test markers in context: mod tests x1",
        "    hunks: mod tests {",
    ]


def test_describe_file_without_a_patch() -> None:
    assert describe_file(FILES[1][1]) == [
        "- test  +3 -0 crates/demo/resources/mdtest/case.md (added)",
        "    path hint: mdtest",
        "    no patch in the API response",
    ]


def test_entry_for_r1_shows_references_development_and_description() -> None:
    entry = render_entry(1, (FIRST, "R1"), "R1 observed", PULLS[1], FILES[1], LINKED)
    assert entry.splitlines() == [
        "=== 001 R1 octo/demo#1 ===",
        FIRST,
        "title: Speed up the parser",
        "author: mona (CONTRIBUTOR)",
        "signal: R1 observed",
        "references in the title and description: octo/other#7",
        "Development: octo/other#7; linked by hand: none",
        "description:",
        "    | Follow-up to octo/other#7.",
        "    | ",
        "    | Second line.",
    ]


def test_entry_for_r1_without_description_or_development() -> None:
    entry = render_entry(4, (SECOND, "R1"), "R1 observed", PULLS[2], FILES[2], {})
    assert entry.splitlines()[5:] == [
        "references in the title and description: none",
        "Development: not fetched",
        "description: empty",
    ]


def test_entry_cuts_a_long_description() -> None:
    pull = _pull(1, "Long", "x" * (MAX_BODY_CHARS + 500))
    entry = render_entry(1, (FIRST, "R1"), "R1 observed", pull, [], LINKED)
    assert (
        entry.splitlines()[-1]
        == f"    [cut at {MAX_BODY_CHARS} of {MAX_BODY_CHARS + 500} characters]"
    )


def test_entry_for_r2_lists_kinds_and_files() -> None:
    entry = render_entry(2, (FIRST, "R2"), "R2 observed", PULLS[1], FILES[1], {})
    lines = entry.splitlines()
    assert lines[0] == "=== 002 R2 octo/demo#1 ==="
    assert lines[5:8] == ["kinds: logic x1, test x1", "files:", "- logic +6 -1 src/parser.rs"]
    assert "description:" not in lines


def test_draft_line_waits_for_a_verdict() -> None:
    assert draft_line(17, (SECOND, "R2")) == "017 R2 octo/demo#2 ="


def test_build_numbers_signals_and_reads_only_the_cache(tmp_path: Path) -> None:
    _warm(tmp_path)
    client = Client(None, CachedTransport(tmp_path, _forbidden))
    sheet, draft = build(_results(), client, LINKED)
    headings = [line for line in sheet.splitlines() if line.startswith("=== ")]
    assert headings == [
        "=== 001 R1 octo/demo#1 ===",
        "=== 002 R2 octo/demo#1 ===",
        "=== 003 R2 octo/demo#2 ===",
    ]
    assert draft.splitlines() == [
        *DRAFT_HEADER,
        "001 R1 octo/demo#1 =",
        "002 R2 octo/demo#1 =",
        "003 R2 octo/demo#2 =",
    ]


def test_development_query_asks_for_every_pull_request_once() -> None:
    query = development_query([FIRST, SECOND])
    assert query.startswith('query { p0: repository(owner: "octo", name: "demo")')
    assert "pullRequest(number: 1)" in query
    assert 'p1: repository(owner: "octo", name: "demo") { pullRequest(number: 2)' in query
    assert query.count("userLinkedOnly: true") == 2
    assert query.count("{") == query.count("}")


def test_read_development() -> None:
    assert read_development(GRAPHQL, [FIRST]) == LINKED


@pytest.mark.parametrize(
    "payload",
    [[], {}, {"data": None}, {**GRAPHQL, "errors": [{"message": "x"}]}, {"data": {"p0": None}}],
)
def test_read_development_refuses_a_broken_answer(payload: Any) -> None:
    with pytest.raises(SheetError):
        read_development(payload, [FIRST])


def test_fetch_development_makes_one_authorised_post() -> None:
    github = _GitHub()
    assert fetch_development([FIRST], "t0ken", github) == LINKED
    assert len(github.posts) == 1
    url, headers, body = github.posts[0]
    assert url == f"{API_ROOT}/graphql"
    assert headers["Authorization"] == "Bearer t0ken"
    assert json.loads(body or b"")["query"] == development_query([FIRST])


def test_fetch_development_refuses_a_failed_request() -> None:
    with pytest.raises(SheetError, match="status 502"):
        fetch_development([FIRST], "t0ken", _GitHub(status=502))


def test_load_development_fetches_once_and_then_reads_the_file(tmp_path: Path) -> None:
    path = tmp_path / "cache" / DEVELOPMENT_NAME
    github = _GitHub()
    assert load_development(path, [FIRST], "t0ken", github) == LINKED
    assert load_development(path, [FIRST], None, _forbidden) == LINKED
    assert len(github.posts) == 1


def test_load_development_needs_a_token_for_the_query(tmp_path: Path) -> None:
    with pytest.raises(SheetError, match="GH_TOKEN"):
        load_development(tmp_path / DEVELOPMENT_NAME, [FIRST], None, _forbidden)


def test_load_development_asks_nothing_for_an_empty_list(tmp_path: Path) -> None:
    assert load_development(tmp_path / DEVELOPMENT_NAME, [], None, _forbidden) == {}


def test_main_writes_the_sheet_the_draft_and_the_development_cache(tmp_path: Path) -> None:
    directory, results_path = _prepare(tmp_path)
    github = _GitHub()
    code = main(
        environ={"GH_TOKEN": "t0ken"},
        transport=github,
        directory=directory,
        results_path=results_path,
    )
    assert code == 0
    assert len(github.posts) == 1
    sheet = (directory / SHEET_NAME).read_text(encoding="utf-8")
    assert "Development: octo/other#7; linked by hand: none" in sheet
    assert (directory / DRAFT_NAME).read_text(encoding="utf-8").endswith("003 R2 octo/demo#2 =\n")
    assert json.loads((directory / DEVELOPMENT_NAME).read_text(encoding="utf-8")) == LINKED


def test_main_leaves_an_existing_draft_alone(tmp_path: Path) -> None:
    directory, results_path = _prepare(tmp_path)
    main(
        environ={"GH_TOKEN": "t0ken"},
        transport=_GitHub(),
        directory=directory,
        results_path=results_path,
    )
    (directory / DRAFT_NAME).write_text("001 R1 octo/demo#1 = correct checked\n", encoding="utf-8")
    (directory / SHEET_NAME).unlink()
    code = main(environ={}, transport=_forbidden, directory=directory, results_path=results_path)
    assert code == 0
    assert (directory / SHEET_NAME).is_file()
    draft = (directory / DRAFT_NAME).read_text(encoding="utf-8")
    assert draft == "001 R1 octo/demo#1 = correct checked\n"


def test_main_fails_without_a_token_or_a_development_cache(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory, results_path = _prepare(tmp_path)
    code = main(environ={}, transport=_forbidden, directory=directory, results_path=results_path)
    assert code == 1
    assert "GH_TOKEN" in capsys.readouterr().err
    assert not (directory / SHEET_NAME).exists()


def test_main_fails_when_a_pull_request_is_not_in_the_cache(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(_results()), encoding="utf-8")
    code = main(
        environ={"GH_TOKEN": "t0ken"},
        transport=_GitHub(),
        directory=tmp_path / "cache",
        results_path=results_path,
    )
    assert code == 1
    assert "not in the cache" in capsys.readouterr().err
