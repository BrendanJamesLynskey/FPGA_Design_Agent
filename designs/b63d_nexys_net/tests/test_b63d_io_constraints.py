"""The RMII I/O constraints of b63d_nexys_net against its declared interfaces (build.yaml io_interfaces), with
flow/io_check.py and no Vivado: clean as written, IO-CLOCK when the delays are referenced to the logic clock instead of
the forwarded eth_refclk (the mistake in the first build), IO-VALUE when a data-sheet number is wrong."""
from __future__ import annotations

from pathlib import Path

import yaml

from flow import io_check

D = Path(__file__).resolve().parents[1]
XDC = (D / "design.xdc").read_text()
IFS = yaml.safe_load((D / "build.yaml").read_text())["io_interfaces"]


def rules(text: str) -> set[str]:
    return {f["rule"] for f in io_check.evaluate(None, "route", [("design.xdc", text)], IFS, None, None)["failures"]}


def test_constraints_clean():
    assert rules(XDC) == set()


def test_wrong_clock_reference_is_caught():
    assert "IO-CLOCK" in rules(XDC.replace("[get_clocks eth_refclk]", "[get_clocks c0]"))


def test_wrong_data_sheet_value_is_caught():
    assert "IO-VALUE" in rules(XDC.replace("-max 14.0", "-max 12.0"))
