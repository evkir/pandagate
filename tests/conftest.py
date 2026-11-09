"""Fixtures shared by the test suite."""

import pytest

from pandagate.rules import base


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test its own copy of the rule registry.

    The registry is process-wide and rules register themselves when their
    module is imported. A test that registers a stub would otherwise leave
    it in place for every test that runs after it, and the failure would
    surface somewhere unrelated.
    """
    monkeypatch.setattr(base, "_REGISTRY", dict(base._REGISTRY))
