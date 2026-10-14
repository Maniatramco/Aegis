"""Compatibility import; implementation lives in ags_agent.onboard_extract_agent."""
import sys as _sys
from importlib import import_module as _import_module
_sys.modules[__name__] = _import_module("ags_app.ags_agent.onboard_extract_agent")
