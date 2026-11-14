"""``marina_rules.equity`` is ``marina_rules_core.equity``: the same module object (see marina_rules/__init__.py).
``python -m marina_rules.equity`` runs ``python -m marina_rules_core.equity``."""
import sys

if __name__ == "__main__":
    import runpy
    runpy.run_module("marina_rules_core.equity", run_name="__main__", alter_sys=True)
else:
    import marina_rules_core.equity
    sys.modules[__name__] = marina_rules_core.equity
