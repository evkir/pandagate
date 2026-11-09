"""The evidence rules.

Importing this package imports every rule module, and each module
registers its rule as it is imported. Anything that reads the registry
imports this package first, so a rule that exists is a rule that runs.
"""

from pandagate.rules import diff_cohesion, issue_link, tests_with_code
from pandagate.rules.base import Outcome, Rule, Signal, register, registry

__all__ = [
    "Outcome",
    "Rule",
    "Signal",
    "diff_cohesion",
    "issue_link",
    "register",
    "registry",
    "tests_with_code",
]
