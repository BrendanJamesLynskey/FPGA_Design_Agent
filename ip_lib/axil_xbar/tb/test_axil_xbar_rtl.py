"""ip_lib/axil_xbar under cocotb + Icarus Verilog 12: random traffic from Python masters to Python slaves through the
crossbar, brief 59's AXI4-Lite checker on every link, at several points of the parameter space; round-robin
read and write fairness; a reset in the middle of transfers; and the guards (a misaligned or overlapping map, out-of-range counts). HIL_RTL_AXIL_XBAR points
the tests at a seeded-fault copy of rtl/ (hil/ip_faults.py)."""
from __future__ import annotations

import json
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from cocotb_tools.runner import get_runner

ROOT = Path(__file__).resolve().parents[3]
XB = ROOT / "ip_lib" / "axil_xbar"
TB = XB / "tb"
BUILD = Path(os.environ.get("HIL_BUILD", ROOT / "build" / "hil_ip"))
CHECKER = [ROOT / "axi_tx" / "rtl" / f for f in ("axil_checker.sv", "axil_rules.sv", "axi_viol_log.sv")]


def rtl_dir() -> Path:
    return Path(os.environ.get("HIL_RTL_AXIL_XBAR", XB / "rtl"))


def holes(bases, bits, aw):
    """The gaps between the slaves' ranges (inclusive bounds), within the address space."""
    rs = sorted((b, b + (1 << n) - 1) for b, n in zip(bases, bits))
    out, cur = [], 0
    for lo, hi in rs:
        if lo > cur:
            out.append((cur, lo - 1))
        cur = max(cur, hi + 1)
    if cur <= (1 << aw) - 1:
        out.append((cur, (1 << aw) - 1))
    return out


# name: masters, slaves, address bits, bases, size bits (2**bits bytes each), traffic knobs
POINTS = {
    "m1s1": dict(n_m=1, n_s=1, addr_w=32, bases=[0x0], bits=[12]),
    "m2s3_holes": dict(n_m=2, n_s=3, addr_w=32, bases=[0x4000_0000, 0x4001_0000, 0x4003_0000], bits=[16, 12, 13]),
    "m3s4": dict(n_m=3, n_s=4, addr_w=32, bases=[0x0, 0x1000, 0x2000, 0x8000], bits=[12, 12, 12, 15]),
    "m4s2_aw16": dict(n_m=4, n_s=2, addr_w=16, bases=[0x0400, 0x8000], bits=[10, 15]),
    "m2s5_small": dict(n_m=2, n_s=5, addr_w=12, bases=[0x000, 0x040, 0x080, 0x100, 0x800], bits=[6, 6, 6, 8, 11]),
}
TRAFFIC = {
    "busy": dict(p_valid=0.9, p_ready=0.9, p_sready=0.9, max_lat=0),
    "stalls": dict(p_valid=0.5, p_ready=0.4, p_sready=0.35, max_lat=4),
}


def params(p):
    aw = p["addr_w"]
    base = sum(b << (i * aw) for i, b in enumerate(p["bases"]))
    bits = sum(n << (i * 8) for i, n in enumerate(p["bits"]))
    return {"N_M": p["n_m"], "N_S": p["n_s"], "ADDR_W": aw,
            "S_BASE": f"{p['n_s'] * aw}'h{base:x}", "S_BITS": f"{p['n_s'] * 8}'h{bits:x}"}


def _run(name, p, testcase, extra_cfg):
    build = BUILD / f"axil_xbar_{name}"
    r = get_runner("icarus")
    srcs = sorted(str(f) for f in rtl_dir().glob("*.sv")) + [str(TB / "axil_xbar_tb.sv")] + [str(f) for f in CHECKER]
    r.build(sources=srcs, hdl_toplevel="axil_xbar_tb", parameters=params(p), build_dir=build, timescale=("1ns", "1ps"),
            always=True, build_args=["-g2012"])
    c = dict(p, holes=holes(p["bases"], p["bits"], p["addr_w"]), **extra_cfg)
    env = {"PYTHONPATH": os.pathsep.join([str(ROOT), str(TB), os.environ.get("PYTHONPATH", "")]),
           "XBAR_CFG": json.dumps(c), "XBAR_OUT": str(build / f"{testcase}.json")}
    res = r.test(test_module="cocotb_axil_xbar", hdl_toplevel="axil_xbar_tb", testcase=testcase, build_dir=build,
                 test_dir=TB, parameters=params(p), extra_env=env, results_xml=str(build / "results.xml"),
                 log_file=build / "sim.log", timescale=("1ns", "1ps"))
    ran = [x for x in ET.parse(res).getroot().iter("testcase") if x.find("skipped") is None]
    bad = [x.get("name") for x in ran if x.find("failure") is not None or x.find("error") is not None]
    assert [x.get("name") for x in ran] == [testcase], f"ran {[x.get('name') for x in ran]}"
    assert not bad, f"{name}: failed {bad} (log {build / 'sim.log'})"
    out = build / f"{testcase}.json"
    return json.loads(out.read_text()) if out.is_file() else {}


CASES = [(p, t, seed) for p in POINTS for t in TRAFFIC for seed in (1, 2)]


@pytest.mark.parametrize("point,traffic,seed", CASES, ids=[f"{p}-{t}-s{s}" for p, t, s in CASES])
def test_traffic(point, traffic, seed):
    p = POINTS[point]
    out = _run(f"{point}_{traffic}_s{seed}", p, "xbar_traffic",
               dict(TRAFFIC[traffic], seed=seed, ops=60, p_hole=0.1, expect_overlap=p["n_m"] > 1 and p["n_s"] > 1))
    assert out["writes"] + out["reads"] == 60 * p["n_m"]
    assert out["decerr"] > 0, "no hole was exercised"      # every point leaves part of its address space unmapped


@pytest.mark.parametrize("point", ["m2s3_holes", "m3s4", "m4s2_aw16"])
def test_fairness(point):
    _run(f"{point}_fair", POINTS[point], "xbar_fairness", {"seed": 0})


@pytest.mark.parametrize("point", ["m2s3_holes", "m3s4", "m4s2_aw16"])
def test_write_fairness(point):
    """Every master writes one slave back to back: the write arbiter serves them equally (counts within one)."""
    _run(f"{point}_wfair", POINTS[point], "write_fairness", {})


@pytest.mark.parametrize("point", ["m1s1", "m2s3_holes"])
def test_reset_mid_transfer(point):
    """A reset with a write and a read in flight: nothing stale afterwards, and the next write completes."""
    _run(f"{point}_rst", POINTS[point], "reset_mid_transfer", {})


GUARDS = [
    ({"N_S": 2, "S_BASE": "64'h0000100000000800", "S_BITS": "16'h0c0c"}, "not a multiple"),     # 0x800 with 4 KB size
    ({"N_S": 2, "S_BASE": "64'h0000100000000000", "S_BITS": "16'h0c0d"}, "overlap"),            # 8 KB at 0 holds 0x1000
    ({"N_S": 1, "S_BITS": "8'h01"}, "outside 2..ADDR_W"),
    ({"N_M": 0}, "N_M"),
    ({"N_M": 17}, "N_M"),
    ({"N_S": 33, "S_BASE": "1056'h0", "S_BITS": "264'h0"}, "N_S"),
    ({"ADDR_W": 8, "S_BITS": "8'h04"}, "ADDR_W"),
]


@pytest.mark.parametrize("over,msg", GUARDS, ids=[g[1].replace(" ", "_") + str(i) for i, g in enumerate(GUARDS)])
def test_guard_rejects(over, msg):
    """An out-of-space parameter value or a bad map must stop elaboration with the block's own $error."""
    vvp = BUILD / f"guard_axil_xbar_{abs(hash(json.dumps(over, sort_keys=True)))}.vvp"
    vvp.parent.mkdir(parents=True, exist_ok=True)
    srcs = sorted(str(f) for f in rtl_dir().glob("*.sv"))
    cmd = ["iverilog", "-g2012", "-o", str(vvp), "-s", "axil_xbar", *[f"-Paxil_xbar.{k}={v}" for k, v in over.items()], *srcs]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:          # some bad values (N_M = 0) already fail to elaborate: that is a refusal too
        return
    out = subprocess.run(["vvp", str(vvp)], capture_output=True, text=True)
    assert "ERROR" in out.stdout and "axil_xbar:" in out.stdout and msg in out.stdout, f"{over} was accepted: {out.stdout}"
