"""Brief 05k: generic mutation testing (flow/mutate.py --generic) and the `mutate` tool. A tiny design (a 4-bit adder
and an equality flag; the bench checks the sum only) gives exactly two operator mutants: the sum mutant must be killed
and the equality mutant must survive and be named in plain words. Each cocotb run is a few seconds."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from flow import mutate as M, verif_gates as G

ROOT = Path(__file__).resolve().parents[2]
RTL = """module tiny(input logic [3:0] a, input logic [3:0] b, output logic [3:0] sum, output logic eq);
    assign sum = a + b;
    assign eq  = (a == b);
endmodule
"""
BENCH = """import cocotb
from cocotb.triggers import Timer


@cocotb.test()
async def sums(dut):
    for a, b in ((1, 2), (5, 5), (7, 9)):
        dut.a.value, dut.b.value = a, b
        await Timer(1, "ns")
        assert int(dut.sum.value) == (a + b) & 15
"""
ENTRY = """from pathlib import Path
from flow import cocotb_run

HERE = Path(__file__).parent


def test_tiny_rtl():
    cocotb_run.run("tiny_05k", "tiny", sorted((HERE.parent / "rtl").glob("*.sv")), "tiny_bench", HERE)
"""


@pytest.fixture
def tiny(tmp_path):
    d = tmp_path / "tiny_design"
    (d / "rtl").mkdir(parents=True)
    (d / "tests").mkdir()
    (d / "rtl" / "tiny.sv").write_text(RTL)
    (d / "tests" / "tiny_bench.py").write_text(BENCH)
    (d / "tests" / "test_tiny_rtl.py").write_text(ENTRY)
    return d


def _cli(design, *args, lock=None):
    env = {**__import__("os").environ, "FDA_HEAVY_LOCK": str(lock)} if lock else __import__("os").environ
    return subprocess.run([sys.executable, str(ROOT / "flow" / "mutate.py"), str(design), "--generic", *args],
                          capture_output=True, text=True, cwd=ROOT, env=env, timeout=600)


def test_candidates_are_plain_operator_changes(tiny):
    c = M.generate_candidates(tiny / "rtl")
    assert [x["class"] for x in c] == ["plus_to_minus", "eq_to_ne"]
    assert "a + b" in c[0]["old_line"] and c[0]["line"] == 2
    assert M.apply_mutant(c[0], (tiny / "rtl" / "tiny.sv").read_text()).count("a - b") == 1
    assert "line 3" in M.plain_words(c[1]) and "'==' replaced by '!='" in M.plain_words(c[1])


def test_generic_run_kills_one_and_names_the_survivor(tiny, tmp_path):
    out = tiny / "build" / "verif" / "mutation.json"
    r = _cli(tiny, "--max-mutants", "5", "--seed", "7", lock=tmp_path / "lock")
    assert r.returncode == 0, r.stdout + r.stderr
    res = json.loads(out.read_text())
    assert (res["killed"], res["survived"], res["timed_out"], res["skipped"], res["invalid"]) == (1, 1, 0, 0, 0)
    assert res["score_pct"] == 50.0 and res["rng_seed"] == 7 and res["candidates"] == 2
    assert len(res["survivor_text"]) == 1 and "rtl/tiny.sv line 3" in res["survivor_text"][0]
    assert not (tmp_path / "lock").exists()                           # the lock is released
    assert (tiny / "rtl" / "tiny.sv").read_text() == RTL              # the real RTL is untouched
    # the gate reads this file: the reason names the survivor
    why = G.mutation_why(res)
    assert "50.0%" in why and "line 3" in why


def test_wall_cap_skips_and_never_counts_as_killed(tiny, tmp_path):
    r = _cli(tiny, "--wall-s", "0", lock=tmp_path / "lock")
    assert r.returncode == 0, r.stdout + r.stderr
    res = json.loads((tiny / "build" / "verif" / "mutation.json").read_text())
    assert res["skipped"] == 2 and res["killed"] == 0 and res["evaluated"] == 0 and res["score_pct"] == 0.0
    assert "no mutant was evaluated" in G.mutation_why(res)


def test_failing_baseline_writes_nothing(tiny, tmp_path):
    (tiny / "tests" / "tiny_bench.py").write_text(BENCH.replace("== (a + b)", "== (a + b + 1)"))
    r = _cli(tiny, lock=tmp_path / "lock")
    assert r.returncode == 3 and not (tiny / "build" / "verif" / "mutation.json").exists()


def test_busy_lock_returns_75(tiny, tmp_path):
    lock = tmp_path / "lock"
    lock.write_text("someone-else big-job 10:00 11:00\n")
    r = _cli(tiny, lock=lock)
    assert r.returncode == M.EX_BUSY and "BUSY" in r.stdout and "someone-else" in r.stdout
    assert lock.read_text().startswith("someone-else")               # not stolen, not deleted


def test_gate_message_without_mutation_names_the_tool():
    assert "`mutate` tool" in G.mutation_why(None)
