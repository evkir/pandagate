"""Tests for path classification."""

import pytest

from pandagate.paths import PathKind, classify


@pytest.mark.parametrize(
    "path",
    [
        "src/pandagate/cli.py",
        "app/main.go",
        "lib/parser.rs",
        "web/components/Button.tsx",
        "scripts/deploy.sh",
    ],
)
def test_source_files_are_logic(path: str) -> None:
    assert classify(path) is PathKind.LOGIC


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_facts.py",
        "test/helpers.py",
        "src/__tests__/button.js",
        "tests/fixtures/payload.json",
        "tests/conftest.py",
        "pkg/parser_test.go",
        "web/button.spec.ts",
        "spec/models/user.rb",
        "testing/python/fixtures.py",
        "src/testing/helper.py",
        "crates/ty_python_semantic/resources/mdtest/call/function.md",
        "pkg/render/snapshots/page.html",
        "web/__snapshots__/button.html",
        "crates/demo/src/testing.rs",
        "ui/Button.snap",
    ],
)
def test_test_material_is_test(path: str) -> None:
    assert classify(path) is PathKind.TEST


@pytest.mark.parametrize(
    "path", ["README.md", "LICENSE", "CHANGELOG", "docs/guide.rst", "docs/conf.py"]
)
def test_documentation_is_docs(path: str) -> None:
    assert classify(path) is PathKind.DOCS


@pytest.mark.parametrize(
    "path",
    [
        "pyproject.toml",
        ".pandagate.toml",
        ".github/workflows/ci.yml",
        "Dockerfile",
        "Makefile",
        "setup.py",
        ".gitignore",
        "uv.lock",
    ],
)
def test_configuration_is_meta(path: str) -> None:
    assert classify(path) is PathKind.META


@pytest.mark.parametrize("path", ["assets/logo.png", "data/model.bin", "fonts/x.woff2"])
def test_unrecognised_files_are_other(path: str) -> None:
    assert classify(path) is PathKind.OTHER


def test_a_directory_merely_containing_test_is_not_test_material() -> None:
    assert classify("src/contest/helper.py") is PathKind.LOGIC
    assert classify("src/latest/helper.py") is PathKind.LOGIC


def test_a_name_merely_starting_with_test_as_a_word_is_not_a_test() -> None:
    assert classify("src/testament.py") is PathKind.LOGIC


def test_a_testing_name_is_test_support_only_for_source_files() -> None:
    assert classify("guide/testing.md") is PathKind.DOCS
    assert classify("src/testing") is PathKind.OTHER
    assert classify("src/testing_utils.py") is PathKind.LOGIC


def test_classification_is_case_insensitive() -> None:
    assert classify("Tests/Test_Thing.py") is PathKind.TEST
    assert classify("DOCKERFILE") is PathKind.META


def test_empty_path_is_other() -> None:
    assert classify("") is PathKind.OTHER
