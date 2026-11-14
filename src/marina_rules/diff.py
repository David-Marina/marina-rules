"""``marina_rules.diff`` is ``marina_rules_core.diff``: the same module object (see marina_rules/__init__.py).
``python -m marina_rules.diff`` runs ``python -m marina_rules_core.diff``."""
import sys

if __name__ == "__main__":
    import runpy
    runpy.run_module("marina_rules_core.diff", run_name="__main__", alter_sys=True)
else:
    import marina_rules_core.diff
    sys.modules[__name__] = marina_rules_core.diff
