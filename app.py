"""Streamlit entry point for the PolicyLens frontend."""

import importlib
import sys
from pathlib import Path

import streamlit as st


_MODULES = (
    "backend.repository",
    "backend.services.claim_readiness",
    "backend.services.documents",
    "backend.services.geography",
    "backend.services.occupations",
    "backend.services.recommendations",
    "frontend.app",
)
_loaded = st.session_state.get("_policylens_mtimes", {})
_current = {}
for _name in _MODULES:
    _module = importlib.import_module(_name)
    _path = Path(_module.__file__)
    _current[_name] = _path.stat().st_mtime_ns
if _current != _loaded:
    for _name in _MODULES:
        importlib.reload(sys.modules[_name])
    st.session_state["_policylens_mtimes"] = _current

importlib.import_module("frontend.app").main()
