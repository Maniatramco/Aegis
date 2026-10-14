"""Compatibility import; implementation lives in ags_models.registry."""
import sys as _sys
from importlib import import_module as _import_module
if __name__ == '__main__':
    from runpy import run_module as _run_module
    _run_module('ags_app.ags_models.registry', run_name='__main__')
else:
    _sys.modules[__name__] = _import_module("ags_app.ags_models.registry")
