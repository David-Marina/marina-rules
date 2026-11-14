"""``marina_rules.adapt`` is ``marina_rules_core.adapt``: the same module object (see marina_rules/__init__.py).
``python -m marina_rules.adapt`` runs ``python -m marina_rules_core.adapt``."""
import sys

if __name__ == "__main__":
    import runpy
    runpy.run_module("marina_rules_core.adapt", run_name="__main__", alter_sys=True)
else:
    import marina_rules_core.adapt
    sys.modules[__name__] = marina_rules_core.adapt
