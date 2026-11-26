"""Brief 213: the regrade over every recorded accepted design we have (sim only). For each design directory: copy it to a scratch folder, run its own bench with
the model-call recording on (as the R3 arm's simulate tool does), then run the regrade (calibration replay, then fresh stimulus) and write one JSON line.
  python results/213_repair_feedback/sweep/regrade_sweep.py OUT.jsonl LABEL=DESIGN_DIR [LABEL=DESIGN_DIR ...]
"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from flow import divergence, regrade  # noqa: E402

out, items = Path(sys.argv[1]), sys.argv[2:]


def run(argv, env, timeout):
    p = subprocess.run(argv, env={**os.environ, **env}, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout + p.stderr


for it in items:
    label, _, src = it.partition("=")
    t0 = time.time()
    scratch = Path(tempfile.mkdtemp(prefix="rg_sweep_", dir=os.environ.get("TMPDIR", "/tmp")))
    d = scratch / "design"
    shutil.copytree(src, d, ignore=shutil.ignore_patterns("build", "__pycache__", "sim_build"))
    (d / "build" / "verif").mkdir(parents=True)
    env = {**os.environ, "FDA_MODEL_RECORD": str(divergence.record_path(d)), "SIM": "icarus", "FDA_SIM_BUILD_ROOT": str(scratch / "simroot"),
           "PYTHONPATH": str(ROOT)}
    rec: dict = {"label": label}
    tests = sorted((d / "tests").glob("test_*_rtl.py"))
    if not tests or not list((d / "rtl").glob("*.sv")):
        rec["status"] = "no_bench_or_rtl"
    else:
        try:
            p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", str(tests[0])], env=env, cwd=str(ROOT),
                               capture_output=True, text=True, timeout=900)
            rec["bench_passed"] = p.returncode == 0
            if p.returncode == 0:
                r = regrade.run_regrade(d, run, seed=213, rtl_files=sorted((d / "rtl").glob("*.sv")), timeout=600)
                rec.update({k: v for k, v in r.items() if k != "digest"})
                rec["digest_head"] = (r.get("digest") or "")[:300]
            else:
                rec["status"] = "bench_failed_here"
                rec["tail"] = (p.stdout + p.stderr)[-300:]
        except subprocess.TimeoutExpired:
            rec["status"] = "timeout"
    rec["seconds"] = round(time.time() - t0)
    with out.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    shutil.rmtree(scratch, ignore_errors=True)
