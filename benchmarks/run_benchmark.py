"""Score the frozen sample with the shipped rules and write results.json.

Run from the repository root:

    python -m benchmarks.run_benchmark

Answers of the API are kept in benchmarks/.cache, so a second run sends no
requests. The run refuses to start when src has uncommitted changes: the
numbers have to belong to a commit.
"""

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.metrics import format_summary, summarise
from benchmarks.pick_sample import SAMPLE_PATH
from pandagate.cli import TOKEN_VARIABLES
from pandagate.config import Config
from pandagate.facts import PullRequestFacts, facts_from_api
from pandagate.github import (
    Client,
    GitHubError,
    Response,
    Transport,
    parse_pull_request_url,
    urllib_transport,
)
from pandagate.score import Report, score

RESULTS_PATH = SAMPLE_PATH.with_name("results.json")
CACHE_DIR = SAMPLE_PATH.with_name(".cache")
ROOT = SAMPLE_PATH.parent.parent

PROGRESS_EVERY = 20


class RunError(RuntimeError):
    """The run could not be carried out the way the protocol requires."""


class CachedTransport:
    """Keeps every successful GET on disk and answers from there the next time."""

    def __init__(self, directory: Path, transport: Transport = urllib_transport) -> None:
        self._directory = directory
        self._transport = transport
        self.hits = 0
        self.misses = 0

    def __call__(
        self,
        url: str,
        headers: Mapping[str, str],
        method: str = "GET",
        body: bytes | None = None,
    ) -> Response:
        if method != "GET":
            return self._transport(url, headers, method, body)
        stored = self._directory / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
        if stored.is_file():
            self.hits += 1
            return Response(200, stored.read_bytes())
        self.misses += 1
        response = self._transport(url, headers, method, body)
        if response.status == 200:
            self._directory.mkdir(parents=True, exist_ok=True)
            stored.write_bytes(response.body)
        return response


def _git(*arguments: str) -> str:
    try:
        done = subprocess.run(
            ["git", *arguments], cwd=ROOT, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RunError(f"git {arguments[0]} failed: {type(exc).__name__}") from exc
    return done.stdout.strip()


def current_commit() -> str:
    """The commit being measured. Uncommitted changes in src are refused."""
    if _git("status", "--porcelain", "--", "src"):
        raise RunError("src has uncommitted changes; commit them before measuring")
    return _git("rev-parse", "HEAD")


def default_judge(facts: PullRequestFacts) -> Report:
    """Every shipped rule under the default configuration."""
    return score(facts, Config())


def evaluate(
    client: Client,
    item: Mapping[str, Any],
    judge: Callable[[PullRequestFacts], Report],
) -> dict[str, Any]:
    """Outcomes of every rule for one pull request of the sample."""
    url = str(item["url"])
    ref = parse_pull_request_url(url)
    pull = client.pull_request(ref)
    files, truncated = client.changed_files(ref)
    report = judge(facts_from_api(pull, files, files_truncated=truncated))
    if not report.signals:
        raise RunError(f"{url}: no rule reported anything")
    return {
        "repository": str(item["repository"]),
        "url": url,
        "signals": [
            {"rule_id": signal.rule_id, "outcome": signal.outcome.name, "detail": signal.detail}
            for signal in report.signals
        ],
        "warnings": list(report.warnings),
    }


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
    sample_path: Path = SAMPLE_PATH,
    results_path: Path = RESULTS_PATH,
    cache_dir: Path = CACHE_DIR,
    commit: Callable[[], str] = current_commit,
    judge: Callable[[PullRequestFacts], Report] = default_judge,
) -> int:
    env = os.environ if environ is None else environ
    cached = CachedTransport(cache_dir, transport)
    pulls: list[dict[str, Any]] = []
    try:
        sample = json.loads(sample_path.read_text(encoding="utf-8"))
        items = sample["pull_requests"]
        taken_at = sample["taken_at"]
        revision = commit()
        client = Client(_token(env), cached)
        for position, item in enumerate(items, start=1):
            pulls.append(evaluate(client, item, judge))
            if position % PROGRESS_EVERY == 0:
                _say(f"{position}/{len(items)}")
    except (OSError, ValueError, KeyError, TypeError, GitHubError, RunError) as exc:
        _say(f"error: {type(exc).__name__}: {exc}")
        return 1

    summary = summarise(pulls)
    document = {
        "pandagate_commit": revision,
        "sample_taken_at": taken_at,
        "run_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": summary,
        "pull_requests": pulls,
    }
    results_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(format_summary(summary))
    _say(f"requests: {cached.misses} sent, {cached.hits} answered from the cache")
    return 0


if __name__ == "__main__":
    sys.exit(main())
