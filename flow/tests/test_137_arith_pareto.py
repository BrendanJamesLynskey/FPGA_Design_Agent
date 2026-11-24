"""Brief 137 (phase 0): the report parsers, error maths, Pareto helpers and Tcl generation of flow/arith_pareto.py.
No Vivado and no hw_dse needed. These are tool tests, not part of a design's bench, so no design testplan names them."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "flow"))
import arith_pareto as ap  # noqa: E402

UTIL = """
| Slice LUTs*             |  131 |     0 |          0 |     20800 |  0.63 |
| Slice Registers         |   76 |     0 |          0 |     41600 |  0.18 |
|   CARRY4                |   13 |     0 |          0 |      8150 |  0.16 |
"""
UTIL_US = "| CLB LUTs                |  8 |     0 |  0 | 117120 | <0.01 |\n| CLB Registers           |  45 |     0 |  0 | 234240 | 0.02 |\n| CARRY8                  |  4 | 0 | 0 | 14640 | 0.03 |\n| DSPs                    |  1 | 0 | 0 | 1248 | 0.08 |\n"
TIM = """
| Design Timing Summary
| ---------------------

    WNS(ns)      TNS(ns)  TNS Failing Endpoints  TNS Total Endpoints      WHS(ns)      THS(ns)  THS Failing Endpoints  THS Total Endpoints
    -------      -------  ---------------------  -------------------      -------      -------  ---------------------  -------------------
     -1.250      -42.000                     60                  180        0.110        0.000                      0                  180
"""
POW = "| Total On-Chip Power (W)  | 0.081        |\n| Dynamic (W)              | 0.011        |\n| Device Static (W)        | 0.070        |\n| Confidence Level         | Low          |\n"


def test_parse_util():
    assert ap.parse_util(UTIL) == dict(luts=131, ffs=76, carry=13, dsp=0, bram=0, lut_mem=0)
    u = ap.parse_util(UTIL_US)
    assert (u["luts"], u["ffs"], u["carry"], u["dsp"]) == (8, 45, 4, 1)


def test_parse_wns_and_power():
    t = ap.parse_wns(TIM)
    assert (t["wns"], t["tns"], t["whs"]) == (-1.25, -42.0, 0.11)
    assert ap.parse_power(POW) == dict(total_w=0.081, dynamic_w=0.011, static_w=0.07, confidence="Low")


def test_clean_drops_dates_and_paths():
    c = ap._clean("| Date         : Sat Nov 21\n| Host : x\nvalue /home/u/a/b.rpt\n")
    assert "Date" not in c and "Host" not in c and "/home/" not in c and "<path>" in c


def test_front_and_dominance():
    assert ap.dominates((1, 1), (2, 2)) and not ap.dominates((1, 3), (2, 2))
    assert ap.front({"a": (1, 3), "b": (2, 2), "c": (3, 3)}) == ["a", "b"]


def test_spearman():
    assert ap.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert ap.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0


def test_errors_per_axis():
    pred = {"P01": dict(luts=110.0, ffs=50.0, fmax_mhz=200.0)}
    meas = [dict(id="P01", route=dict(luts=100, ffs=50, fmax_mhz=250.0), synth=dict(luts=100, ffs=50, fmax_mhz=250.0))]
    e = ap.errors(pred, meas, "route")["summary"]
    assert e["luts"]["rms"] == 10.0 and e["ffs"]["rms"] == 0.0 and e["fmax_mhz"]["bias"] == -20.0


def test_points_are_unique_and_k26_subset():
    ids = [p[0] for p in ap.POINTS]
    assert len(ids) == len(set(ids)) == 13
    assert set(ap.K26_IDS) <= set(ids)
    assert {p[1] for p in ap.POINTS} == {"iterative", "unrolled_k", "pipelined", "pipelined_m"}


def test_tcl_names_every_job():
    t = ap.TCL.format(threads=2, part="xc7a35tcpg236-1", clock=3.5, jobs="{P01 m1} {P02 m2}")
    assert "foreach job {{P01 m1} {P02 m2}} {" in t and "route_design" in t and "report_power" in t and "-mode out_of_context" in t
