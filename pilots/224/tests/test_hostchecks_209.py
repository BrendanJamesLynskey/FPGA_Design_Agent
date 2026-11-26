"""Dry runs of the brief 209 host checks against mock buses (no board): the logic passes a correct design and fails each seeded fault."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mocks_209 as m  # noqa: E402
import run_check as rc  # noqa: E402


@pytest.fixture(autouse=True)
def rom_file_present(tmp_path_factory, monkeypatch):
    """The p2 host check reads the design's ROM image, which is not in this tree. The mocks only need some 1024-word image, so when the real file is
    absent a deterministic stand-in is written to a temporary directory (the logic under test does not depend on the values)."""
    if not m.c2.ROM_FILE.exists():
        stand_in = tmp_path_factory.mktemp("rom") / "rom_init.hex"
        stand_in.write_text("".join(f"{(0x9E3779B1 * (i + 1)) & 0xFFFFFFFF:08x}\n" for i in range(m.c2.N)))
        monkeypatch.setattr(m.c2, "ROM_FILE", stand_in)


def go(design, tmp_path, **faults):
    clk = m.VClock()
    bus = m.MOCKS[design](clk, **faults)
    kw = {"soak_s": 600.0} if design == "p5_async_fifo" else {}
    if design == "p6_glitchfree_mux": kw["switches"] = 1000
    return rc.check(design, bus, clk, m.BUILD, tmp_path, **kw)


@pytest.mark.parametrize("design", sorted(m.MOCKS))
def test_good_design_passes(design, tmp_path):
    rep = go(design, tmp_path)
    assert rep.all_pass, [c for c in rep.criteria if not c["pass"]] or rep.aborted
    assert (tmp_path / f"{design}.json").exists()


@pytest.mark.parametrize("design,fault,crit", [
    ("p1_clkmeter", {"ppm": 300.0}, "c3_frequency_within_100ppm"),
    ("p2_bram_rom", {"bad_rom": 1}, "rom_matches_file"),
    ("p2_bram_rom", {"bad_ram": 1}, "ram_powerup_values"),
    ("p2_bram_rom", {"march_fault": 1}, "march_200_passes_errors"),
    ("p3_crc_engine", {"bad_crc": 1}, "crc_equals_zlib_1000_messages"),
    ("p4_fir_dsp", {"no_sat": 1}, "max_stress_sat_count"),
    ("p5_async_fifo", {"errs": 1}, "soak_data_errors_zero"),
    ("p6_glitchfree_mux", {"glitch": 1}, "mux_domain_errors_zero"),
    ("p6_glitchfree_mux", {"stuck": 1}, "freq_start_1s_sel1"),
])
def test_faulty_design_fails(design, fault, crit, tmp_path):
    rep = go(design, tmp_path, **fault)
    failed = {c["name"] for c in rep.criteria if not c["pass"]}
    assert crit in failed and rep.verdict() == "FAIL", (failed, rep.aborted)


@pytest.mark.parametrize("design", sorted(m.MOCKS))
def test_wrong_build_is_inconclusive_not_fail(design, tmp_path):
    rep = go(design, tmp_path, build=0xDEAD0000)
    assert rep.verdict() == "INCONCLUSIVE" and not rep.criteria


def test_board_script_syntax_and_refusals(tmp_path):
    import subprocess
    sh = Path(__file__).resolve().parents[1] / "run_pilot_board.sh"
    if not sh.exists():
        pytest.skip("run_pilot_board.sh is not in pilots/224 (the board script belongs to the 209 tree)")
    assert subprocess.run(["bash", "-n", str(sh)]).returncode == 0
    assert subprocess.run(["bash", str(sh), "nonsense", "YES"], capture_output=True).returncode == 2
    # without a stamp.txt the stage refuses before anything is touched (PILOT_ROOT points at an empty tree)
    (tmp_path / "pilots/209/p1_clkmeter").mkdir(parents=True)
    r = subprocess.run(["bash", str(sh), "p1_clkmeter", "YES"], capture_output=True, text=True, env={"PILOT_ROOT": str(tmp_path), "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    assert r.returncode == 2 and "no" in r.stdout and "stamp.txt" in r.stdout
    (tmp_path / "pilots/209/p1_clkmeter/stamp.txt").write_text("zz\n")
    r = subprocess.run(["bash", str(sh), "p1_clkmeter", "YES"], capture_output=True, text=True, env={"PILOT_ROOT": str(tmp_path), "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    assert r.returncode == 2 and "8 hex" in r.stdout
