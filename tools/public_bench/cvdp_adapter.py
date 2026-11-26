"""Brief 215: adapter between the CVDP non-agentic code-generation problems and the FPGA agent (stages 0 to 2, simulation only).

Stdlib only. The CVDP dataset and harness are NOT in this repository (Apache-2.0 harness, CC BY 4.0 / Apache-2.0 dataset; fetched
at run time, pins in results/215_public_benchmarks/README.md). Subcommands:

  sample   --data F --seed N --per-category c002=14,... [--exclude ids.txt]   print a stratified sample (problem ids, one per line)
  prepare  --data F --id ID --out DIR       write DIR/spec.md and DIR/data/<provided files> for `python -m agent run DIR/spec.md`
  collect  --data F --out DS.jsonl --run ID=DESIGN_DIR ...   copy each run's rtl files into the problem's output.context and
                                            write a one-line-per-problem dataset the CVDP harness scores (golden mode, no model)
  score    --harness DIR --python PY --dataset DS.jsonl --work DIR     run the CVDP harness on that dataset, print id,pass lines

The agent's own bench never counts: scoring is the CVDP harness's hidden tests only (house rule: never our own tests).
"""
from __future__ import annotations

import argparse, json, os, random, subprocess, sys
from pathlib import Path


def load(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def by_id(rows):
    return {r["id"]: r for r in rows}


def cmd_sample(a):
    rows = load(a.data)
    excl = set(Path(a.exclude).read_text().split()) if a.exclude else set()
    want = {k: int(v) for k, v in (x.split("=") for x in a.per_category.split(","))}
    rng = random.Random(a.seed)
    out = []
    for cat in sorted(want):
        pool = sorted(r["id"] for r in rows if r["categories"][0] == cat and r["id"] not in excl)
        out += sorted(rng.sample(pool, want[cat]))
    print("\n".join(out))


def targets(row):
    return list(row["output"]["context"].keys())


def spec_text(row):
    inp = row["input"]
    tg = targets(row)
    mod = [k for k in inp.get("context", {})]
    L = [f"# {row['id']}", "",
         "This is a standalone RTL module task from a public benchmark, not a board design. There is no board top, no pins, no "
         "constraints file and no test shell: the deliverable is the module(s) described below, in the file(s) named at the end. "
         "Keep every module, port, parameter and signal name exactly as the task gives it; a hidden testbench instantiates the "
         "module by those names. The hidden testbench compiles ONLY the file(s) named under 'Files to deliver': put every module "
         "the design needs, submodules included, inside those file(s); any other file is not seen and the design then fails.", "", "## Task", "", inp["prompt"].strip(), ""]
    if mod:
        L += ["## Provided files (the current design; the files to deliver replace them)", ""]
        for k in mod:
            L += [f"### {k}", "```systemverilog", inp["context"][k].rstrip(), "```", ""]
    L += ["## Files to deliver", ""]
    for k in tg:
        L.append(f"- `{k}`: write it at exactly this relative path inside the design directory, with this exact file name.")
    L.append("")
    return "\n".join(L)


def cmd_prepare(a):
    row = by_id(load(a.data))[a.id]
    out = Path(a.out)
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "spec.md").write_text(spec_text(row))
    for k, v in row["input"].get("context", {}).items():
        p = out / "data" / k
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(v)
    print(out / "spec.md")


def cmd_collect(a):
    rows = by_id(load(a.data))
    res = []
    for item in a.run:
        pid, d = item.split("=", 1)
        row = json.loads(json.dumps(rows[pid]))
        got, missing = {}, []
        for k in targets(row):
            f = Path(d) / k
            if not f.is_file() and a.ext_map:      # post hoc variant (amendment 3): the flow writes .sv for a task that names .v; same stem, same text
                alt = f.with_suffix(".sv" if f.suffix == ".v" else ".v")
                if alt.is_file():
                    f = alt
                    print(f"{pid} ext_map {k} <- {alt.name}", file=sys.stderr)
            if f.is_file():
                got[k] = f.read_text(errors="replace")
            else:
                missing.append(k)
                got[k] = ""          # a missing file is an empty file: the hidden tests fail it
        row["output"]["context"] = got
        row["output"]["response"] = ""
        res.append(row)
        print(f"{pid} files_found={len(got) - len(missing)}/{len(got)} missing={missing}", file=sys.stderr)
    Path(a.out).write_text("".join(json.dumps(r) + "\n" for r in res))


def cmd_score(a):
    work = Path(a.work).resolve()
    ds = Path(a.dataset).resolve()
    env = dict(os.environ)
    p = subprocess.run([a.python, "run_benchmark.py", "-f", str(ds), "-p", str(work), "-t", str(a.threads)], cwd=a.harness, env=env,
                       capture_output=True, text=True)
    (work.parent / (work.name + ".harness.log")).write_text(p.stdout[-20000:] + p.stderr[-5000:])
    rep = json.loads((work / "report.json").read_text())
    ids_pass = {t["test_id"] for t in rep["test_details"]["passing_tests"]}
    ids_fail = {t["test_id"] for t in rep["test_details"]["failing_tests"]}
    for r in load(ds):
        print(f"{r['id']},{'pass' if r['id'] in ids_pass else 'fail' if r['id'] in ids_fail else 'noresult'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("sample"); s.add_argument("--data", required=True); s.add_argument("--seed", type=int, required=True)
    s.add_argument("--per-category", required=True); s.add_argument("--exclude"); s.set_defaults(f=cmd_sample)
    s = sp.add_parser("prepare"); s.add_argument("--data", required=True); s.add_argument("--id", required=True)
    s.add_argument("--out", required=True); s.set_defaults(f=cmd_prepare)
    s = sp.add_parser("collect"); s.add_argument("--data", required=True); s.add_argument("--out", required=True)
    s.add_argument("--run", nargs="+", required=True)
    s.add_argument("--ext-map", action="store_true", help="use the same-stem .sv file for a missing .v target (and the reverse)"); s.set_defaults(f=cmd_collect)
    s = sp.add_parser("score"); s.add_argument("--harness", required=True); s.add_argument("--python", required=True)
    s.add_argument("--dataset", required=True); s.add_argument("--work", required=True); s.add_argument("--threads", type=int, default=2)
    s.set_defaults(f=cmd_score)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
