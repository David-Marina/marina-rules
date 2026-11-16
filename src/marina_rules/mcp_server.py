"""``marina_rules.mcp_server`` is ``marina_rules_core.mcp_server``: the same module object (see marina_rules/__init__.py).
``python -m marina_rules.mcp_server`` runs ``python -m marina_rules_core.mcp_server``."""
import sys

if __name__ == "__main__":
    import runpy
    runpy.run_module("marina_rules_core.mcp_server", run_name="__main__", alter_sys=True)
else:
    import marina_rules_core.mcp_server
    sys.modules[__name__] = marina_rules_core.mcp_server
