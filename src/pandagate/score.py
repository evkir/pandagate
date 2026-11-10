"""Running the enabled rules over one pull request.

This module owns the decisions that neither the configuration nor an
individual rule can make: which registered rules a configuration
actually selects, what to say about an identifier the configuration
names but no rule claims, and what happens when a rule raises.

A rule that fails produces one unknown reading, never a failed run. A
broken rule must not take the whole action down, and it must not turn
into something a contributor has to answer for.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from pandagate.config import Config, Mode
from pandagate.facts import PullRequestFacts
from pandagate.rules.base import Outcome, Rule, Signal, registry

#: What a rule reports in place of its own observation when it cannot be run.
UNREADABLE_DETAIL = "this rule could not be run on this pull request"


@dataclass(frozen=True, slots=True)
class Report:
    """Everything one run established about one pull request.

    Signals come from the rules. Warnings come from the configuration and
    from this module, and they are about the run itself, never about the
    pull request.
    """

    signals: tuple[Signal, ...] = ()
    warnings: tuple[str, ...] = ()

    def by_outcome(self, outcome: Outcome) -> tuple[Signal, ...]:
        """Every signal with this outcome, in report order."""
        return tuple(signal for signal in self.signals if signal.outcome is outcome)

    @property
    def questions(self) -> tuple[str, ...]:
        """Every question the rules carry, in report order."""
        return tuple(signal.question for signal in self.signals if signal.question)


def score(
    facts: PullRequestFacts,
    config: Config,
    rules: Mapping[str, Rule] | None = None,
) -> Report:
    """Run the configured rules over one pull request.

    Rules run in identifier order, so the report does not depend on the
    order in which modules happened to be imported.
    """
    available = registry() if rules is None else dict(rules)
    warnings = list(config.warnings)

    if config.mode is Mode.OFF:
        return Report((), tuple(warnings))

    if not available:
        warnings.append("no rules are registered")
        return Report((), tuple(warnings))

    warnings.extend(_unknown_rule_warnings(config, available))

    signals: list[Signal] = []
    for rule_id in sorted(available):
        if not config.is_enabled(rule_id):
            continue
        options = config.options_for(rule_id)
        signal, failure = _run_rule(available[rule_id], rule_id, facts, options)
        signals.append(signal)
        if failure is not None:
            warnings.append(failure)

    return Report(tuple(signals), tuple(warnings))


def _unknown_rule_warnings(config: Config, available: Mapping[str, Rule]) -> list[str]:
    """Report identifiers the configuration names that no rule claims.

    This is a warning and not an error: a configuration written for a
    later version of the action must still work on this one.
    """
    if config.enabled_rules is None:
        return []
    return [
        f"enabled_rules: no rule with this identifier: {rule_id}"
        for rule_id in config.enabled_rules
        if rule_id not in available
    ]


def _run_rule(
    rule: Rule,
    rule_id: str,
    facts: PullRequestFacts,
    options: Mapping[str, object],
) -> tuple[Signal, str | None]:
    """Evaluate one rule, converting any failure into an unknown reading."""
    try:
        signal = rule.evaluate(facts, options)
    except Exception as exc:
        reason = f"{rule_id}: the rule raised {type(exc).__name__}"
        return _unreadable(rule, rule_id), reason

    if not isinstance(signal, Signal):
        returned = type(signal).__name__
        reason = f"{rule_id}: the rule returned {returned} where a signal was expected"
        return _unreadable(rule, rule_id), reason

    if signal.rule_id != rule_id:
        reason = f"{rule_id}: the rule reported under the identifier {signal.rule_id}"
        return _unreadable(rule, rule_id), reason

    return signal, None


def _unreadable(rule: Rule, rule_id: str) -> Signal:
    """The signal that stands in for a rule that could not be run."""
    return Signal(rule_id, _title_of(rule, rule_id), Outcome.UNKNOWN, UNREADABLE_DETAIL)


def _title_of(rule: Rule, rule_id: str) -> str:
    """The rule's title, falling back to its identifier."""
    title = getattr(rule, "title", None)
    return title if isinstance(title, str) and title else rule_id
