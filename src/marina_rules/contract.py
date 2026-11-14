"""``marina_rules.contract`` is ``marina_rules_core.contract``: the same module object (see marina_rules/__init__.py).
``python -m marina_rules.contract`` runs ``python -m marina_rules_core.contract``."""
import sys

if __name__ == "__main__":
    import runpy
    runpy.run_module("marina_rules_core.contract", run_name="__main__", alter_sys=True)
else:
    import marina_rules_core.contract
    sys.modules[__name__] = marina_rules_core.contract
