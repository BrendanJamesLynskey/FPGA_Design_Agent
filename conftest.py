"""Repo-wide pytest options: on-board tests are marked ``hw`` and skipped unless asked for.

    python -m pytest -m hw --hw-port /dev/serial/by-id/... --hw-stamp dfd4624e designs/t1_dimmer_counter
(flow/bringup.py runs them this way, after programming the board.) Without ``--hw-port``
every ``hw`` test is skipped, so CI and a plain ``pytest`` never touch a serial port.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    g = parser.getgroup("hw", "tests on the attached board")
    g.addoption("--hw-port", default=None, help="the board's UART device; enables the hw tests")
    g.addoption("--hw-stamp", default=None, help="build stamp (8 hex digits) the bitstream must report")
    g.addoption("--hw-seed", type=int, default=20261030, help="seed for the random loopback values")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "hw: needs the programmed board on --hw-port (skipped otherwise)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--hw-port"):
        return
    skip = pytest.mark.skip(reason="hw test: needs the board (--hw-port)")
    for item in items:
        if "hw" in item.keywords:
            item.add_marker(skip)
