#!/usr/bin/env python3
"""Merge the per-run coverage dumps of the b96 UVM bench and write the coverage report (brief 112).

    cov_merge.py <out dir> <cov dump files and run logs...>

A dump (written by pcs_mac_cov at the end of a run) has lines "point|bin|hits"; a run log is read for its "SVA_COV <instance> <name> <hits>" lines.
Vivado 2026.1 Basic refuses xcrg, so xsim's own coverage database cannot be merged; this is the merge. Writes <out dir>/coverage_merged.tsv (every
bin, merged hits, the number of runs that hit it), <out dir>/sva_cover.tsv and <out dir>/coverage_report.md (per-point percentages, the holes, the
waivers from cov_waivers.tsv with their reasons). Standard library only."""
import collections
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def main(argv):
    out = Path(argv[1]); out.mkdir(parents=True, exist_ok=True)
    hits = collections.OrderedDict()
    runs_hit = collections.Counter()
    sva = collections.Counter()
    nruns = 0
    for fn in argv[2:]:
        p = Path(fn)
        if p.suffix == ".txt":
            nruns += 1
            for line in p.read_text().splitlines():
                key, _, n = line.rpartition("|")
                if not key:
                    continue
                hits[key] = hits.get(key, 0) + int(n)
                if int(n) > 0:
                    runs_hit[key] += 1
        else:
            for line in p.read_bytes().decode("utf-8", "replace").splitlines():
                if line.startswith("SVA_COV "):
                    _t, inst, name, n = line.split()
                    inst = inst.split(".", 1)[1] if "." in inst else inst
                    sva[f"{inst} {name}"] += int(n)
    waivers = {}
    wf = HERE / "cov_waivers.tsv"
    if wf.exists():
        for line in wf.read_text().splitlines():
            if line and not line.startswith("#"):
                key, why = line.split("\t", 1)
                waivers[key] = why
    with open(out / "coverage_merged.tsv", "w") as f:
        f.write("point|bin\thits\truns_hit\n")
        for k, n in hits.items():
            f.write(f"{k}\t{n}\t{runs_hit[k]}\n")
    with open(out / "sva_cover.tsv", "w") as f:
        f.write("instance and cover\thits\n")
        for k, n in sorted(sva.items()):
            f.write(f"{k}\t{n}\n")
    points = collections.OrderedDict()
    for k, n in hits.items():
        pt, b = k.split("|", 1)
        points.setdefault(pt, []).append((b, n))
    tot = hit = wtot = 0
    lines = []
    holes = []
    waived_rows = []
    for pt, bins in points.items():
        h = sum(1 for _b, n in bins if n > 0)
        w = sum(1 for b, n in bins if n == 0 and f"{pt}|{b}" in waivers)
        tot += len(bins); hit += h; wtot += w
        lines.append(f"| {pt} | {len(bins)} | {h} | {w} | {100.0 * h / len(bins):.1f} % | {100.0 * h / max(1, len(bins) - w):.1f} % |")
        for b, n in bins:
            if n == 0:
                if f"{pt}|{b}" in waivers:
                    waived_rows.append(f"| {pt} | {b} | {waivers[f'{pt}|{b}']} |")
                else:
                    holes.append(f"| {pt} | {b} |")
    rep = [f"# Functional coverage, merged over {nruns} runs", "",
           f"Bins hit {hit} of {tot} ({100.0 * hit / tot:.1f} %). Bins waived with a reason: {wtot}. Open holes: {len(holes)}. "
           f"Coverage excluding waived bins: {100.0 * hit / (tot - wtot):.1f} %.", "",
           "| coverage point | bins | hit | waived | hit of all | hit of reachable |", "|---|---|---|---|---|---|"] + lines + ["", "## Open holes", ""]
    rep += (["| point | bin |", "|---|---|"] + holes) if holes else ["None."]
    rep += ["", "## Waived bins (not reachable on this bench, with the reason)", ""]
    rep += (["| point | bin | reason |", "|---|---|---|"] + waived_rows) if waived_rows else ["None."]
    rep += ["", "## SVA cover properties (hits summed over all runs)", "", "| instance and cover | hits |", "|---|---|"]
    rep += [f"| {k} | {n} |" for k, n in sorted(sva.items())]
    (out / "coverage_report.md").write_text("\n".join(rep) + "\n")
    print(f"merged {nruns} runs: {hit}/{tot} bins hit, {wtot} waived, {len(holes)} open holes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
