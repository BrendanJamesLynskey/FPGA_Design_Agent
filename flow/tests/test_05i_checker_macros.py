"""Brief 05i: the checker macro file is seeded into every run, read-only for the roles, and the V1 gate says when a
name was declared as plain SystemVerilog. Fixture: the t1_checker.sv the live run 20261104-040146-b5cd wrote."""

import shutil
from pathlib import Path

import pytest

from agent.core.security import PathJail, SecurityError
from flow import verif_gates as G

ROOT = Path(__file__).resolve().parents[2]
T1 = ROOT / "designs" / "t1_dimmer_counter"
PLAIN = Path(__file__).parent / "data" / "t1_checker_plain_sv.sv"


def _tree(tmp_path, monkeypatch, checker_text=None):
    """A copy of the T1 reference design whose checkers are the plain-SV file, under a patched repo root."""
    dst = tmp_path / "designs" / "t1_dimmer_counter"
    shutil.copytree(T1, dst, ignore=shutil.ignore_patterns("__pycache__", "build"))
    chk = dst / "verif" / "checkers"
    for f in chk.glob("*.sv"):
        f.unlink()
    (chk / "t1_checker.sv").write_text(checker_text if checker_text is not None else PLAIN.read_text())
    plan_f = dst / "verif" / "testplan.yaml"
    plan = G.yaml.safe_load(plan_f.read_text())
    plan["requirements"][0]["cover_props"] = ["C_btnu_press", "C_nowhere_declared"]
    plan["requirements"][0]["assertions"] = []
    plan_f.write_text(G.yaml.safe_dump(plan))
    monkeypatch.setattr(G, "ROOT", tmp_path)
    return dst


def _v1(dst, tmp_path):
    return G.evaluate(dst, tmp_path / "none", [], tmp_path / "nof", None, None)


def test_plain_sv_name_is_called_plain_sv_and_unknown_name_keeps_the_ordinary_message(tmp_path, monkeypatch):
    dst = _tree(tmp_path, monkeypatch)
    refs = _v1(dst, tmp_path)["stages"]["V1"]["checks"]["unresolved_references"]["value"]
    plain = [x for x in refs if "C_btnu_press" in x]
    other = [x for x in refs if "C_nowhere_declared" in x]
    assert plain and "declared as plain SV; the gate reads only `V_*(name, ...)` from v_macros.svh" in plain[0]
    assert other == [other[0]] and other[0].endswith("C_nowhere_declared")      # found nowhere: no extra text


def test_the_same_name_through_the_macro_resolves(tmp_path, monkeypatch):
    text = PLAIN.read_text().replace("C_btnu_press:     cover property (@(posedge clk) ok && btnu);",
                                     "`V_COVER(C_btnu_press, ok && btnu)")
    dst = _tree(tmp_path, monkeypatch, text)
    refs = _v1(dst, tmp_path)["stages"]["V1"]["checks"]["unresolved_references"]["value"]
    assert not any("C_btnu_press" in x for x in refs)


def test_seed_macros_copies_the_canonical_file_once(tmp_path):
    assert G.seed_macros(tmp_path) is True
    f = tmp_path / G.MACROS_REL
    assert f.read_text() == G.MACROS_CANON.read_text()
    f.write_text("// edited\n")
    assert G.seed_macros(tmp_path) is False and f.read_text() == "// edited\n"      # never overwritten


def test_the_reference_design_carries_the_canonical_file():
    assert (T1 / G.MACROS_REL).read_text() == G.MACROS_CANON.read_text()


def test_gate_warns_when_the_macro_file_differs_or_is_missing(tmp_path, monkeypatch):
    dst = _tree(tmp_path, monkeypatch)
    (dst / G.MACROS_REL).unlink()
    assert "missing" in _v1(dst, tmp_path)["warnings"][0]
    G.seed_macros(dst)
    assert "warnings" not in _v1(dst, tmp_path)
    (dst / G.MACROS_REL).write_text((dst / G.MACROS_REL).read_text() + "`define V_SAME(n,a,c)\n")
    assert "differs from the flow's canonical copy" in _v1(dst, tmp_path)["warnings"][0]


def test_the_jail_refuses_a_write_to_the_macro_file(tmp_path):
    G.seed_macros(tmp_path)
    j = PathJail(tmp_path)
    assert j.resolve(G.MACROS_REL).is_file()                       # readable
    with pytest.raises(SecurityError):
        j.resolve(G.MACROS_REL, write=True)
    j.resolve("verif/checkers/t1_checker.sv", write=True)           # the role's own checker files stay writable
