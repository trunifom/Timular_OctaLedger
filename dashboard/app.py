"""Streamlit entry point. Start with ``scripts\\start_dashboard.bat``.

The whole dashboard lives in the installable package ``octaledger.dashboard`` so that it is
type-checked, importable and covered by automated GUI tests; this file only starts it.
"""

from octaledger.dashboard.main import run

run()
