"""Reading one pull request from the GitHub REST API.

Everything here is a read. The token is sent to one host only, and a
redirect is refused instead of followed: following it would hand the
token to wherever the redirect points.

Every response is untrusted. A body of an unexpected shape is an error
or, for the file list, a reason to report the list as incomplete. It is
never a reason to guess.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pandagate import __version__
from pandagate.config import CONFIG_FILENAME, MAX_CONFIG_BYTES, Config, ConfigError, parse_config
from pandagate.facts import PullRequestFacts, facts_from_api

API_ROOT = "https://api.github.com"
WEB_HOST = "github.com"
API_VERSION = "2022-11-28"

PER_PAGE = 100

#: The files endpoint lists at most 3000 files, which is this many pages.
MAX_FILE_PAGES = 30

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
TIMEOUT_SECONDS = 20

_JSON = "application/vnd.github+json"
_RAW = "application/vnd.github.raw+json"

_OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}")
_REPOSITORY = re.compile(r"[A-Za-z0-9._-]{1,100}")
_NUMBER = re.compile(r"[1-9][0-9]{0,9}")
_TOKEN = re.compile(r"[\x21-\x7e]+")

_HINTS = {
    401: "the token was not accepted",
    403: "access was refused, or the rate limit was reached",
    404: "not found, or not visible with this token",
    429: "the rate limit was reached",
}


class GitHubError(RuntimeError):
    """The pull request could not be read."""


@dataclass(frozen=True, slots=True)
class Response:
    """The part of an HTTP response this module reads."""

    status: int
    body: bytes


Transport = Callable[[str, Mapping[str, str]], Response]


@dataclass(frozen=True, slots=True)
class PullRequestRef:
    """Which pull request, in which repository."""

    owner: str
    repo: str
    number: int

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_pull_request_url(url: str) -> PullRequestRef:
    """Read owner, repository and number out of a pull request URL.

    Only https://github.com is accepted, with no port and no user
    information, so that a look-alike URL cannot pass for the real host.
    """
    try:
        parts = urllib.parse.urlsplit(url.strip())
        host, port = parts.hostname, parts.port
    except ValueError:
        raise GitHubError("not a pull request URL") from None

    on_host = parts.scheme == "https" and host == WEB_HOST and port is None
    if not on_host or parts.username is not None or parts.password is not None:
        raise GitHubError(f"expected a pull request URL on https://{WEB_HOST}")

    segments = parts.path.split("/")
    if len(segments) < 5 or segments[3] != "pull":
        raise GitHubError("expected a URL ending in <owner>/<repository>/pull/<number>")

    owner, repository, number = segments[1], segments[2], segments[4]
    named = _OWNER.fullmatch(owner) and _REPOSITORY.fullmatch(repository)
    if not named or repository in {".", ".."} or not _NUMBER.fullmatch(number):
        raise GitHubError("expected a URL ending in <owner>/<repository>/pull/<number>")

    return PullRequestRef(owner, repository, int(number))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Turns every redirect into an error instead of a second request."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _read_limited(reply: Any) -> bytes:
    data = reply.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise GitHubError(f"a response was larger than {MAX_RESPONSE_BYTES} bytes")
    return data


def urllib_transport(url: str, headers: Mapping[str, str]) -> Response:
    """Send one GET request with the standard library."""
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with _OPENER.open(request, timeout=TIMEOUT_SECONDS) as reply:
            return Response(reply.status, _read_limited(reply))
    except urllib.error.HTTPError as exc:
        exc.close()
        return Response(exc.code, b"")
    except OSError as exc:
        raise GitHubError(f"could not reach {API_ROOT}: {type(exc).__name__}") from exc


def _expect_ok(response: Response, what: str) -> None:
    if response.status == 200:
        return
    if 300 <= response.status < 400:
        hint = "redirects are not followed; the repository may have been renamed"
    else:
        hint = _HINTS.get(response.status, "")
    suffix = f" ({hint})" if hint else ""
    raise GitHubError(f"{what}: GitHub answered {response.status}{suffix}")


def _json(response: Response, what: str) -> Any:
    try:
        return json.loads(response.body)
    except (ValueError, RecursionError):
        raise GitHubError(f"{what}: the response was not valid JSON") from None


def _repository_path(ref: PullRequestRef) -> str:
    owner = urllib.parse.quote(ref.owner, safe="")
    repo = urllib.parse.quote(ref.repo, safe="")
    return f"/repos/{owner}/{repo}"


class Client:
    """Read-only access to one host of the GitHub REST API."""

    def __init__(self, token: str | None = None, transport: Transport = urllib_transport) -> None:
        if token and not _TOKEN.fullmatch(token):
            raise GitHubError("the token contains characters that cannot be sent in a header")
        self._token = token or None
        self._transport = transport

    def _get(
        self,
        path: str,
        query: Mapping[str, str] | None = None,
        accept: str = _JSON,
    ) -> Response:
        url = API_ROOT + path
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        headers = {
            "Accept": accept,
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": f"pandagate/{__version__}",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return self._transport(url, headers)

    def pull_request(self, ref: PullRequestRef) -> Mapping[str, Any]:
        """The pull request object as the API reports it."""
        what = f"pull request {ref.slug}#{ref.number}"
        response = self._get(f"{_repository_path(ref)}/pulls/{ref.number}")
        _expect_ok(response, what)
        payload = _json(response, what)
        if not isinstance(payload, dict):
            raise GitHubError(f"{what}: the response was not an object")
        return payload

    def changed_files(self, ref: PullRequestRef) -> tuple[list[Mapping[str, Any]], bool]:
        """The changed files, and whether the list is known to be incomplete."""
        what = f"files of {ref.slug}#{ref.number}"
        path = f"{_repository_path(ref)}/pulls/{ref.number}/files"
        entries: list[Mapping[str, Any]] = []
        incomplete = False
        for page in range(1, MAX_FILE_PAGES + 1):
            response = self._get(path, {"per_page": str(PER_PAGE), "page": str(page)})
            _expect_ok(response, what)
            batch = _json(response, what)
            if not isinstance(batch, list):
                raise GitHubError(f"{what}: the response was not a list")
            kept = [entry for entry in batch if isinstance(entry, dict)]
            incomplete = incomplete or len(kept) != len(batch)
            entries.extend(kept)
            if len(batch) < PER_PAGE:
                return entries, incomplete
        return entries, True

    def config(self, ref: PullRequestRef, base_ref: str) -> Config:
        """The configuration on the base branch, or the defaults when it has none.

        The file is read from the repository the pull request targets,
        at the branch it targets. Nothing is read from the head of the
        pull request.
        """
        what = f"{CONFIG_FILENAME} of {ref.slug}"
        path = f"{_repository_path(ref)}/contents/{CONFIG_FILENAME}"
        response = self._get(path, {"ref": base_ref}, accept=_RAW)
        if response.status == 404:
            return Config()
        _expect_ok(response, what)
        if len(response.body) > MAX_CONFIG_BYTES:
            raise ConfigError(f"{CONFIG_FILENAME}: larger than {MAX_CONFIG_BYTES} bytes")
        try:
            text = response.body.decode("utf-8")
        except UnicodeDecodeError:
            raise ConfigError(f"{CONFIG_FILENAME}: not valid UTF-8") from None
        return parse_config(text)


def _base_ref(payload: Mapping[str, Any]) -> str:
    base = payload.get("base")
    name = base.get("ref") if isinstance(base, Mapping) else None
    if not isinstance(name, str) or not name:
        raise GitHubError("the pull request names no base branch")
    return name


def load_pull_request(client: Client, ref: PullRequestRef) -> tuple[PullRequestFacts, Config]:
    """Read everything one run needs: the facts and the base branch configuration."""
    payload = client.pull_request(ref)
    config = client.config(ref, _base_ref(payload))
    files, incomplete = client.changed_files(ref)
    expected = payload.get("changed_files")
    if isinstance(expected, int) and not isinstance(expected, bool) and expected > len(files):
        incomplete = True
    return facts_from_api(payload, files, files_truncated=incomplete), config
