"""Tests for reading .pandagate.toml."""

import pytest

from pandagate.config import Config, ConfigError, Mode, parse_config


def test_empty_text_gives_defaults():
    config = parse_config("")
    assert config.mode is Mode.WARN
    assert config.enabled_rules is None
    assert config.rule_options == {}
    assert config.warnings == ()


def test_invalid_toml_is_rejected():
    with pytest.raises(ConfigError, match="not valid TOML"):
        parse_config("mode = ")


@pytest.mark.parametrize("value", ["warn", "off"])
def test_each_mode_is_accepted(value):
    assert parse_config(f'mode = "{value}"').mode is Mode(value)


def test_there_is_no_blocking_mode():
    with pytest.raises(ConfigError, match="mode"):
        parse_config('mode = "block"')


def test_mode_must_be_a_string():
    with pytest.raises(ConfigError, match="mode"):
        parse_config("mode = 3")


def test_enabled_rules_is_read_in_order():
    assert parse_config('enabled_rules = ["R2", "R1"]').enabled_rules == ("R2", "R1")


def test_an_empty_rule_list_enables_nothing():
    config = parse_config("enabled_rules = []")
    assert config.enabled_rules == ()
    assert not config.is_enabled("R1")


def test_a_repeated_rule_is_a_warning_not_an_error():
    config = parse_config('enabled_rules = ["R1", "R1"]')
    assert config.enabled_rules == ("R1",)
    assert any("more than once" in w for w in config.warnings)


@pytest.mark.parametrize("value", ["enabled_rules = 3", 'enabled_rules = ["R1", 2]'])
def test_a_malformed_rule_list_is_rejected(value):
    with pytest.raises(ConfigError, match="enabled_rules"):
        parse_config(value)


def test_rule_options_are_carried_through_untouched():
    config = parse_config('[rules.R2]\nmin_logic_lines = 20\nwhat = "ever"')
    assert config.options_for("R2") == {"min_logic_lines": 20, "what": "ever"}


def test_options_are_not_validated_against_any_rule():
    config = parse_config("[rules.R404]\nno_such_option = true")
    assert config.options_for("R404") == {"no_such_option": True}
    assert config.warnings == ()


def test_a_rule_without_options_gets_an_empty_mapping():
    assert parse_config("").options_for("R1") == {}


def test_rules_must_be_a_table_of_tables():
    with pytest.raises(ConfigError, match="rules"):
        parse_config("rules = 3")
    with pytest.raises(ConfigError, match="rules.R1"):
        parse_config("[rules]\nR1 = 3")


def test_an_unknown_key_is_a_warning_not_an_error():
    config = parse_config("verdict = true")
    assert config.warnings == ("unknown key: verdict",)


def test_unnamed_rules_are_all_enabled():
    config = Config()
    assert config.is_enabled("R1") and config.is_enabled("R99")


def test_a_named_rule_list_is_exhaustive():
    config = parse_config('enabled_rules = ["R1"]')
    assert config.is_enabled("R1")
    assert not config.is_enabled("R2")


def test_mode_off_disables_every_rule():
    config = parse_config('mode = "off"\nenabled_rules = ["R1"]')
    assert not config.is_enabled("R1")
