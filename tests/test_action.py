"""The action definition keeps the promises made about it.

The checks read ``action.yml`` as text: the project has no dependencies, so
there is no YAML parser to lean on, and the properties that matter here are
visible line by line.
"""

from pathlib import Path

ACTION = Path(__file__).resolve().parent.parent / "action.yml"
CALL = 'python3 -m pandagate check --post "$PANDAGATE_PULL_REQUEST_URL"'


def _text() -> str:
    return ACTION.read_text(encoding="utf-8")


def _run_lines() -> list[str]:
    """Every line that sits inside a ``run:`` block."""
    collected: list[str] = []
    indent: int | None = None
    for line in _text().splitlines():
        stripped = line.strip()
        depth = len(line) - len(line.lstrip(" "))
        if indent is not None:
            if stripped and depth <= indent:
                indent = None
            else:
                collected.append(line)
                continue
        if stripped.startswith("run:"):
            indent = depth
    return collected


def test_the_action_is_composite():
    assert "  using: composite" in _text().splitlines()


def test_there_is_a_script_to_inspect():
    assert any(line.strip() for line in _run_lines())


def test_no_expression_is_pasted_into_a_script():
    assert [line for line in _run_lines() if "${{" in line] == []


def test_no_other_action_is_used():
    used = [line for line in _text().splitlines() if line.strip().lstrip("- ").startswith("uses:")]
    assert used == []


def test_the_token_and_the_address_travel_through_the_environment():
    lines = [line.strip() for line in _text().splitlines()]
    assert "GITHUB_TOKEN: ${{ inputs.token }}" in lines
    assert "PANDAGATE_PULL_REQUEST_URL: ${{ github.event.pull_request.html_url }}" in lines


def test_the_script_calls_the_module_from_its_own_source():
    script = [line.strip() for line in _run_lines()]
    assert CALL in script
    assert script.index('cd "$GITHUB_ACTION_PATH/src"') < script.index(CALL)
    first_python = next(i for i, line in enumerate(script) if "python3" in line)
    assert script.index('cd "$GITHUB_ACTION_PATH/src"') < first_python


def test_nothing_is_installed():
    assert "pip install" not in _text()
