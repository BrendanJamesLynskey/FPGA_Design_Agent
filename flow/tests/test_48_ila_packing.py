"""Brief 48: the ILA probes packed into at most 5 ports (the free Basic licence tier on Vivado 2026.1 refuses more), and
the capture side that slices the samples back to the named probes. No Vivado or board needed."""
from __future__ import annotations

import random
from pathlib import Path

import pytest
import yaml

from flow import ila, prepare

ROOT = Path(__file__).resolve().parents[2]


def _t1_probes() -> list[dict]:
    return yaml.safe_load((ROOT / "designs" / "t1_dimmer_counter" / "probes.yaml").read_text())["probes"]


def test_t1_thirteen_probes_fit_in_two_ports():
    probes = _t1_probes()
    ports = prepare.pack_probes(probes)
    assert len(probes) == 13 and len(ports) <= prepare.ILA_MAX_PORTS == 5
    assert sorted(x["name"] for p in ports for x in p["slices"]) == sorted(p["name"] for p in probes)
    assert [p["width"] for p in ports] == [56, 8]


def test_offsets_are_contiguous_and_round_trip():
    rnd = random.Random(48)
    probes = [{"name": f"p{i}", "pins": f"x{i}", "width": rnd.choice([1, 1, 2, 8, 16]), "group": rnd.choice("abcde")}
              for i in range(40)]
    ports = prepare.pack_probes(probes)
    assert len(ports) <= 5
    for p in ports:                                   # slices tile the port exactly, in probe order
        end = 0
        for x in p["slices"]:
            assert x["offset"] == end
            end += x["width"]
        assert end == p["width"]
    for _ in range(50):                               # pack random values into the ports and cut them out again
        vals = {pr["name"]: rnd.getrandbits(pr["width"]) for pr in probes}
        words = {p["port"]: sum(vals[x["name"]] << x["offset"] for x in p["slices"]) for p in ports}
        for p in ports:
            for x in p["slices"]:
                assert (words[p["port"]] >> x["offset"]) & ((1 << x["width"]) - 1) == vals[x["name"]]


def test_more_than_five_groups_is_refused():
    probes = [{"name": f"p{i}", "pins": "x", "width": 4, "group": f"g{i}"} for i in range(6)]
    with pytest.raises(ValueError, match="limit is 5"):
        prepare.pack_probes(probes)


def test_probes_tcl_carries_both_lists():
    t = prepare.probes_tcl(ROOT / "designs" / "t1_dimmer_counter" / "probes.yaml")
    assert t.count("lappend ila_probes") == 13 and t.count("lappend ila_ports") == 2


def test_capture_is_sliced_back_to_the_named_probes(tmp_path: Path):
    pm = tmp_path / "probe_map.txt"
    pm.write_text("probe0   cnt   4   0  u/cnt_reg[*]/Q\nprobe0   dat   4   4  u/dat_reg[*]/Q\nprobe1   en    1   0  u/en_reg/Q\n")
    hw = tmp_path / "hw_probes.txt"
    hw.write_text("0 8 probe0[7:0] u/cnt_dat\n1 1 probe1[0] u/en\n")
    csv_p = tmp_path / "cap.csv"
    csv_p.write_text("Sample in Window,TRIGGER,u/cnt_dat,u/en\nRadix - UNSIGNED,UNSIGNED,HEX,HEX\n"
                     "0,0,A3,1\n1,1,5C,0\n2,0,F0,1\n")
    out = ila.load_capture(csv_p, pm, hw)
    assert out["cnt"] == [3, 0xC, 0] and out["dat"] == [0xA, 5, 0xF] and out["en"] == [1, 0, 1]
    assert out["TRIGGER"] == [0, 1, 0]


def test_old_probe_map_without_offsets_still_reads(tmp_path: Path):
    pm = tmp_path / "probe_map.txt"
    pm.write_text("probe0   count        16  u_dut/count_reg[*]/Q\nprobe1   press_up      1  u_dut/u_db_up/press_reg/Q\n")
    assert ila.read_probe_slices(pm) == [("count", 0, 0, 16), ("press_up", 1, 0, 1)]
    assert ila.read_probe_map(pm) == {0: ("count", 16), 1: ("press_up", 1)}


# --- the .ltx of an ILA that is an IP (flow/ltx_fix.py) ----------------------------------------------------------------------
FXD = ROOT / "flow" / "tests" / "fixtures" / "ila_ip_exceptions" / "ila_ip_base"


def _ltx_build(tmp: Path, with_names: bool = True) -> Path:
    import shutil
    d = tmp / "b"
    d.mkdir()
    for f in ("t1_dimmer_counter_top.ltx", "probe_map.txt"):
        shutil.copy(FXD / f, d / f)
    if with_names:
        shutil.copy(FXD / "probe_nets.txt", d / "probe_nets.txt")
    return d


def test_ltx_with_a_bus_net_without_subnets_is_repaired(tmp_path: Path):
    """Vivado 2026.1 wrote win_addr as {isBus: true} with no subnets for three bits; the hardware manager then rejected the file
    (Labtools 27-1979) and found no probes. The real file of the T1 ILA build is the fixture."""
    from flow import ltx_fix
    d = _ltx_build(tmp_path)
    fixed, problems = ltx_fix.fix_and_check(d)
    assert fixed == 3 and problems == []
    assert ltx_fix.fix_and_check(d) == (0, [])           # a repaired file passes untouched


def test_ltx_gap_is_an_error_not_a_silent_file(tmp_path: Path):
    from flow import ltx_fix
    fixed, problems = ltx_fix.fix_and_check(_ltx_build(tmp_path, with_names=False))
    assert fixed == 0 and len(problems) == 1 and "probe0[24:30]" in problems[0] and "without subnets" in problems[0]
    (tmp_path / "x").mkdir()
    assert ltx_fix.main([str(_ltx_build(tmp_path / "x", with_names=False))]) == 1
