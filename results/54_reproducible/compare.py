#!/usr/bin/env python3
"""Brief 54: compare the reproducibility builds that repro.sh recorded, pair by pair, and write the results.

    python3 results/54_reproducible/compare.py <raw dir> [--out results/54_reproducible]

For each pair: the manifests (build ID, which identity fields differ), the bitstreams (flow/bitstream.py diff: every
differing header field, register write and frame word, with the configuration CRC recomputed), the placement and routing
hashes (flow/result_hash.py), the routed timing summary and utilisation reports line by line (the lines that differ are
listed, by their label, before anything is masked), and the gate numbers. Writes ``results.json`` and ``results.md``
and copies each build's small records (no bitstreams, no reports) to ``raw/<label>/``.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flow import bitstream, manifest  # noqa: E402

PAIRS = [
    ("reproducibility: T1, two clean trees in different directories, 4 threads", "t1_A_t4", "t1_B_t4"),
    ("reproducibility: c13 (11k LUT), two clean trees in different directories, 4 threads", "c13_A_t4", "c13_B_t4"),
    ("thread count: T1, 4 against 1 thread", "t1_A_t4", "t1_A_t1"),
    ("thread count: T1, 4 against 2 threads", "t1_A_t4", "t1_A_t2"),
    ("thread count: c13, 4 against 1 thread", "c13_A_t4", "c13_A_t1"),
    ("mutation: T1, one comment line changed in dimmer_counter.sv", "t1_A_t4", "t1_M_t4"),
]
RECORDS = ("manifest.json", "run.json", "gates.json", "result_hash.json", "stages.txt", "tool.txt", "rc.txt")
HEADER = re.compile(r"^\|\s*([A-Za-z][A-Za-z ]+?)\s*:")


def report_diff(a: Path, b: Path) -> dict:
    """Line-by-line comparison; each differing line is labelled by its report header key, or 'body'."""
    if not a.is_file() or not b.is_file():
        return {"present": False}
    la, lb = a.read_text(errors="replace").splitlines(), b.read_text(errors="replace").splitlines()
    diffs = []
    for i in range(max(len(la), len(lb))):
        x = la[i] if i < len(la) else None
        y = lb[i] if i < len(lb) else None
        if x != y:
            m = HEADER.match(x or "") or HEADER.match(y or "")
            diffs.append({"line": i + 1, "label": m.group(1) if m else "body", "a": x, "b": y})
    labels = sorted({d["label"] for d in diffs})
    return {"present": True, "lines_a": len(la), "lines_b": len(lb), "lines_differ": len(diffs), "labels": labels,
            "only_header": all(d["label"] != "body" for d in diffs), "first": diffs[:6]}


def identity_diff(ma: dict, mb: dict) -> list[str]:
    ia, ib = manifest.identity(ma), manifest.identity(mb)
    out = []
    for k in sorted(set(ia) | set(ib)):
        if ia.get(k) != ib.get(k):
            if isinstance(ia.get(k), dict) and isinstance(ib.get(k), dict):
                for kk in sorted(set(ia[k]) | set(ib[k])):
                    if ia[k].get(kk) != ib[k].get(kk):
                        out.append(f"{k}.{kk}")
            else:
                out.append(k)
    return out


def gate_numbers(g: dict) -> dict:
    t, u = g.get("timing") or {}, g.get("utilization") or {}
    return {"pass": g.get("pass"), "wns_ns": t.get("wns_ns"), "tns_ns": t.get("tns_ns"), "whs_ns": t.get("whs_ns"),
            "lut": u.get("lut"), "ff": u.get("ff"), "bram_tile": u.get("bram_tile"), "dsp": u.get("dsp"),
            "power_w": (g.get("power") or {}).get("total_w")}


def load(raw: Path, label: str) -> dict:
    d = raw / label
    rec = {"label": label, "dir": d}
    for n in ("manifest.json", "run.json", "gates.json", "result_hash.json"):
        f = d / n
        rec[n.split(".")[0]] = json.loads(f.read_text()) if f.is_file() else None
    bits = sorted(d.glob("*.bit"))
    rec["bit"] = bits[0] if bits else None
    return rec


def compare(raw: Path, title: str, la: str, lb: str) -> dict:
    a, b = load(raw, la), load(raw, lb)
    r: dict = {"title": title, "a": la, "b": lb}
    if not (a["manifest"] and b["manifest"] and a["bit"] and b["bit"]):
        r["missing"] = [x["label"] for x in (a, b) if not (x["manifest"] and x["bit"])]
        return r
    ma, mb = a["manifest"], b["manifest"]
    r["build_id"] = {"a": ma["build_id"], "b": mb["build_id"], "same": ma["build_id"] == mb["build_id"]}
    r["identity_fields_differ"] = identity_diff(ma, mb)
    r["build_dirs"] = [ma.get("build_dir"), mb.get("build_dir")]
    r["threads"] = [ma["settings"]["threads"], mb["settings"]["threads"]]
    r["manifest_check"] = {"a": manifest.check(ma, a["bit"]), "b": manifest.check(mb, b["bit"])}
    d = bitstream.diff(a["bit"], b["bit"])
    for w in d["register_writes"]:
        w.pop("_data", None)
    r["bitstream"] = d
    ha, hb = a["result_hash"] or {}, b["result_hash"] or {}
    r["result_hash"] = {"a": {k: (ha.get(f"{k}_sha256") or "") for k in ("placement", "routing")},
                        "b": {k: (hb.get(f"{k}_sha256") or "") for k in ("placement", "routing")}}
    r["result_hash"]["same"] = r["result_hash"]["a"] == r["result_hash"]["b"] and bool(ha)
    r["timing_summary"] = report_diff(a["dir"] / "timing_summary.rpt", b["dir"] / "timing_summary.rpt")
    r["utilization"] = report_diff(a["dir"] / "utilization.rpt", b["dir"] / "utilization.rpt")
    r["gates"] = {"a": gate_numbers(a["gates"] or {}), "b": gate_numbers(b["gates"] or {})}
    r["wall_s"] = [(a["run"] or {}).get("wall_s"), (b["run"] or {}).get("wall_s")]
    r["scope_anon_peak_mib"] = [(a["run"] or {}).get("scope_anon_peak_mib"), (b["run"] or {}).get("scope_anon_peak_mib")]
    return r


def md(results: list[dict]) -> str:
    out = ["# Brief 54: reproducibility, thread count and mutation (generated by compare.py from raw/)", "",
           "Vivado 2026.1 (Basic licence tier), non-project flow (`flow/build.tcl`), fresh builds (`FDA_BUILD_CACHE=0`),",
           "`FDA_RESULT_HASH=1`, each tree a clean checkout of the same commit in its own directory.", ""]
    for r in results:
        out += [f"## {r['title']}", "", f"`{r['a']}` against `{r['b']}`.", ""]
        if r.get("missing"):
            out += [f"Not compared: no build or bitstream for {', '.join(r['missing'])}.", ""]
            continue
        d = r["bitstream"]
        bid = r["build_id"]
        out.append(f"- Build ID: {bid['a']} and {bid['b']} ({'same' if bid['same'] else 'different'}); identity fields "
                   f"that differ: {', '.join(r['identity_fields_differ']) or 'none'}.")
        out.append(f"- Manifest checks (build ID = hash, USR_ACCESS = build ID): "
                   f"{'clean' if not (r['manifest_check']['a'] or r['manifest_check']['b']) else r['manifest_check']}.")
        if d["identical"]:
            out.append(f"- Bitstreams: **byte-identical** ({d['sha256_a'][:16]}...).")
        else:
            out.append(f"- Bitstreams: not identical; {d['bytes_differ']} bytes differ"
                       + (f" (lengths {d.get('length_a')} and {d.get('length_b')})" if d["bytes_differ"] is None else "")
                       + f"; same packet sequence: {d['same_packet_sequence']}; kinds: {', '.join(d['explained']['kinds'])}.")
            for h in d["header"]:
                out.append(f"  - header field `{h['field']}`: `{h['a']}` / `{h['b']}`")
            for w in d["register_writes"]:
                if w["reg"] == "FDRI":
                    out.append(f"  - frame data (FDRI write {w['index']}): {w['words_differ']} words in "
                               f"{w['frames_touched']} frames differ (first frames {w['first_frames'][:8]})")
                else:
                    out.append(f"  - register {w['reg']} (write {w['index']}, file bytes {w['bytes_a']}): "
                               f"{w['a']} / {w['b']}")
            out.append(f"  - configuration CRC recomputed from the packets matches the file's CRC words: "
                       f"{r['bitstream']['crc_recomputed_match']}")
        rh = r["result_hash"]
        out.append(f"- Placement and routing hashes: {rh['a'].get('placement', '')[:12]}/{rh['a'].get('routing', '')[:12]} and "
                   f"{rh['b'].get('placement', '')[:12]}/{rh['b'].get('routing', '')[:12]} ({'same' if rh['same'] else 'different'}).")
        for rep in ("timing_summary", "utilization"):
            x = r[rep]
            if not x.get("present"):
                out.append(f"- `{rep}.rpt`: missing")
                continue
            out.append(f"- `{rep}.rpt`: {x['lines_differ']} of {x['lines_a']} lines differ"
                       + (f", all in the header ({', '.join(x['labels'])})" if x["lines_differ"] and x["only_header"]
                          else (f" (labels {', '.join(x['labels'])})" if x["lines_differ"] else "")) + ".")
        ga, gb = r["gates"]["a"], r["gates"]["b"]
        out.append(f"- Gates and numbers: {ga} / {gb}.")
        out.append(f"- Wall time s: {r['wall_s']}; scope anonymous peak MiB: {r['scope_anon_peak_mib']}; threads {r['threads']}.")
        out.append("")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("raw", type=Path)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    a = ap.parse_args(argv)
    results = [compare(a.raw, *p) for p in PAIRS]
    (a.out / "results.json").write_text(json.dumps(results, indent=1, default=str) + "\n")
    (a.out / "results.md").write_text(md(results))
    for d in sorted(p for p in a.raw.iterdir() if p.is_dir()):
        dst = a.out / "raw" / d.name
        dst.mkdir(parents=True, exist_ok=True)
        for n in RECORDS:
            if (d / n).is_file():
                shutil.copyfile(d / n, dst / n)
    print((a.out / "results.md").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
