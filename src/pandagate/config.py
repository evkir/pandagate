"""Reading .pandagate.toml.

The configuration is read from the base branch of a pull request, never
from the pull request's own head: a contributor must not be able to turn
off the rules that read their own pull request.

This module knows nothing about individual rules. An entry under
[rules.<id>] is carried through as an opaque mapping, and the rule that
consumes it is the one that validates it.
"""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

CONFIG_FILENAME = ".pandagate.toml"

#: A configuration file past this size is a mistake or an attack, not a
#: configuration, and is refused before it is read into memory.
MAX_CONFIG_BYTES = 64 * 1024


class ConfigError(ValueError):
    """The configuration cannot be used as written."""


class Mode(StrEnum):
    """How much the action does with what the rules report.

    WARN  post one comment, change nothing about the pull request
    OFF   report nothing

    There is deliberately no mode that fails a check or blocks a merge.
    The action reports observations, and an observation is not a verdict.
    """

    WARN = "warn"
    OFF = "off"


_TOP_LEVEL_KEYS = frozenset({"mode", "enabled_rules", "rules"})


@dataclass(frozen=True, slots=True)
class Config:
    """Resolved configuration.

    enabled_rules is None when the file names no rules, which enables
    every registered rule. An empty list enables none, and is distinct.
    """

    mode: Mode = Mode.WARN
    enabled_rules: tuple[str, ...] | None = None
    rule_options: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def is_enabled(self, rule_id: str) -> bool:
        """Whether this rule should run."""
        if self.mode is Mode.OFF:
            return False
        return self.enabled_rules is None or rule_id in self.enabled_rules

    def options_for(self, rule_id: str) -> Mapping[str, Any]:
        """This rule's options, empty when the file configures none."""
        return self.rule_options.get(rule_id, {})


def parse_config(text: str) -> Config:
    """Parse configuration text, raising ConfigError on anything unusable."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"not valid TOML: {exc}") from exc
    return _from_mapping(raw)


def _from_mapping(raw: Mapping[str, Any]) -> Config:
    warnings = [f"unknown key: {key}" for key in sorted(raw) if key not in _TOP_LEVEL_KEYS]
    enabled, enabled_warnings = _read_enabled_rules(raw)
    warnings.extend(enabled_warnings)
    return Config(
        mode=_read_mode(raw),
        enabled_rules=enabled,
        rule_options=_read_rule_options(raw),
        warnings=tuple(warnings),
    )


def _read_mode(raw: Mapping[str, Any]) -> Mode:
    value = raw.get("mode", Mode.WARN.value)
    if not isinstance(value, str):
        raise ConfigError("mode: expected a string")
    try:
        return Mode(value)
    except ValueError:
        allowed = ", ".join(m.value for m in Mode)
        raise ConfigError(f"mode: expected one of {allowed}, got {value!r}") from None


def _read_enabled_rules(raw: Mapping[str, Any]) -> tuple[tuple[str, ...] | None, list[str]]:
    if "enabled_rules" not in raw:
        return None, []
    value = raw["enabled_rules"]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError("enabled_rules: expected a list of rule identifiers")
    seen: set[str] = set()
    ordered: list[str] = []
    warnings: list[str] = []
    for item in value:
        if item in seen:
            warnings.append(f"enabled_rules: listed more than once: {item}")
            continue
        seen.add(item)
        ordered.append(item)
    return tuple(ordered), warnings


def _read_rule_options(raw: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    value = raw.get("rules", {})
    if not isinstance(value, dict):
        raise ConfigError("rules: expected a table of per-rule tables")
    options: dict[str, dict[str, Any]] = {}
    for rule_id, entry in value.items():
        if not isinstance(entry, dict):
            raise ConfigError(f"rules.{rule_id}: expected a table of options")
        options[rule_id] = dict(entry)
    return options


def load_config(path: Path) -> Config:
    """Read configuration from a file, falling back to defaults when absent.

    The absent file is the ordinary case: a repository that has never
    configured anything gets every rule at its default thresholds.

    The path must point into a checkout of the base branch. Reading it
    from the pull request's own head would let a contributor disable the
    rules that read their contribution.
    """
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return Config()
    except OSError as exc:
        raise ConfigError(f"{path.name}: cannot be read: {exc}") from exc

    if size > MAX_CONFIG_BYTES:
        raise ConfigError(f"{path.name}: larger than {MAX_CONFIG_BYTES} bytes, refusing to read")

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"{path.name}: cannot be read: {exc}") from exc

    try:
        return parse_config(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{path.name}: not valid UTF-8") from exc
