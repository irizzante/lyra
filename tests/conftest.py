"""Pytest config for the Lyra test suite.

Auto-skips tests that require the external ``qmd`` CLI when it is not
available on PATH (e.g. minimal dev environments that have not installed
``@tobilu/qmd``). CI installs qmd before running tests, so this skip never
fires there.
"""

from __future__ import annotations

import shutil

import pytest

QMD_AVAILABLE = shutil.which("qmd") is not None

_QMD_DEPENDENT_MODULES = {
    "tests/test_file_cmd.py",
    "tests/test_qa_filing.py",
    "tests/test_qmd_integration.py",
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if QMD_AVAILABLE:
        return
    skip_marker = pytest.mark.skip(
        reason="qmd CLI not installed (npm install -g @tobilu/qmd)"
    )
    for item in items:
        node_path = item.nodeid.split("::", 1)[0]
        if node_path in _QMD_DEPENDENT_MODULES:
            item.add_marker(skip_marker)
