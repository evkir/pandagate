"""Tests for reading .pandagate.toml."""

import pytest

from pandagate.config import (
    CONFIG_FILENAME,
    MAX_CONFIG_BYTES,
    Config,
    ConfigError,
    Mode,
    load_config,
    parse_config,
)


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


def _write(tmp_path, data):
    path = tmp_path / CONFIG_FILENAME
    path.write_bytes(data)
    return path


def test_an_absent_file_gives_defaults(tmp_path):
    config = load_config(tmp_path / CONFIG_FILENAME)
    assert config == Config()


def test_an_empty_file_gives_defaults(tmp_path):
    assert load_config(_write(tmp_path, b"")) == Config()


def test_a_file_is_parsed(tmp_path):
    path = _write(tmp_path, b'mode = "off"\n[rules.R1]\nrequire_closing_keyword = true\n')
    config = load_config(path)
    assert config.mode is Mode.OFF
    assert config.options_for("R1") == {"require_closing_keyword": True}


def test_utf8_content_survives_the_round_trip(tmp_path):
    path = _write(tmp_path, 'enabled_rules = ["Ромб"]\n'.encode())
    assert load_config(path).enabled_rules == ("Ромб",)


def test_an_oversized_file_is_refused_by_size(tmp_path):
    path = _write(tmp_path, b"# " + b"x" * MAX_CONFIG_BYTES)
    with pytest.raises(ConfigError, match="refusing to read"):
        load_config(path)


def test_a_file_at_the_size_limit_is_read(tmp_path):
    padding = b"# " + b"x" * (MAX_CONFIG_BYTES - 2)
    assert load_config(_write(tmp_path, padding)) == Config()


def test_a_file_that_is_not_utf8_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="UTF-8"):
        load_config(_write(tmp_path, b'mode = "\xff\xfe"'))


def test_a_directory_in_place_of_the_file_is_an_error(tmp_path):
    (tmp_path / CONFIG_FILENAME).mkdir()
    with pytest.raises(ConfigError, match="cannot be read"):
        load_config(tmp_path / CONFIG_FILENAME)
