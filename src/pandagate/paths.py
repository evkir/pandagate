"""Classify a changed path by what kind of file it is.

The classification is by path shape alone - no file contents are read.
It is deliberately conservative: anything unrecognised is OTHER rather
than LOGIC, so a rule that asks for tests does not ask for them over a
binary asset or a lock file.
"""

from enum import StrEnum
from pathlib import PurePosixPath

LOGIC_EXTENSIONS = frozenset(
    {
        ".py",
        ".pyi",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".kts",
        ".scala",
        ".rb",
        ".php",
        ".cs",
        ".swift",
        ".c",
        ".h",
        ".cc",
        ".cpp",
        ".hpp",
        ".m",
        ".mm",
        ".sh",
        ".bash",
        ".zsh",
        ".sql",
        ".pl",
        ".lua",
        ".ex",
        ".exs",
        ".erl",
        ".clj",
        ".hs",
        ".ml",
        ".dart",
    }
)
DOCS_EXTENSIONS = frozenset({".md", ".rst", ".txt", ".adoc", ".org"})
META_EXTENSIONS = frozenset(
    {".toml", ".ini", ".cfg", ".yml", ".yaml", ".json", ".lock", ".editorconfig"}
)

TEST_PATH_MARKERS = frozenset(
    {
        "test",
        "tests",
        "testing",
        "spec",
        "specs",
        "__tests__",
        "testdata",
        "mdtest",
        "snapshots",
        "__snapshots__",
    }
)
DOCS_PATH_MARKERS = frozenset({"doc", "docs", "documentation", "man"})
META_PATH_MARKERS = frozenset({".github", ".gitlab", ".circleci", ".idea", ".vscode"})

DOCS_STEMS = frozenset(
    {
        "readme",
        "license",
        "licence",
        "notice",
        "changelog",
        "changes",
        "contributing",
        "code_of_conduct",
        "security",
        "authors",
        "maintainers",
    }
)
META_FILENAMES = frozenset(
    {
        "dockerfile",
        "makefile",
        "justfile",
        "procfile",
        "setup.py",
        "setup.cfg",
        "manifest.in",
        ".gitignore",
        ".gitattributes",
        ".dockerignore",
        ".pre-commit-config.yaml",
    }
)

_TEST_NAME_PREFIXES = ("test_", "test-", "test.")
_TEST_NAME_INFIXES = ("_test.", "-test.", ".test.", ".spec.", "_spec.")
TEST_EXTENSIONS = frozenset({".snap"})
TEST_SUPPORT_STEMS = frozenset({"testing"})


class PathKind(StrEnum):
    """What a changed path is, as far as its shape can tell."""

    LOGIC = "logic"
    TEST = "test"
    DOCS = "docs"
    META = "meta"
    OTHER = "other"


def _looks_like_a_test_name(name: str) -> bool:
    lowered = name.lower()
    if lowered == "conftest.py":
        return True
    if lowered.startswith(_TEST_NAME_PREFIXES):
        return True
    suffix = PurePosixPath(lowered).suffix
    if suffix in TEST_EXTENSIONS:
        return True
    if PurePosixPath(lowered).stem in TEST_SUPPORT_STEMS and suffix in LOGIC_EXTENSIONS:
        return True
    return any(infix in lowered for infix in _TEST_NAME_INFIXES)


def classify(path: str) -> PathKind:
    """Classify one repository-relative path.

    Test markers win over every other signal, so a fixture under tests/ is
    test material and not a configuration change.
    """
    parts = PurePosixPath(path).parts
    directories = {part.lower() for part in parts[:-1]}
    name = parts[-1] if parts else ""
    suffix = PurePosixPath(name).suffix.lower()
    stem = PurePosixPath(name).stem.lower()

    if directories & TEST_PATH_MARKERS or _looks_like_a_test_name(name):
        return PathKind.TEST
    if directories & DOCS_PATH_MARKERS:
        return PathKind.DOCS
    if directories & META_PATH_MARKERS or name.lower() in META_FILENAMES:
        return PathKind.META
    if stem in DOCS_STEMS or suffix in DOCS_EXTENSIONS:
        return PathKind.DOCS
    if suffix in META_EXTENSIONS:
        return PathKind.META
    if suffix in LOGIC_EXTENSIONS:
        return PathKind.LOGIC
    return PathKind.OTHER
