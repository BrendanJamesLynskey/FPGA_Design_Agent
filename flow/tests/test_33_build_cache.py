"""Brief 33: the build cache (flow/build_cache.py), the result hash (flow/result_hash.py) and their wiring in
flow/run_vivado.sh. The decision tests are pure; the runner test uses a stand-in Vivado and runs only where
``systemd-run --user`` works (the build PC, not CI)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from flow import build_cache, result_hash

ROOT = Path(__file__).resolve().parents[2]
VIV = "/opt/Xilinx/2025.2/Vivado/bin/vivado"
INPUTS = """# generated
set top {top}
set part {xc7a100tcsg324-1}
set sources [list {/r/a.sv}]
set constraints [list {/r/a.xdc}]
set generics [list {BUILD_STAMP=32'h1234abcd}]
set out {OUT}
set ila 0
set power_env {-airflow 0}
set stop_after {STOP}
set timing_margin_ns 0
"""


def _build(d: Path, stop: str = "synth", sha: str = "s" * 64, reached: list[str] | None = None,
           extra: str = "") -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "inputs.tcl").write_text(INPUTS.replace("OUT", str(d)).replace("STOP", stop) + extra)
    (d / "prepare.json").write_text(json.dumps({"sources_sha256": sha}))
    if reached is not None:
        (d / "stages.txt").write_text("".join(f"{n:16s} {i:8.1f}\n" for i, n in enumerate(reached)))
    return d


def _done(d: Path, env: dict, threads: str = "1") -> Path:
    """Mark ``d`` as a finished build of its own inputs (its keys written, as run_vivado.sh does)."""
    (d / "flow_key.txt").write_text(build_cache.flow_key(d, VIV, threads, env) + "\n")
    (d / "synth_key.txt").write_text(build_cache.synth_key(d, VIV, threads) + "\n")
    for f in ("post_synth.dcp", "post_route.dcp"):
        (d / f).write_text("x")
    return d


SYNTH = ["read", "elaborate", "rtl_reports", "synth", "synth_reports"]
ROUTE = SYNTH + ["opt", "place", "phys_opt", "place_reports", "route", "reports"]


def test_keys_ignore_the_output_dir_and_stop_stage_but_not_the_inputs(tmp_path):
    env: dict = {}
    a = _build(tmp_path / "a", "synth")
    b = _build(tmp_path / "b", "bitstream")
    assert build_cache.flow_key(a, VIV, "1", env) == build_cache.flow_key(b, VIV, "1", env)
    assert build_cache.flow_key(a, VIV, "1", env) != build_cache.flow_key(a, VIV, "4", env)          # threads
    assert build_cache.flow_key(a, VIV, "1", env) != build_cache.flow_key(a, VIV.replace("2025.2", "2026.1"), "1", env)
    assert build_cache.flow_key(a, VIV, "1", env) != build_cache.flow_key(a, VIV, "1", {"FDA_XPROBE": "1"})
    c = _build(tmp_path / "c", sha="t" * 64)                                                        # source content
    assert build_cache.flow_key(a, VIV, "1", env) != build_cache.flow_key(c, VIV, "1", env)
    assert build_cache.synth_key(a, VIV, "1") != build_cache.synth_key(c, VIV, "1")
    # the ILA switch and the power environment change the flow key but not what synthesis reads
    d = _build(tmp_path / "d")
    (d / "inputs.tcl").write_text((d / "inputs.tcl").read_text().replace("set ila 0", "set ila 1"))
    assert build_cache.flow_key(a, VIV, "1", env) != build_cache.flow_key(d, VIV, "1", env)
    assert build_cache.synth_key(a, VIV, "1") == build_cache.synth_key(d, VIV, "1")


def test_reached_reads_the_last_step_of_each_stage(tmp_path):
    assert build_cache.reached(tmp_path) == 0
    assert build_cache.reached(_build(tmp_path / "s", reached=SYNTH)) == 1
    assert build_cache.reached(_build(tmp_path / "e", reached=SYNTH[:4])) == 0      # stopped inside synthesis reports
    assert build_cache.reached(_build(tmp_path / "r", reached=ROUTE)) == 3
    assert build_cache.reached(_build(tmp_path / "b", reached=ROUTE + ["bitstream"])) == 4
    assert build_cache.reached(_build(tmp_path / "x", reached=["resumed_route", "bitstream"])) == 4


def test_decisions(tmp_path):
    env: dict = {}
    prev = _done(_build(tmp_path / "prev", "route", reached=ROUTE), env)
    new = _build(tmp_path / "new", "synth")
    assert build_cache.decide(new, prev, None, "base", "synth", VIV, "1", env)["action"] == "hit"
    assert build_cache.decide(new, prev, None, "base", "route", VIV, "1", env)["action"] == "hit"
    assert build_cache.decide(new, prev, None, "base", "bitstream", VIV, "1", env)["action"] == "resume_route"
    # another thread count is another key: no reuse
    assert build_cache.decide(new, prev, None, "base", "route", VIV, "4", env)["action"] == "fresh"
    # the switch turns it off
    assert build_cache.decide(new, prev, None, "base", "route", VIV, "1", {"FDA_BUILD_CACHE": "0"})["action"] == "fresh"
    sprev = _done(_build(tmp_path / "sprev", "synth", reached=SYNTH), env)
    (sprev / "post_route.dcp").unlink()
    d = build_cache.decide(new, sprev, None, "base", "route", VIV, "1", env)
    assert d["action"] == "resume_synth" and d["resume_dir"] == str(sprev)
    # changed sources: fresh, and an incremental reference only when asked for
    changed = _build(tmp_path / "changed", sha="u" * 64)
    assert build_cache.decide(changed, prev, None, "base", "route", VIV, "1", env)["action"] == "fresh"
    assert "incremental_ref" not in build_cache.decide(changed, prev, None, "base", "route", VIV, "1", env)
    inc = build_cache.decide(changed, prev, None, "base", "route", VIV, "1", {"FDA_INCREMENTAL": "1"})
    assert inc["action"] == "fresh" and inc["incremental_ref"] == str(prev / "post_route.dcp")


def test_ila_starts_from_the_base_post_synth_checkpoint(tmp_path):
    env: dict = {}
    base = _done(_build(tmp_path / "base", "bitstream", reached=ROUTE + ["bitstream"]), env)
    ila = _build(tmp_path / "ila", "bitstream")
    (ila / "inputs.tcl").write_text((ila / "inputs.tcl").read_text().replace("set ila 0", "set ila 1"))
    d = build_cache.decide(ila, None, base, "ila", "bitstream", VIV, "1", env)
    assert d["action"] == "resume_synth" and d["resume_dir"] == str(base)
    other = _build(tmp_path / "ila2", "bitstream", sha="v" * 64)
    assert build_cache.decide(other, None, base, "ila", "bitstream", VIV, "1", env)["action"] == "fresh"


def test_main_appends_the_resume_lines(tmp_path, monkeypatch):
    env: dict = {}
    prev = _done(_build(tmp_path / "prev", "route", reached=ROUTE), env)
    new = _build(tmp_path / "new", "bitstream")
    monkeypatch.setenv("FDA_STOP_AFTER", "bitstream")
    for k in ("FDA_BUILD_CACHE", "FDA_XPROBE", "FDA_RESULT_HASH", "FDA_INCREMENTAL"):
        monkeypatch.delenv(k, raising=False)
    assert build_cache.main([str(new), "--prev", str(prev), "--vivado", VIV, "--threads", "1"]) == 0
    text = (new / "inputs.tcl").read_text()
    assert "set resume_from route" in text and f"set resume_dir {{{prev}}}" in text
    assert (new / "flow_key.txt").read_text().strip() == (prev / "flow_key.txt").read_text().strip()


def test_result_hash_ignores_line_order(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("C u/x SLICE_X0Y0 SLICE_X0Y0/AFF\nC u/y SLICE_X1Y0 SLICE_X1Y0/BFF\nN n1 { CLBLL_L_AQ NR1BEG0 }\n")
    b.write_text("N n1 { CLBLL_L_AQ NR1BEG0 }\nC u/y SLICE_X1Y0 SLICE_X1Y0/BFF\nC u/x SLICE_X0Y0 SLICE_X0Y0/AFF\n")
    ra, rb = result_hash.result_hash(a), result_hash.result_hash(b)
    assert ra == rb and ra["cells"] == 2 and ra["nets"] == 1
    b.write_text(b.read_text().replace("SLICE_X1Y0/BFF", "SLICE_X1Y0/CFF"))
    rb = result_hash.result_hash(b)
    assert rb["placement_sha256"] != ra["placement_sha256"] and rb["routing_sha256"] == ra["routing_sha256"]


# --- the runner, with a stand-in Vivado -------------------------------------------------------------------------
FAKE = r"""#!/usr/bin/env bash
# stand-in for vivado: follows build.tcl's stage log for the stop stage and resume point, records each call
inputs="${@: -1}"
out="$(sed -n 's/^set out {\(.*\)}$/\1/p' "$inputs")"
stop="$(sed -n 's/^set stop_after {\(.*\)}$/\1/p' "$inputs")"
resume="$(sed -n 's/^set resume_from \(.*\)$/\1/p' "$inputs")"
rdir="$(sed -n 's/^set resume_dir {\(.*\)}$/\1/p' "$inputs")"
echo "${resume:-fresh} $stop" >> "$FAKE_LOG"
echo "Vivado v2025.2 (64-bit)" > "$out/vivado.log"
log() { printf '%-16s %8.1f\n' "$1" 1.0 >> "$out/stages.txt"; }
case "$resume" in
  "") log synth_reports; echo x > "$out/post_synth.dcp" ;;
  synth) log resumed_synth; cp "$rdir/post_synth.dcp" "$out/" ;;
  route) log resumed_route; cp "$rdir/post_synth.dcp" "$rdir/post_route.dcp" "$out/" ;;
esac
[ "$stop" = synth ] && exit 0
if [ "$resume" != route ]; then log place_reports; [ "$stop" = place ] && exit 0; log reports; echo x > "$out/post_route.dcp"; fi
[ "$stop" = route ] && exit 0
log bitstream
"""


def _systemd_user() -> bool:
    if not shutil.which("systemd-run"):
        return False
    r = subprocess.run(["systemd-run", "--user", "--scope", "--quiet", "true"], capture_output=True)
    return r.returncode == 0


@pytest.mark.skipif(not _systemd_user(), reason="needs systemd-run --user (the build PC)")
def test_runner_reuses_builds(tmp_path):
    fake = tmp_path / "vivado"
    fake.write_text(FAKE)
    fake.chmod(0o755)
    log = tmp_path / "calls.txt"
    design = ROOT / "designs" / "t1_dimmer_counter"
    build = design / "build"
    keep = tmp_path / "kept_build"
    if build.exists():                       # never lose a real build that is lying in the checkout
        shutil.move(str(build), keep)
    try:
        env = dict(os.environ, VIVADO=str(fake), FAKE_LOG=str(log), MIN_AVAIL_GB="0", FDA_VIVADO_MAX="2",
                   FDA_TEST_VIVADO_RUNNING="0",     # the fake Vivado runs whatever real jobs other sessions have going
                   FDA_VIVADO_THREADS="1")
        env.pop("FDA_BUILD_CACHE", None)
        seq = ["synth", "synth", "route", "route", "bitstream", "bitstream"]
        actions = []
        for stop in seq:
            r = subprocess.run([str(ROOT / "flow" / "run_vivado.sh"), str(design), "base"], cwd=ROOT,
                               env=dict(env, FDA_STOP_AFTER=stop), capture_output=True, text=True)
            actions.append(next(l.split(": ")[-1] for l in r.stdout.splitlines() if "build cache:" in l))
        assert actions == ["fresh", "hit", "resume_synth", "hit", "resume_route", "hit"]
        assert log.read_text().split("\n")[:3] == ["fresh synth", "synth route", "route bitstream"]
        run = json.loads((build / "base" / "run.json").read_text())
        assert run["max_threads"] == 1 and run["cache"] == "resume_route" and len(run["cache_hits"]) == 1
        assert not (build / "base.prev").exists()
        # the ILA variant starts from the base build's post_synth.dcp
        r = subprocess.run([str(ROOT / "flow" / "run_vivado.sh"), str(design), "ila"], cwd=ROOT, env=env,
                           capture_output=True, text=True)
        assert "build cache: resume_synth" in r.stdout
    finally:
        if build.exists():
            shutil.rmtree(build)
        if keep.exists():
            shutil.move(str(keep), build)
