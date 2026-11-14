"""``marina_rules._precompiled`` is ``marina_rules_core._precompiled``: the same module object (see marina_rules/__init__.py).
``python -m marina_rules._precompiled`` runs ``python -m marina_rules_core._precompiled``."""
import sys

if __name__ == "__main__":
    import runpy
    runpy.run_module("marina_rules_core._precompiled", run_name="__main__", alter_sys=True)
else:
    import marina_rules_core._precompiled
    sys.modules[__name__] = marina_rules_core._precompiled
