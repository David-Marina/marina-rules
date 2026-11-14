# ``marina_rules`` — the name to import. Point-in-time trading rules for financial markets, as data.
#
#     >>> import marina_rules as mr
#     >>> mr.rule_at("stamp_duty_sell", "2023-08-28")
#     0.0005
#
# Two packages are installed under this name. ``marina-rules`` (date versions, ``mr.VERSION``) is the dataset: it holds
# the rule files (``mr.DATA_DIR``) and this module. ``marina-rules-core`` (semantic versions, ``mr.__version__``) is the
# code, the module :mod:`marina_rules_core`. This module is that module under its usual name: every attribute is read
# from and written to :mod:`marina_rules_core` (``mr.rule_at is marina_rules_core.rule_at``), and each submodule
# (``marina_rules.check``, ``marina_rules.contract``, …) is the same module object as ``marina_rules_core.<name>``.
#
# The forwarding lives in the dataset package on purpose. Up to 2026.11.16 one package, ``marina-rules``, held the code
# and the data in this directory. Because the directory still belongs to ``marina-rules``, ``pip install -U
# marina-rules`` from one of those versions removes the old files and then writes these ones. Had this directory moved to
# marina-rules-core, pip would have installed it with the new dependency and then deleted it while removing the old
# version (it removes every file the old version's RECORD lists).

import sys as _sys
import types as _types

try:
    import marina_rules_core as _core
except ModuleNotFoundError as _e:
    if _e.name != "marina_rules_core":
        raise
    raise ImportError(
        "marina_rules: the code is not installed. It is the package marina-rules-core, which `pip install marina-rules` "
        "installs with the data (an install with --no-deps does not): pip install marina-rules-core") from None

# Names that belong to this module object itself (the import system's bookkeeping); everything else is the code's.
_OWN = frozenset({"__name__", "__qualname__", "__doc__", "__file__", "__path__", "__spec__", "__loader__",
                  "__package__", "__cached__", "__builtins__", "__class__", "__dict__", "_core", "_OWN", "_sys",
                  "_types", "_Forward", "_forward"})


def _forward(name):
    """A data descriptor for one name of the code module, so that tools which save and restore a module attribute
    through the module's own ``__dict__`` (pytest's monkeypatch, for one) still read and restore the code's value."""
    return property(lambda self: getattr(_core, name), lambda self, value: setattr(_core, name, value),
                    lambda self: delattr(_core, name))


class _Forward(_types.ModuleType):
    """A module whose attributes are those of marina_rules_core: reads, writes and deletes go there."""

    def __getattr__(self, name):           # names the code module gained after this one was imported
        return getattr(_core, name)

    def __setattr__(self, name, value):
        if name in _OWN:
            super().__setattr__(name, value)
        else:
            setattr(_core, name, value)

    def __delattr__(self, name):
        if name in _OWN:
            super().__delattr__(name)
        else:
            delattr(_core, name)

    def __dir__(self):
        return sorted(set(dir(_core)) | set(self.__dict__))


for _name in list(vars(_core)):
    if _name not in _OWN and (not _name.startswith("__") or _name in ("__version__", "__all__")):
        setattr(_Forward, _name, _forward(_name))
del _name

__doc__ = _core.__doc__   # help(marina_rules) shows the code's documentation; the note above says why it is here
_sys.modules[__name__].__class__ = _Forward
