"""Take the benchmark sample and freeze it in sample.json.

Run from the repository root with a token in GITHUB_TOKEN or GH_TOKEN:

    python -m benchmarks.pick_sample

The file is written once. An existing sample is never replaced, because the
protocol fixes the sample before any rule is measured against it.
"""

import json
import os
import sys
import urllib.parse
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.sampling import CUTOFF, REPOSITORIES, RESERVE, Selection, entry, select
from pandagate import __version__
from pandagate.cli import TOKEN_VARIABLES
from pandagate.github import (
    API_ROOT,
    API_VERSION,
    PER_PAGE,
    Client,
    GitHubError,
    Transport,
    urllib_transport,
)

#: Pages of closed pull requests read from one repository before giving up.
MAX_PAGES = 100

SAMPLE_PATH = Path(__file__).resolve().parent / "sample.json"


class SampleError(RuntimeError):
    """The sample could not be assembled under the protocol."""


def closed_pulls(
    repository: str,
    token: str | None,
    transport: Transport = urllib_transport,
) -> Iterator[Mapping[str, Any]]:
    """Closed pull requests of one repository, newest first.

    A page is requested only when the caller reads that far.
    """
    what = f"pull requests of {repository}"
    owner, _, name = repository.partition("/")
    owner = urllib.parse.quote(owner, safe="")
    name = urllib.parse.quote(name, safe="")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": f"pandagate/{__version__}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for page in range(1, MAX_PAGES + 1):
        query = urllib.parse.urlencode(
            {
                "state": "closed",
                "sort": "created",
                "direction": "desc",
                "per_page": str(PER_PAGE),
                "page": str(page),
            }
        )
        response = transport(f"{API_ROOT}/repos/{owner}/{name}/pulls?{query}", headers)
        if response.status != 200:
            raise GitHubError(f"{what}: GitHub answered {response.status}")
        try:
            batch = json.loads(response.body)
        except (ValueError, RecursionError):
            raise GitHubError(f"{what}: the response was not valid JSON") from None
        if not isinstance(batch, list):
            raise GitHubError(f"{what}: the response was not a list")
        yield from (item for item in batch if isinstance(item, dict))
        if len(batch) < PER_PAGE:
            return
    raise GitHubError(f"{what}: more than {MAX_PAGES} pages were needed")


def assemble(
    read: Callable[[str], Selection],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the sample, replacing a repository that falls short with the reserve.

    Returns the sample and a record of every repository that was read,
    including the ones that were replaced.
    """
    reserve = list(RESERVE)
    sample: list[dict[str, Any]] = []
    visited: list[dict[str, Any]] = []
    for repository in REPOSITORIES:
        candidate = repository
        while True:
            selection = read(candidate)
            visited.append(
                {
                    "repository": candidate,
                    "scanned": selection.scanned,
                    "picked": len(selection.picked),
                }
            )
            if selection.complete:
                sample.extend(entry(candidate, pull) for pull in selection.picked)
                break
            if not reserve:
                raise SampleError(f"{candidate} fell short and the reserve is used up")
            candidate = reserve.pop(0)
    return sample, visited


def _token(environ: Mapping[str, str]) -> str | None:
    for name in TOKEN_VARIABLES:
        value = environ.get(name, "").strip()
        if value:
            return value
    return None


def _say(text: str) -> None:
    print(text, file=sys.stderr)


def main(
    *,
    environ: Mapping[str, str] | None = None,
    transport: Transport = urllib_transport,
    path: Path = SAMPLE_PATH,
) -> int:
    env = os.environ if environ is None else environ
    token = _token(env)
    if token is None:
        _say("error: a token is needed in GITHUB_TOKEN or GH_TOKEN")
        return 1
    if path.exists():
        _say(f"error: {path.name} already exists; the sample is taken once")
        return 1

    def read(repository: str) -> Selection:
        selection = select(closed_pulls(repository, token, transport))
        _say(f"{repository}: picked {len(selection.picked)}, scanned {selection.scanned}")
        return selection

    try:
        # Constructing a client checks that the token can be sent in a header.
        Client(token, transport)
        sample, visited = assemble(read)
    except (GitHubError, SampleError) as exc:
        _say(f"error: {exc}")
        return 1

    document = {
        "cutoff": CUTOFF,
        "taken_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repositories": visited,
        "pull_requests": sample,
    }
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    _say(f"wrote {len(sample)} pull requests to {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
