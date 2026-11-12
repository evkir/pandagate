"""Tests for the command line of the benchmark run."""

from pathlib import Path

import pytest

from benchmarks.run_benchmark import RESULTS_PATH, cli


class _Recorder:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def __call__(self, *, results_path: Path) -> int:
        self.paths.append(results_path)
        return 0


def test_output_goes_to_the_named_file(tmp_path: Path) -> None:
    run = _Recorder()
    target = tmp_path / "results-tuned.json"
    assert cli(["--output", str(target)], run=run) == 0
    assert run.paths == [target]


def test_default_output_is_the_baseline_and_it_is_protected(
    capsys: pytest.CaptureFixture[str],
) -> None:
    run = _Recorder()
    assert RESULTS_PATH.is_file()
    assert cli([], run=run) == 1
    assert run.paths == []
    assert "already exists" in capsys.readouterr().err


def test_an_existing_file_is_never_overwritten(tmp_path: Path) -> None:
    run = _Recorder()
    target = tmp_path / "results.json"
    target.write_text("{}", encoding="utf-8")
    assert cli(["--output", str(target)], run=run) == 1
    assert run.paths == []
    assert target.read_text(encoding="utf-8") == "{}"


def test_an_unknown_argument_is_an_argument_error() -> None:
    with pytest.raises(SystemExit) as caught:
        cli(["--overwrite"], run=_Recorder())
    assert caught.value.code == 2
