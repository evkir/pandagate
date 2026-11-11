"""The workflow this repository runs on itself asks for no more than it needs."""

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "pandagate.yml"


def _lines() -> list[str]:
    return WORKFLOW.read_text(encoding="utf-8").splitlines()


def _stripped() -> list[str]:
    return [line.strip() for line in _lines()]


def test_it_runs_in_the_context_of_the_base_branch():
    assert "  pull_request_target:" in _lines()


def test_an_edited_description_is_read_again():
    assert "types: [opened, edited, synchronize, reopened]" in _stripped()


def test_the_workflow_itself_holds_no_permissions():
    assert "permissions: {}" in _lines()


def test_the_job_may_write_to_pull_requests_and_nothing_else():
    assert [line for line in _stripped() if line.endswith(": write")] == ["pull-requests: write"]
    assert "contents: read" in _stripped()


def test_nothing_is_checked_out_and_no_script_is_run():
    steps = [line for line in _stripped() if not line.startswith("#")]
    assert [line for line in steps if "checkout" in line] == []
    assert [line for line in steps if line.startswith(("run:", "- run:"))] == []
    assert [line for line in steps if "uses:" in line] == ["- uses: evkir/pandagate@main"]
