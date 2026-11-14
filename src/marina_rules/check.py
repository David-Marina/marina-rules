"""``marina_rules.check`` is ``marina_rules_core.check``: the same module object (see marina_rules/__init__.py).
``python -m marina_rules.check`` runs ``python -m marina_rules_core.check``."""
import sys

if __name__ == "__main__":
    import runpy
    runpy.run_module("marina_rules_core.check", run_name="__main__", alter_sys=True)
else:
    import marina_rules_core.check
    sys.modules[__name__] = marina_rules_core.check
