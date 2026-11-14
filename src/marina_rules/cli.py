"""``marina_rules.cli`` is ``marina_rules_core.cli``: the same module object (see marina_rules/__init__.py).
``python -m marina_rules.cli`` runs ``python -m marina_rules_core.cli``."""
import sys

if __name__ == "__main__":
    import runpy
    runpy.run_module("marina_rules_core.cli", run_name="__main__", alter_sys=True)
else:
    import marina_rules_core.cli
    sys.modules[__name__] = marina_rules_core.cli
