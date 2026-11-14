"""``marina_rules.sourcehash`` is ``marina_rules_core.sourcehash``: the same module object (see marina_rules/__init__.py).
``python -m marina_rules.sourcehash`` runs ``python -m marina_rules_core.sourcehash``."""
import sys

if __name__ == "__main__":
    import runpy
    runpy.run_module("marina_rules_core.sourcehash", run_name="__main__", alter_sys=True)
else:
    import marina_rules_core.sourcehash
    sys.modules[__name__] = marina_rules_core.sourcehash
