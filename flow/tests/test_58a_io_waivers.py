"""The DDR edge-pairing check (io_check IO-DDR-REQUIREMENT) and the TIMING-47 waivers of the exceptions gate.

Fixture: the reports of a routed KR260 build whose RGMII exceptions kept the wrong edge pairs (flow/tests/fixtures/
b58a_io): Vivado then timed the centre-aligned receive data against a full period (setup requirement 8 ns, hold -4 ns)
and the forwarded-clock transmit data likewise. The requirement check must catch that; with the intended pairing it
must not. No Vivado needed."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from flow import exceptions_check as ec
from flow import io_check

ROOT = Path(__file__).resolve().parents[2]
FX = Path(__file__).parent / "fixtures" / "b58a_io"
XDC = FX / "design" / "design.xdc"


def interfaces() -> list[dict]:
    return yaml.safe_load((ROOT / "designs" / "b58a_trigger" / "build.yaml").read_text())["io_interfaces"]


def slow() -> list[str]:
    return yaml.safe_load((ROOT / "boards" / "kr260" / "board.yaml").read_text())["slow_ports"]


def test_requirements_from_the_interface() -> None:
    rx, tx = interfaces()[0], interfaces()[2]
    assert io_check.ddr_requirements(rx) == {"max": 4.0, "min": 0.0}
    assert io_check.ddr_requirements(tx) == {"max": 4.0, "min": 0.0}
    fwd90 = {"ddr": True, "clock_period_ns": 8.0, "direction": "out", "forwarded_phase_deg": 90}
    assert io_check.ddr_requirements(fwd90) == {"max": 2.0, "min": -2.0}
    assert io_check.ddr_requirements({"ddr": False, "clock_period_ns": 8}) is None


def test_wrong_edge_pairing_is_caught() -> None:
    """The fixture's build (the B3 finding): full-period requirements on the RGMII ports."""
    r = io_check.evaluate(FX / "reports", "route", [XDC], interfaces(), [], slow())
    bad = [f for f in r["failures"] if f["rule"] == "IO-DDR-REQUIREMENT"]
    names = {f["message"].split(":")[0] for f in bad}
    assert {"interface rgmii_rx_a", "interface rgmii_rx_b", "interface rgmii_tx_a", "interface rgmii_tx_b"} <= names, bad
    assert any("setup requirement 8 ns" in f["message"] for f in bad)


def test_intended_pairing_passes(tmp_path: Path) -> None:
    """The same dump with the requirements of the intended pairing: no IO-DDR-REQUIREMENT."""
    d = tmp_path / "rep"
    shutil.copytree(FX / "reports", d)
    lines = []
    for ln in (d / "io_paths_route.txt").read_text().splitlines():
        f = ln.split("|")
        if f[0] == "IO" and f[1].startswith(("a_rx", "b_rx")):
            f[5] = "4.000" if f[3] == "max" else "0.000"
        if f[0] == "IO" and f[1].startswith(("a_tx", "b_tx")):
            f[5] = "4.000" if f[3] == "max" else "0.000"
        lines.append("|".join(f))
    (d / "io_paths_route.txt").write_text("\n".join(lines) + "\n")
    r = io_check.evaluate(d, "route", [XDC], interfaces(), [], slow())
    assert not [f for f in r["failures"] if f["rule"] == "IO-DDR-REQUIREMENT"], r["failures"]


@pytest.mark.parametrize("text,ok", [
    ("set_false_path -setup -rise_from [get_clocks a_rxc_v] -fall_to [get_clocks a_rxc]", True),
    ("set_false_path -hold  -fall_from [get_clocks a_rxc_v] -fall_to [get_clocks a_rxc]", True),
    ("set_false_path -from [get_clocks a_rxc_v] -to [get_clocks a_rxc]", False),                 # whole clock
    ("set_false_path -setup -from [get_clocks a_rxc_v] -to [get_clocks a_rxc]", False),          # no edges
    ("set_clock_groups -asynchronous -group [get_clocks a_rxc] -group [get_clocks clk0_u]", False),
    ("set_false_path -setup -rise_from [get_clocks a] -fall_to [get_cells x]", False),
])
def test_waiver_shapes(text: str, ok: bool) -> None:
    assert (ec.waiver_shape_problem(text) is None) == ok


def test_waiver_clocks() -> None:
    clocks = {"a_rxc_v": {"virtual": True, "generated": False, "source": ""},
              "a_rxc": {"virtual": False, "generated": False, "source": "a_rxc"},
              "clk0_u": {"virtual": False, "generated": True, "source": "u_mmcm/CLKOUT0"},
              "a_txc": {"virtual": False, "generated": True, "source": "a_txc"}}
    ports = {"a_rxc": "in", "a_txc": "out"}
    ok = "set_false_path -setup -rise_from [get_clocks {}] -fall_to [get_clocks {}]"
    assert ec.waiver_clock_problem(ok.format("a_rxc_v", "a_rxc"), clocks, ports) is None
    assert ec.waiver_clock_problem(ok.format("clk0_u", "a_txc"), clocks, ports) is None
    assert ec.waiver_clock_problem(ok.format("clk0_u", "a_rxc"), clocks, ports) is not None   # not virtual -> port
    assert ec.waiver_clock_problem(ok.format("a_rxc_v", "clk0_u"), clocks, ports) is not None


def _build(tmp_path: Path, waivers: dict | None) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    d = tmp_path / "rep"
    shutil.copytree(FX / "reports", d)
    des = tmp_path / "design"
    des.mkdir()
    if waivers is not None:
        (des / "waivers.yaml").write_text(yaml.safe_dump(waivers))
    (d / "prepare.json").write_text(json.dumps({"design": str(des), "files": [str(XDC)]}))
    return d


def _flagged() -> dict[str, int]:
    """TIMING-47 count per XDC line in the fixture, from the gate itself (no waivers)."""
    out: dict[str, int] = {}
    for f in ec.evaluate(FX / "reports", "route", [XDC])["failures"]:
        if f["rule"] == "TIMING-47":
            out[f["text"]] = out.get(f["text"], 0) + 1
    return out


def test_no_waivers_fails() -> None:
    assert sum(_flagged().values()) == 16


def test_exact_waivers_waive(tmp_path: Path) -> None:
    """The receive lines (virtual clock to its port clock, one edge pair each) are waivable; the fixture's transmit lines
    name their clocks through pins and a two-clock list, which a waiver may not, so they still fail."""
    rx = {t: n for t, n in _flagged().items() if "rxc_v" in t}
    w = {"timing_47": [{"text": t, "count": n, "reason": "RGMII DDR edge pair"} for t, n in rx.items()]}
    r = ec.evaluate(_build(tmp_path, w), "route", [XDC])
    assert r["waived"] == 8 and not r["pass"]
    assert {f["rule"] for f in r["failures"]} == {"TIMING-47"} and all("txc" in f["text"] for f in r["failures"])
    tx = [{"text": t, "count": n, "reason": "x"} for t, n in _flagged().items() if "txc" in t]
    r2 = ec.evaluate(_build(tmp_path / "2", {"timing_47": w["timing_47"] + tx}), "route", [XDC])
    assert not r2["pass"] and sum(f["rule"] == "EXC-WAIVER" for f in r2["failures"]) == 4


def test_wrong_count_fails(tmp_path: Path) -> None:
    fl = _flagged()
    w = {"timing_47": [{"text": t, "count": n + (1 if i == 0 else 0), "reason": "x"} for i, (t, n) in enumerate(fl.items())]}
    r = ec.evaluate(_build(tmp_path, w), "route", [XDC])
    assert not r["pass"] and any(f["rule"] == "EXC-WAIVER" for f in r["failures"])


def test_whole_clock_waiver_fails(tmp_path: Path) -> None:
    w = {"timing_47": [{"text": "set_false_path -from [get_clocks a_rxc_v] -to [get_clocks a_rxc]", "count": 1,
                        "reason": "x"}]}
    r = ec.evaluate(_build(tmp_path, w), "route", [XDC])
    assert not r["pass"] and any(f["rule"] == "EXC-WAIVER" for f in r["failures"])
