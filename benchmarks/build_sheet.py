"""Labelling sheet for metric C.

Builds, out of results.json and the cache of the run, a sheet with what a
person needs to check every ABSENT signal by hand, and a draft to write the
verdicts into. Pull requests and their files come from the cache only. The
one request it makes is a single GraphQL query for the issues linked in the
Development sidebar, and the answer to it is cached as well.

The hints on the sheet are wider than the rules on purpose: they point at
what to look at, and the verdict stays with the person.
"""

import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from benchmarks.labels import Key
from benchmarks.run_benchmark import CachedTransport
from pandagate import __version__
from pandagate.facts import facts_from_api
from pandagate.github import (
    API_ROOT,
    Client,
    GitHubError,
    Response,
    Transport,
    parse_pull_request_url,
    urllib_transport,
)
from pandagate.paths import PathKind, classify

RESULTS_PATH = Path(__file__).with_name("results.json")
CACHE_DIRECTORY = Path(__file__).with_name(".cache")
SHEET_NAME = "sheet.txt"
DRAFT_NAME = "draft.txt"
DEVELOPMENT_NAME = "development.json"
MAX_BODY_CHARS = 1500
MAX_FILES = 40
MAX_HEADINGS = 6
MAX_HEADING_CHARS = 80
DRAFT_HEADER = (
    "# One line per ABSENT signal. After '=' write the verdict and the reason:",
    "#   correct <reason>     or     wrong <reason>",
    "# Lines left empty after '=' are skipped when the draft is applied.",
)

_TOKEN_VARIABLES = ("GITHUB_TOKEN", "GH_TOKEN")
_REFERENCE = re.compile(
    r"https?://github\.com/[\w.-]+/[\w.-]+/(?:issues|pull)/\d+"
    r"|(?:[\w.-]+/[\w.-]+)?#\d+\b"
    r"|\bGH-\d+\b",
    re.IGNORECASE,
)
_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("#[test]", re.compile(r"#\[(?:\w+::)*test\b")),
    ("#[cfg(test)]", re.compile(r"#\[cfg\(test\)\]")),
    ("mod tests", re.compile(r"\bmod tests?\b")),
    ("def test_", re.compile(r"\bdef test_")),
    ("func Test", re.compile(r"\bfunc Test")),
    ("it/describe/test(", re.compile(r"(?<![.\w])(?:it|describe|test)(?:\.\w+)?\(")),
    ("TEST_CASE", re.compile(r"\bTEST_CASE\b|\bTEST(?:_F|_P)?\(")),
)
_HUNK = re.compile(r"@@ [^@]* @@ ?(.*)")
_HINT_DIRECTORIES = frozenset({"snapshots", "__snapshots__", "fixtures", "e2e", "benches"})
_NODES = "nodes { number repository { nameWithOwner } }"
_LINKS = (
    f"all: closingIssuesReferences(first: 10) {{ {_NODES} }} "
    f"manual: closingIssuesReferences(first: 10, userLinkedOnly: true) {{ {_NODES} }}"
)

Development = Mapping[str, Mapping[str, Sequence[str]]]


class SheetError(RuntimeError):
    """The sheet cannot be built from what is on disk."""


@dataclass(frozen=True)
class PatchScan:
    """Test markers of one patch: on changed lines, around them, and hunk headings."""

    changed: Mapping[str, int]
    nearby: Mapping[str, int]
    headings: tuple[str, ...]


def offline(
    url: str,
    headers: Mapping[str, str],
    method: str = "GET",
    body: bytes | None = None,
) -> Response:
    """A transport for work that must not touch the network."""
    raise SheetError(f"not in the cache: {method} {url}")


def pull_slug(url: str) -> str:
    """owner/repository#number of a pull request URL."""
    ref = parse_pull_request_url(url)
    return f"{ref.slug}#{ref.number}"


def absent_signals(results: Mapping[str, Any]) -> list[tuple[Key, str]]:
    """Every ABSENT signal of a run with its detail, in the order of the results."""
    return [
        ((str(pull["url"]), str(signal["rule_id"])), str(signal["detail"]))
        for pull in results["pull_requests"]
        for signal in pull["signals"]
        if signal["outcome"] == "ABSENT"
    ]


def find_hints(text: str) -> tuple[str, ...]:
    """Everything in a text that looks like a reference to an issue, in any repository."""
    return tuple(dict.fromkeys(match.group(0) for match in _REFERENCE.finditer(text)))


def scan_patch(patch: str) -> PatchScan:
    """Count test markers on the changed lines of a patch and around them."""
    changed: dict[str, int] = {}
    nearby: dict[str, int] = {}
    headings: dict[str, None] = {}
    for line in patch.splitlines():
        hunk = _HUNK.match(line)
        if hunk:
            text = hunk.group(1).strip()
            if text:
                headings[text] = None
            target = nearby
        elif line.startswith(("+", "-")):
            target, text = changed, line[1:]
        else:
            target, text = nearby, line
        for name, pattern in _MARKERS:
            count = len(pattern.findall(text))
            if count:
                target[name] = target.get(name, 0) + count
    return PatchScan(changed, nearby, tuple(headings))


def path_hints(path: str) -> tuple[str, ...]:
    """Parts of a path that suggest test material."""
    hints = [
        part
        for part in PurePosixPath(path).parts
        if "test" in part.lower() or part.lower() in _HINT_DIRECTORIES
    ]
    if path.lower().endswith(".snap"):
        hints.append(".snap")
    return tuple(dict.fromkeys(hints))


def _counts(found: Mapping[str, int]) -> str:
    return ", ".join(f"{name} x{count}" for name, count in found.items())


def describe_file(entry: Mapping[str, Any]) -> list[str]:
    """The lines of the sheet about one changed file."""
    path = str(entry.get("filename", ""))
    kind = classify(path)
    head = f"- {kind.value:<5} +{entry.get('additions', 0)} -{entry.get('deletions', 0)} {path}"
    status = str(entry.get("status", ""))
    if status != "modified":
        head = f"{head} ({status})"
    lines = [head]
    hints = path_hints(path)
    if hints:
        lines.append(f"    path hint: {', '.join(hints)}")
    patch = entry.get("patch")
    if not isinstance(patch, str):
        lines.append("    no patch in the API response")
        return lines
    scan = scan_patch(patch)
    if scan.changed:
        lines.append(f"    test markers on changed lines: {_counts(scan.changed)}")
    if scan.nearby:
        lines.append(f"    test markers in context: {_counts(scan.nearby)}")
    if kind is PathKind.LOGIC and scan.headings:
        shown = [heading[:MAX_HEADING_CHARS] for heading in scan.headings[:MAX_HEADINGS]]
        lines.append(f"    hunks: {' | '.join(shown)}")
    return lines


def _issue_lines(title: str, body: str, linked: Mapping[str, Sequence[str]] | None) -> list[str]:
    hints = find_hints(f"{title}\n{body}")
    lines = [f"references in the title and description: {', '.join(hints) or 'none'}"]
    if linked is None:
        lines.append("Development: not fetched")
    else:
        everything = ", ".join(linked["all"]) or "none"
        by_hand = ", ".join(linked["manual"]) or "none"
        lines.append(f"Development: {everything}; linked by hand: {by_hand}")
    lines.append("description:" if body.strip() else "description: empty")
    lines.extend(f"    | {line}" for line in body[:MAX_BODY_CHARS].splitlines())
    if len(body) > MAX_BODY_CHARS:
        lines.append(f"    [cut at {MAX_BODY_CHARS} of {len(body)} characters]")
    return lines


def _file_lines(files: Sequence[Mapping[str, Any]]) -> list[str]:
    kinds: dict[str, int] = {}
    for entry in files:
        kind = classify(str(entry.get("filename", ""))).value
        kinds[kind] = kinds.get(kind, 0) + 1
    lines = [f"kinds: {_counts(kinds)}", "files:"]
    for entry in files[:MAX_FILES]:
        lines.extend(describe_file(entry))
    if len(files) > MAX_FILES:
        lines.append(f"[{len(files) - MAX_FILES} more file(s) not shown]")
    return lines


def render_entry(
    number: int,
    key: Key,
    detail: str,
    pull: Mapping[str, Any],
    files: Sequence[Mapping[str, Any]],
    development: Development,
) -> str:
    """The block of the sheet about one ABSENT signal."""
    url, rule_id = key
    facts = facts_from_api(pull, files)
    lines = [
        f"=== {number:03d} {rule_id} {pull_slug(url)} ===",
        url,
        f"title: {facts.title}",
        f"author: {facts.author} ({facts.author_association})",
        f"signal: {detail}",
    ]
    if rule_id == "R1":
        lines.extend(_issue_lines(facts.title, facts.body, development.get(url)))
    elif rule_id == "R2":
        lines.extend(_file_lines(files))
    return "\n".join(lines) + "\n"


def draft_line(number: int, key: Key) -> str:
    """The line of the draft that waits for the verdict on one signal."""
    url, rule_id = key
    return f"{number:03d} {rule_id} {pull_slug(url)} ="


def build(results: Mapping[str, Any], client: Client, development: Development) -> tuple[str, str]:
    """The text of the sheet and the text of an empty draft."""
    loaded: dict[str, tuple[Mapping[str, Any], list[Mapping[str, Any]]]] = {}
    blocks: list[str] = []
    draft = list(DRAFT_HEADER)
    for number, (key, detail) in enumerate(absent_signals(results), start=1):
        url = key[0]
        if url not in loaded:
            ref = parse_pull_request_url(url)
            files, _ = client.changed_files(ref)
            loaded[url] = (client.pull_request(ref), files)
        pull, files = loaded[url]
        blocks.append(render_entry(number, key, detail, pull, files, development))
        draft.append(draft_line(number, key))
    return "\n".join(blocks), "".join(f"{line}\n" for line in draft)


def development_query(urls: Sequence[str]) -> str:
    """One GraphQL query for the issues linked to every pull request in the list."""
    parts = []
    for position, url in enumerate(urls):
        ref = parse_pull_request_url(url)
        owner, name = ref.slug.split("/")
        parts.append(
            f"p{position}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) "
            f"{{ pullRequest(number: {ref.number}) {{ {_LINKS} }} }}"
        )
    return "query { " + " ".join(parts) + " }"


def _issues(connection: Mapping[str, Any]) -> list[str]:
    return [
        f"{node['repository']['nameWithOwner']}#{node['number']}" for node in connection["nodes"]
    ]


def read_development(payload: Any, urls: Sequence[str]) -> dict[str, dict[str, list[str]]]:
    """Linked issues per pull request URL out of the answer to development_query."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or payload.get("errors"):
        raise SheetError("the Development query did not come back clean")
    linked: dict[str, dict[str, list[str]]] = {}
    for position, url in enumerate(urls):
        try:
            pull = data[f"p{position}"]["pullRequest"]
            linked[url] = {"all": _issues(pull["all"]), "manual": _issues(pull["manual"])}
        except (KeyError, TypeError):
            raise SheetError(f"the Development query has no answer for {url}") from None
    return linked


def fetch_development(
    urls: Sequence[str], token: str, transport: Transport = urllib_transport
) -> dict[str, dict[str, list[str]]]:
    """Ask GitHub once for the linked issues of every pull request in the list."""
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": f"pandagate/{__version__}",
    }
    body = json.dumps({"query": development_query(urls)}).encode()
    response = transport(f"{API_ROOT}/graphql", headers, "POST", body)
    if response.status != 200:
        raise SheetError(f"the Development query failed with status {response.status}")
    try:
        payload = json.loads(response.body)
    except ValueError:
        raise SheetError("the answer to the Development query is not JSON") from None
    return read_development(payload, urls)


def load_development(
    path: Path, urls: Sequence[str], token: str | None, transport: Transport = urllib_transport
) -> Development:
    """Linked issues from the cache, or from one query that then fills the cache."""
    if path.is_file():
        stored = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(stored, dict) and all(url in stored for url in urls):
            return stored
    if not urls:
        return {}
    if not token:
        raise SheetError("the Development links are not cached: set GH_TOKEN for one query")
    linked = fetch_development(urls, token, transport)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(linked, indent=2) + "\n", encoding="utf-8")
    return linked


def main(
    *,
    environ: Mapping[str, str] | None = None,
    transport: Transport = urllib_transport,
    directory: Path = CACHE_DIRECTORY,
    results_path: Path = RESULTS_PATH,
) -> int:
    """Write the sheet, and the draft unless one is already there."""
    variables = os.environ if environ is None else environ
    token = next((variables[name] for name in _TOKEN_VARIABLES if variables.get(name)), None)
    try:
        results = json.loads(results_path.read_text(encoding="utf-8"))
        signals = absent_signals(results)
        asked = list(dict.fromkeys(url for (url, rule_id), _ in signals if rule_id == "R1"))
        development = load_development(directory / DEVELOPMENT_NAME, asked, token, transport)
        client = Client(None, CachedTransport(directory, offline))
        sheet, draft = build(results, client, development)
    except (SheetError, GitHubError) as error:
        print(f"build_sheet: {error}", file=sys.stderr)
        return 1
    sheet_path = directory / SHEET_NAME
    sheet_path.write_text(sheet, encoding="utf-8")
    print(f"build_sheet: {len(signals)} signal(s) in {sheet_path}")
    draft_path = directory / DRAFT_NAME
    if draft_path.exists():
        print(f"build_sheet: {draft_path} is already there and is left as it is")
    else:
        draft_path.write_text(draft, encoding="utf-8")
        print(f"build_sheet: empty draft in {draft_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
