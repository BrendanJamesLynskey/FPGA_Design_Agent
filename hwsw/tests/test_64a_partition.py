"""Brief 64A: the partitioning cost model's formulas, crossovers, input checks and decision rules (plain Python)."""
from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest
import yaml

from hwsw import partition as P

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = sorted((ROOT / "hwsw" / "examples").glob("partition_*.yaml"))


def test_formulas_by_hand() -> None:
    sw = {"f_cpu_hz": 1e9, "cycles_per_call": 100, "cycles_per_item": 4}
    assert P.t_sw(sw, 1000) == pytest.approx(4.1e-6)
    acc = {"f_fabric_hz": 1e8, "latency_clocks": 10, "ii_clocks": 1, "bytes_in_per_item": 4, "bytes_out_per_item": 4,
           "dma_bytes_per_s": 4e8, "mmio_writes": 5, "mmio_reads": 1, "mmio_write_s": 1e-7, "mmio_read_s": 2e-7,
           "completion": "poll", "polls": 1, "coherent": False, "flush_bytes_per_s": 1e9, "invalidate_bytes_per_s": 2e9,
           "overlap": False}
    parts = P.accel_parts(acc, 1000)
    assert parts["setup"] == pytest.approx(7e-7)
    assert parts["cache"] == pytest.approx(4000 / 1e9 + 4000 / 2e9)
    assert parts["transfer_in"] == pytest.approx(1e-5) and parts["transfer_out"] == pytest.approx(1e-5)
    assert parts["compute"] == pytest.approx(1010 / 1e8)
    assert parts["done"] == pytest.approx(2e-7)
    assert parts["total"] == pytest.approx(7e-7 + 6e-6 + 2e-5 + 1.01e-5 + 2e-7)
    acc2 = dict(acc, overlap=True, coherent=True, completion="irq", irq_latency_s=5e-6)
    p2 = P.accel_parts(acc2, 1000)
    assert p2["cache"] == 0 and p2["body"] == pytest.approx(max(1e-5, 1.01e-5, 1e-5) + 10 / 1e8)
    assert p2["done"] == 5e-6


def test_amdahl() -> None:
    assert P.amdahl(0.5, 1e12) == pytest.approx(2.0)
    assert P.amdahl(0.6, 2.0) == pytest.approx(1 / (0.4 + 0.3))
    assert P.amdahl(0.0, 10) == 1.0


def test_break_even_matches_the_closed_form() -> None:
    # sw: 50 + 8n cycles at 1 GHz; accel: 2 us + n * 1 ns  ->  50e-9 + 8e-9 n = 2e-6 + 1e-9 n  ->  n = 278.57
    fa = lambda n: (50 + 8 * n) / 1e9                       # noqa: E731
    fb = lambda n: 2e-6 + n * 1e-9                           # noqa: E731
    assert P.break_even(fa, fb) == pytest.approx((2e-6 - 50e-9) / 7e-9, rel=1e-6)
    assert P.break_even(fb, fa) is None                      # software is never faster at large n
    assert P.crossings(fa, lambda n: 1e-9 * n)["faster_at_lo"] is True


def test_every_example_runs_and_reports() -> None:
    assert EXAMPLES, "no example inputs"
    for e in EXAMPLES:
        d = P.load(e)
        out, dec = P.run(e)
        text = P.report(d, out, dec)
        assert "Kernel:" in text and out["rows"]
        for r in out["rows"]:
            for k, v in r.items():
                if k.startswith("t_"):
                    assert 0 < v[0] <= v[1]


def test_zynq_example_is_a_measure_verdict() -> None:
    out, dec = P.run(ROOT / "hwsw" / "examples" / "partition_crc32_zynq.yaml")
    assert dec["choice"] == "measure"
    lo, hi = out["app_speedup_accel_at_typical_n"]
    assert lo < 1.1 < hi
    assert out["sensitivity_at_typical_n"][0]["input"] == "sw.cycles_per_item"


def _zynq() -> dict:
    return yaml.safe_load((ROOT / "hwsw" / "examples" / "partition_crc32_zynq.yaml").read_text())


@pytest.mark.parametrize("edit,expect", [
    (lambda d: d["options"]["sw"].update(cycles_per_item=5), "give {value: ..., source: ...}"),
    (lambda d: d["options"]["sw"].update(cycles_per_item={"value": [9, 2], "source": "x"}), "low <= high"),
    (lambda d: d["options"]["accel"].pop("flush_bytes_per_s"), "non-coherent port needs"),
    (lambda d: d["options"]["accel"].update(completion="irq"), "needs irq_latency_s"),
    (lambda d: d["options"]["accel"].update(bogus={"value": 1, "source": "x"}), "unknown inputs ['bogus']"),
    (lambda d: d["application"].update(kernel_fraction={"value": 1.0, "source": "x"}), "must be in [0, 1)"),
    (lambda d: d.update(sizes=[0, 4]), "positive integers"),
    (lambda d: d["options"].update(gpu={}), "give some of sw, ci, accel"),
], ids=["no source", "bad range", "no maintenance", "irq latency", "unknown", "fraction", "sizes", "option"])
def test_inputs_are_checked(edit, expect) -> None:
    d = copy.deepcopy(_zynq())
    edit(d)
    with pytest.raises(P.ModelError) as ex:
        P.check_inputs(d)
    assert expect in str(ex.value)


BASE = {"src_regs": 2, "dst_regs": 1, "state_bits": 0, "streaming": False, "memory_access": False,
        "unit_latency_clocks": 1, "unit_fmax_hz": 150e6, "core_fmax_hz": 100e6, "bytes_per_call": 1500,
        "accel_break_even_bytes": 300, "app_speedup_ci": 1.5, "app_speedup_accel": 1.3, "toolchain": "intrinsic",
        "reuse_programs": 3}


@pytest.mark.parametrize("change,ci_ok,acc_ok,choice,why", [
    ({}, True, True, "ci", "choose ci"),
    ({"src_regs": 3}, False, True, "accel", "3 source registers"),
    ({"dst_regs": 2}, False, True, "accel", "2 results"),
    ({"state_bits": 2048}, False, True, "accel", "2048 bits of state"),
    ({"streaming": True}, False, True, "accel", "streaming kernel"),
    ({"memory_access": True}, False, True, "accel", "accesses memory"),
    ({"unit_latency_clocks": 8}, False, True, "accel", "8-clock latency"),
    ({"unit_fmax_hz": 80e6}, False, True, "accel", "below the core's"),
    ({"bytes_per_call": 64}, True, False, "ci", "below its break-even"),
    ({"app_speedup_ci": [1.0, 1.4], "app_speedup_accel": 1.05}, True, True, "measure", "straddles 1.1"),
    ({"app_speedup_ci": 1.02, "app_speedup_accel": 1.04}, True, True, "sw", "choose software"),
    ({"src_regs": 3, "bytes_per_call": 64}, False, False, "sw", "choose software"),
])
def test_decision_rules(change, ci_ok, acc_ok, choice, why) -> None:
    dec = P.decide(dict(BASE, **change))
    assert (dec["ci_eligible"], dec["accel_eligible"], dec["choice"]) == (ci_ok, acc_ok, choice), dec
    assert any(why in r for r in dec["reasons"]), dec["reasons"]


def test_missing_traits_are_reported_not_assumed() -> None:
    dec = P.decide({"src_regs": 2, "app_speedup_ci": 2.0})
    assert "state_bits" in dec["unknown"] and "unit_latency_clocks" in dec["unknown"]


def test_corners_cover_both_ends() -> None:
    d = _zynq()
    cs = list(P.corners(d))
    assert len(cs) == 2 ** len(P._ranges(d))
    vals = {c["sw"]["cycles_per_item"] for c in cs}
    assert vals == {2.0, 10.0}
    assert not any(math.isnan(c["accel"]["dma_bytes_per_s"]) for c in cs)
