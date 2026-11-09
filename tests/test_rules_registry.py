"""The registered rules, as a reader of the registry sees them."""

import pandagate.rules as rules_package
from pandagate.rules import diff_cohesion, issue_link, tests_with_code
from pandagate.rules.base import registry

EXPECTED = {
    "R1": issue_link.RULE,
    "R2": tests_with_code.RULE,
    "R3": diff_cohesion.RULE,
}


def test_importing_the_package_registers_every_rule() -> None:
    assert sorted(registry()) == sorted(EXPECTED)


def test_each_identifier_maps_to_its_own_rule() -> None:
    assert all(registry()[rule_id] is rule for rule_id, rule in EXPECTED.items())


def test_a_registered_rule_reports_its_own_identifier() -> None:
    assert all(rule.rule_id == rule_id for rule_id, rule in registry().items())


def test_every_registered_rule_carries_a_title() -> None:
    assert all(rule.title.strip() for rule in registry().values())


def test_no_rule_module_is_left_out_of_the_package() -> None:
    """A new rule file that nobody imports would never register itself."""
    from pathlib import Path

    directory = Path(rules_package.__file__).parent
    on_disk = {p.stem for p in directory.glob("*.py")} - {"__init__", "base"}
    imported = {type(rule).__module__.rsplit(".", 1)[-1] for rule in registry().values()}
    assert on_disk == imported
