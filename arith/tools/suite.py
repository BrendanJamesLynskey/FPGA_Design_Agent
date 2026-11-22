"""The test bodies every arithmetic function shares (arith brief 139a); each function's tests/test_<fn>_*.py is a thin file that calls these.

The checks are about the files of one function: spec.yaml against the RTL's real port list and parameters, spec.md naming every variant and
port, Verilator -Wall lint of every variant at every point, the generated wrappers and build.yaml files being current and lint-clean, the
README linking the function, and the bench, mutation and formal runs themselves."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

from arith.tools import arith_common as ac
from arith.tools import gen_build


def point_params(fn: str, key: str) -> list:
    spec = ac.load_spec(fn)
    return [pytest.param(v, p, id=f"{v}-" + "-".join(f"{k}{x}" for k, x in p.items())) for v, vd in spec["variants"].items() for p in vd[key]]


def variant_ids(fn: str) -> list[str]:
    return list(ac.load_spec(fn)["variants"])


# ---- spec against RTL -----------------------------------------------------------------------------------------
_PORT = re.compile(r"^\s*(input|output)\s+logic\s*(?:\[[^\]]+\])?\s*(\w+)\s*,?\s*$")
_PARAM = re.compile(r"^\s*parameter\s+int\s+(\w+)\s*=\s*([^,\s]+)")


def rtl_interface(path: Path) -> tuple[list[tuple[str, str]], dict[str, str]]:
    """The module's ports (direction, name) and parameters (name -> default) as written in its header, skipping lint pragmas."""
    ports, params, in_head = [], {}, False
    for line in path.read_text().splitlines():
        if re.match(r"^module\s", line):
            in_head = True
        if not in_head:
            continue
        m = _PARAM.match(line)
        if m:
            params[m.group(1)] = m.group(2)
        m = _PORT.match(line)
        if m:
            ports.append((m.group(1), m.group(2)))
        if line.strip().startswith(");"):
            break
    return ports, params


def check_spec_matches_rtl(fn: str) -> None:
    spec = ac.load_spec(fn)
    want = [("input" if p["dir"] == "in" else "output", p["name"]) for p in spec["ports"]]
    for v, vd in spec["variants"].items():
        ports, params = rtl_interface(ac.ARITH / fn / vd["file"])
        assert ports == want, f"{v}: the RTL's ports {ports} differ from spec.yaml's {want}"
        assert {k: str(x) for k, x in vd["params"].items()} == params, f"{v}: spec.yaml's default parameters {vd['params']} differ from the RTL's {params}"
        assert re.search(rf"^module\s+{vd['module']}\b", (ac.ARITH / fn / vd["file"]).read_text(), re.M)
        # the intended primitive use is a stated expectation in the RTL's header, not a measurement
        head = (ac.ARITH / fn / vd["file"]).read_text().split("module ")[0]
        assert "Intended primitive use" in head and "not yet measured" in head, f"{v}: the RTL header must state the intended primitive use"
        assert vd["latency"] and vd.get("exhaustive_points") and vd.get("random_points") and vd.get("ooc_points") and vd.get("mutant_run")
    for key in ("contract", "integration"):
        assert spec.get(key), f"spec.yaml lacks {key}"
    for k in ("protocol", "throughput", "latency", "reset", "clock", "stall"):
        assert spec["contract"].get(k), f"contract lacks {k}"
    assert spec["integration"].get("port_timing") and spec["integration"].get("constraints")
    assert all(vd.get("throughput") for vd in spec["variants"].values())
    for key in ("guess_wrong", "latency_definition", "exactness", "signedness"):
        assert spec.get(key), f"spec.yaml lacks {key}"


def check_spec_md(fn: str) -> None:
    from arith.tools import gen_spec_md
    spec = ac.load_spec(fn)
    md = (ac.ARITH / fn / "spec.md").read_text()
    assert md == gen_spec_md.render(fn), f"arith/{fn}/spec.md is out of date: run python -m arith.tools.gen_spec_md"
    for v, vd in spec["variants"].items():
        assert vd["module"] in md
    for p in spec["ports"]:
        assert f"`{p['name']}`" in md
    for g in spec["guess_wrong"]:
        assert g in md


# ---- lint -----------------------------------------------------------------------------------------------------
def lint(top: str, files: list[Path], params: dict) -> str:
    v = ac.tool("verilator")
    assert v, "verilator not found (CI installs it; locally use the OSS CAD Suite)"
    cmd = [v, "--lint-only", "-Wall", "--top-module", top] + [f"-G{k}={x}" for k, x in params.items()] + [str(f) for f in files]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return "" if r.returncode == 0 else (r.stdout + r.stderr)[-800:]


def check_lint_clean(fn: str) -> None:
    spec = ac.load_spec(fn)
    bad = []
    for v, vd in spec["variants"].items():
        f = ac.ARITH / fn / vd["file"]
        pts = {json.dumps({**vd["params"], **p}, sort_keys=True): {**vd["params"], **p} for k in ("exhaustive_points", "random_points", "ooc_points") for p in vd[k]}
        pts[json.dumps(vd["params"], sort_keys=True)] = dict(vd["params"])
        for p in pts.values():
            e = lint(vd["module"], [f], p)
            if e:
                bad.append(f"{v} {p}: {e}")
    assert not bad, "\n".join(bad[:3])


def check_build_files(fn: str) -> None:
    spec = ac.load_spec(fn)
    outs = gen_build.outputs(fn)
    for p, t in outs.items():
        assert p.exists(), f"{p.relative_to(ac.ROOT)}: run python -m arith.tools.gen_build"
        assert p.read_text() == t, f"{p.relative_to(ac.ROOT)} is out of date: run python -m arith.tools.gen_build"
    bad = []
    for v, vd in spec["variants"].items():
        y = yaml.safe_load((ac.ARITH / fn / "build" / v / "build.yaml").read_text())
        assert y["top"] == vd["module"] + "_ooc" and y["part"] == ac.PARTS["a7"]
        assert set(y["ooc"]["parts"]) == {"a7", "k26"} and y["ooc"]["parts"]["k26"]["part"] == ac.PARTS["k26"]
        assert y["expected_primitives"] and set(y["expected_primitives"]) == {"a7", "k26"}
        for s in y["sources"]:
            assert (ac.ROOT / s).is_file(), f"{v}: source {s} missing"
        srcs = [ac.ROOT / s for s in y["sources"]]
        for p in [y["generics"]] + y["points"]:
            e = lint(y["top"], srcs, {**y["generics"], **p})
            if e:
                bad.append(f"{v} {p}: {e}")
    assert not bad, "\n".join(bad[:3])


def check_readme(fn: str) -> None:
    text = (ac.ARITH / "README.md").read_text()
    assert f"({fn}/spec.md)" in text and f"({fn}/verif/testplan.yaml)" in text, f"arith/README.md does not link {fn}"


# ---- the bench itself -----------------------------------------------------------------------------------------
def check_latency_is_exact(fn: str, variant: str, params: dict) -> None:
    """The bench is sensitive to the stated latency: claiming two clocks more than the variant has must make it fail."""
    spec = ac.load_spec(fn)
    p = ac.merged_params(spec, variant, params)
    good = ac.latency_of(spec, variant, p)
    ac.run_point(fn, variant, params, "randomised", n=200, lat=good)
    with pytest.raises(AssertionError):
        ac.run_point(fn, variant, params, "randomised", n=200, lat=good + 2)


def check_mutants(fn: str) -> None:
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / "mutation.json"
        r = subprocess.run([sys.executable, "-m", "arith.tools.run_mutants", fn, "--jobs", "2", "--json", str(out)], cwd=ac.ROOT, capture_output=True, text=True)
        assert out.exists(), r.stdout[-600:] + r.stderr[-600:]
        res = json.loads(out.read_text())
    assert not res["invalid"], f"mutants that do not build: {res['invalid']}"
    assert not res["survived"], f"mutants the bench did not kill: {res['survived']}"
    assert res["killed"] == res["valid"] and res["valid"] >= 10


def job_kind(j: dict) -> str:
    """proof (k-induction, no mutant), bounded (BMC, no mutant) or refute (a planted fault that must be caught)."""
    return "refute" if j.get("mutant") else ("bounded" if j.get("mode") == "bmc" else "proof")


def formal_job_params(fn: str, kind: str) -> list:
    jobs = yaml.safe_load((ac.ARITH / fn / "formal" / "jobs.yaml").read_text())["jobs"]
    return [pytest.param(j["name"], id=j["name"]) for j in jobs if job_kind(j) == kind]


def check_formal_job(fn: str, name: str) -> None:
    from arith.tools import run_formal
    if not ac.tool("sby"):
        pytest.skip("SymbiYosys (OSS CAD Suite) not found")
    d = ac.ARITH / fn
    jobs = {j["name"]: j for j in yaml.safe_load((d / "formal" / "jobs.yaml").read_text())["jobs"]}
    mutants = {m["name"]: m for m in yaml.safe_load((d / "verif" / "mutants.yaml").read_text())["mutants"]}
    with tempfile.TemporaryDirectory() as t:
        r = run_formal.run_job(fn, jobs[name], Path(t), mutants)
    assert r["ok"], f"{name}: expected {r['expected']}, got {r['status']}: {r['tail']}"


# ---- the packaged harness -------------------------------------------------------------------------------------
def run_harness(fn: str, rtl: Path, top: str, params: dict, lat: int, mode: str, extra: list[str] | None = None, n: int = 800) -> subprocess.CompletedProcess:
    h = ac.ARITH / fn / "harness"
    cmd = [sys.executable, str(h / "run_harness.py"), "--rtl", str(rtl), "--top", top, "--params", json.dumps(params), "--latency", str(lat), "--mode", mode,
           "--n", str(n)] + (extra or [])
    return subprocess.run(cmd, capture_output=True, text=True, cwd=h)


def harness_cases(fn: str) -> list:
    spec = ac.load_spec(fn)
    out = []
    for v, vd in spec["variants"].items():
        out.append(pytest.param(v, vd["exhaustive_points"][-1], "exhaustive", id=f"{v}-exhaustive"))
        out.append(pytest.param(v, vd["random_points"][0], "randomised", id=f"{v}-randomised"))
    return out


def check_harness_passes(fn: str, variant: str, params: dict, mode: str) -> None:
    """The harness, run standalone against the repository's own variant with the SystemVerilog checker beside it: it passes, and (random mode) meets its coverage targets."""
    spec = ac.load_spec(fn)
    vd = spec["variants"][variant]
    p = ac.merged_params(spec, variant, params)
    r = run_harness(fn, ac.ARITH / fn / vd["file"], vd["module"], p, ac.latency_of(spec, variant, p), mode, ["--checker"])
    assert r.returncode == 0, r.stdout[-700:] + r.stderr[-300:]
    if mode == "randomised":
        assert "bins met" in r.stdout and "NOT met" not in r.stdout, r.stdout[-500:]


def check_harness_catches_a_fault(fn: str, mutant: str) -> None:
    """A planted fault (a mutant of verif/mutants.yaml) makes the standalone harness fail, with the checker and without it."""
    d = ac.ARITH / fn
    spec = ac.load_spec(fn)
    m = next(x for x in yaml.safe_load((d / "verif" / "mutants.yaml").read_text())["mutants"] if x["name"] == mutant)
    vd = spec["variants"][m["variant"]]
    run0 = vd["mutant_run"][0]
    p = ac.merged_params(spec, m["variant"], run0["params"])
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / Path(vd["file"]).name
        src = (d / vd["file"]).read_text()
        assert src.count(m["old"]) == 1
        f.write_text(src.replace(m["old"], m["new"]))
        for extra in ([], ["--checker"]):
            r = run_harness(fn, f, vd["module"], p, ac.latency_of(spec, m["variant"], p), run0["mode"], extra)
            assert r.returncode == 1 and "FAIL" in r.stdout, r.stdout[-500:]


def check_harness_files(fn: str) -> None:
    from arith.tools import gen_harness
    for p, t in gen_harness.outputs(fn).items():
        assert p.exists() and p.read_text() == t, f"{p.relative_to(ac.ROOT)} is out of date: run python -m arith.tools.gen_harness"
    h = ac.ARITH / fn / "harness"
    for f in ("assertions.sv", "chk_top.sv", "coverage.yaml", "README.md", "run_harness.py"):
        assert (h / f).is_file()
    # the checker is a simulation checker (initial values, a display): it must parse and elaborate in Verilator; warnings are not a failure
    top = {"adder": "adder_checker", "multiplier": "mult_checker", "mac": "mac_checker"}[fn]
    r = subprocess.run([ac.tool("verilator"), "--lint-only", "-Wno-fatal", "-Wno-lint", "-Wno-style", "--top-module", top, str(h / "assertions.sv")] + [str(x) for x in sorted(h.glob("mac_ref.sv"))],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "%Error" not in r.stderr, r.stderr[-600:]
