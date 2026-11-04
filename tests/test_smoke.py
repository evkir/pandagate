"""Smoke tests. These are not evidence rules."""

import pandagate


def test_version_is_exposed() -> None:
    assert pandagate.__version__ == "0.0.1"


def test_rules_package_importable() -> None:
    import pandagate.rules  # noqa: F401


def test_no_third_party_dependencies_declared() -> None:
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)
    assert data["project"]["dependencies"] == []
