#!/usr/bin/env python3
"""Release bundles: everything that identifies and justifies one bitstream, in one checked folder.

A *bundle* is one folder holding a bitstream and the evidence for it, with a checksum file over everything in it.

    python3 flow/release.py make designs/<name> [--variant base|ila] [--out <dir>] [--force] [--trace <trace.json>] [--allow-dirty]
    python3 flow/release.py check <bundle dir> [--allow-dirty] [--json <file>]

``make`` collects, from ``designs/<name>/build/<variant>/`` (a build by flow/run_vivado.sh):

- the bitstream (and the ``.ltx`` of an ILA build);
- ``manifest.json`` (flow/manifest.py), ``gates.json`` and ``run.json``;
- the key reports under ``reports/``: timing summary, check_timing, utilisation, power, DRC, methodology, CDC and the
  routed QoR assessment (or the note that the licence tier did not allow it);
- the traceability matrix (``trace.json`` and ``trace.md``) when one is given or found beside the build;
- the review pages (``build/review/*.html``) when the design has them;
- ``RELEASE.md`` (what it is, its build ID, the gates, timing, utilisation and power, and how to check it) and
  ``SHA256SUMS`` (``sha256sum -c`` format, every other file).

It refuses a build whose gates failed, whose manifest is inconsistent or whose bitstream does not carry its build ID,
one whose tree state is unknown, and (unless ``--allow-dirty``) one built from a tree with uncommitted changes. Text files
are copied with the machine's details replaced: the repository root by ``$ROOT``, the build directory by ``$BUILD``, the
home directory by ``$HOME`` and the host name on report header lines (``| Host :``) by ``<host>``. The default output is
``build/release/<design>_<variant>_<build ID>/``. An existing ``--out`` directory is replaced only if it is a previous
bundle (it holds ``SHA256SUMS`` and ``RELEASE.md``) and ``--force`` is given; the checkout, any of its parents and the
build directory are never used as ``--out``.

``check`` needs nothing but the bundle: every file in SHA256SUMS is present with that hash and no file is unlisted; the
gates in gates.json passed; the manifest's build ID is the hash of its identity; the bitstream's USR_ACCESS word is that
build ID and its SHA-256 is the manifest's; the configuration CRC recomputed from the bitstream's packets matches its
CRC words; RELEASE.md names the same build ID; the tree was clean (unless ``--allow-dirty``). It prints one line per check
and exits 1 if any fails.

**Integrity, not authenticity.** ``SHA256SUMS`` is inside the bundle, so anyone who edits a file and recomputes the sums
gets a bundle that passes, as long as the edit does not touch the fields the build ID covers (for example the commit,
the gate results or the dirty flag). The check shows that the bundle is complete and self-consistent and that the
bitstream is the one the manifest identifies; it does not show who made it. A signature over ``SHA256SUMS``, kept
outside the bundle, would add that.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flow import bitstream, manifest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ("timing_summary.rpt", "check_timing.rpt", "utilization.rpt", "power.rpt", "drc.rpt", "methodology.rpt",
           "cdc.rpt", "qor_assessment_route.rpt", "qor_unavailable_route.txt")
RECORDS = ("manifest.json", "gates.json", "run.json")
SUMS = "SHA256SUMS"


class ReleaseError(Exception):
    pass


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _find_trace(design: Path, bdir: Path, given: Path | None) -> Path | None:
    if given is not None:
        if not given.is_file():
            raise ReleaseError(f"no traceability matrix {given}")
        return given
    for c in (bdir / "trace.json", design / "build" / "trace.json", design / "build" / "trace" / "trace.json"):
        if c.is_file():
            return c
    return None


def _summary(gates: dict) -> dict[str, Any]:
    t = gates.get("timing") or {}
    u = gates.get("utilization") or {}
    pw = gates.get("power") or {}
    env = gates.get("power_environment") or {}
    return {"wns": t.get("wns_ns"), "tns": t.get("tns_ns"), "whs": t.get("whs_ns"), "ths": t.get("ths_ns"),
            "luts": u.get("lut"), "ffs": u.get("ff"), "bram": u.get("bram_tile"), "dsp": u.get("dsp"),
            "power_w": pw.get("total_w"), "tj_c": env.get("junction_c")}


_HOST_LINE = re.compile(r"^(\|\s*Host\s*:\s*)\S+", re.M)


def _scrub(text: str, root: Path, bdir: Path) -> str:
    """The machine's details out of a text file: build directory, repository root, home directory, host name."""
    for real, alias in ((str(bdir.resolve()), "$BUILD"), (str(bdir), "$BUILD"), (str(root.resolve()), "$ROOT"),
                        (str(root), "$ROOT"), (str(Path.home()), "$HOME")):
        if real and real != "/":
            text = text.replace(real, alias)
    # the host name only where a report header names it ("| Host : <name> running ..."), never elsewhere in the text
    return _HOST_LINE.sub(lambda m: m.group(1) + "<host>", text)


def _repo_root(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / "flow" / "manifest.py").is_file():
            return d
    return ROOT


def _prepare_out(out: Path, root: Path, bdir: Path, force: bool) -> None:
    o = out.resolve()
    protected = [root.resolve(), bdir.resolve()]
    if any(o == p or o in p.parents for p in protected) or o == Path.home().resolve() or o == Path("/"):
        raise ReleaseError(f"--out {out} is the checkout, a parent of it, or the build directory: choose another folder")
    if o.exists():
        if not o.is_dir():
            raise ReleaseError(f"--out {out} exists and is not a directory")
        if any(o.iterdir()):
            previous = (o / SUMS).is_file() and (o / "RELEASE.md").is_file()
            if not previous:
                raise ReleaseError(f"--out {out} exists, is not empty and is not a release bundle: nothing was changed")
            if not force:
                raise ReleaseError(f"--out {out} holds a previous bundle; pass --force to replace it")
            shutil.rmtree(o)
    o.mkdir(parents=True, exist_ok=True)


def release_md(m: dict, gates: dict, files: list[str]) -> str:
    s = _summary(gates)
    tools = m.get("tools") or {}
    fl = m.get("flow") or {}
    failed = gates.get("first_failed_stage")
    lines = [
        f"# Release: {m['design'].split('/')[-1]} ({m['variant']}), build ID `{m['build_id']}`", "",
        "The release record of one build. `SHA256SUMS` lists every other file; the check below verifies the bundle.", "",
        f"- Design `{m['design']}`, top `{m['top']}`, part `{m['part']}`.",
        f"- **Build ID `{m['build_id']}`**: the first 8 hex digits of the SHA-256 of the manifest's identity part (the "
        "keys in `build_id_covers`). The bitstream carries it in its USR_ACCESS register (read over JTAG as "
        "REGISTER.USR_ACCESS). Full hash:",
        f"  `{m['build_id_sha256']}`",
        f"- Flow commit `{fl.get('commit')}`{' (**dirty tree**)' if fl.get('dirty') else ' (clean tree)'}; "
        f"knowledge-bank pin `{m.get('kb_pin')}`.",
        f"- Vivado {tools.get('vivado')} (ran {tools.get('vivado_ran')}, SW build {tools.get('vivado_sw_build')}, "
        f"licence tier {tools.get('vivado_licence_tier')}); {m['settings']['threads']} threads; directives "
        + ", ".join(f"{k} {v}" for k, v in m['settings']['directives'].items()) + ".",
        f"- Gates: **{'pass' if gates.get('pass') else 'FAIL'}**" + (f" (first failed stage {failed})" if failed else "") + ".",
        f"- Timing: WNS {s['wns']} ns, TNS {s['tns']} ns, WHS {s['whs']} ns, THS {s['ths']} ns.",
        f"- Utilisation: {s['luts']} LUT, {s['ffs']} FF, {s['bram']} block RAM tiles, {s['dsp']} DSP.",
        f"- Power: {s['power_w']} W on chip, junction {s['tj_c']} C (estimated by report_power at the board's assumed "
        "ambient and airflow).",
        *([f"- **Incremental build**: placed and routed against a reference checkpoint (SHA-256 "
           f"`{(m.get('incremental') or {}).get('used')}`), not from scratch."]
          if (m.get("incremental") or {}).get("status") == "used" else []),
        *([f"- Incremental reference hashed, not used: the build ID covers a reference checkpoint (SHA-256 "
           f"`{m['settings']['incremental_ref_sha256']}`), but the build resumed from a cached checkpoint instead."]
          if (m.get("incremental") or {}).get("status") == "reference hashed, not used" else []),
        "",
        "## Files", "",
        *[f"- `{f}`" for f in files],
        f"- `{SUMS}`", "",
        "## Check", "",
        "From a clone of FPGA_Design_Agent:", "",
        "```",
        "sha256sum -c SHA256SUMS",
        "python3 flow/release.py check <this folder>     # sums, gates, build ID in the manifest and in the bitstream",
        "```", "",
        "The check proves the bundle is complete and self-consistent (integrity), not who made it (authenticity): the "
        "sums are inside the bundle.", "",
    ]
    return "\n".join(lines)


def make(design: Path, variant: str = "base", out: Path | None = None, trace: Path | None = None,
         allow_dirty: bool = False, force: bool = False) -> Path:
    bdir = design / "build" / variant
    mf = bdir / "manifest.json"
    if not mf.is_file():
        raise ReleaseError(f"no manifest.json in {bdir}: build it with flow/run_vivado.sh (builds made before manifests "
                           "existed cannot be bundled)")
    m = json.loads(mf.read_text())
    bit = bdir / f"{m['top']}.bit"
    if not bit.is_file():
        raise ReleaseError(f"no bitstream {bit}")
    errs = manifest.check(m, bit)
    if errs:
        raise ReleaseError("; ".join(errs))
    gates = json.loads((bdir / "gates.json").read_text())
    if not gates.get("pass"):
        raise ReleaseError(f"the gates failed (first failed stage {gates.get('first_failed_stage')}): no release")
    dirty = (m.get("flow") or {}).get("dirty")
    if dirty is None:
        raise ReleaseError("the manifest does not say whether the tree was clean (git was not available at build time)")
    if dirty and not allow_dirty:
        raise ReleaseError("built from a tree with uncommitted changes; commit, rebuild, or pass --allow-dirty")
    name = f"{design.name}_{variant}_{m['build_id']}"
    root = _repo_root(bdir.resolve())
    out = out or (ROOT / "build" / "release" / name)
    _prepare_out(out, root, bdir, force)
    files: list[str] = []

    def put(src: Path, rel: str) -> None:
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix in (".bit", ".ltx"):
            shutil.copyfile(src, dst)
        else:
            dst.write_text(_scrub(src.read_text(errors="replace"), root, bdir))
        files.append(rel)

    put(bit, bit.name)
    ltx = bdir / f"{m['top']}.ltx"
    if variant == "ila":
        if not ltx.is_file():
            raise ReleaseError(f"no probes file {ltx}")
        put(ltx, ltx.name)
    for r in RECORDS:
        if (bdir / r).is_file():
            put(bdir / r, r)
    for r in REPORTS:
        if (bdir / r).is_file():
            put(bdir / r, f"reports/{r}")
    tr = _find_trace(design, bdir, trace)
    if tr is not None:
        put(tr, "trace/trace.json")
        if tr.with_suffix(".md").is_file():
            put(tr.with_suffix(".md"), "trace/trace.md")
    rev = design / "build" / "review"
    for h in sorted(rev.glob("*.html")) if rev.is_dir() else []:
        put(h, f"review/{h.name}")
    (out / "RELEASE.md").write_text(release_md(m, gates, files))
    files.append("RELEASE.md")
    (out / SUMS).write_text("".join(f"{_sha(out / f)}  {f}\n" for f in sorted(files)))
    return out


def check(bundle: Path, allow_dirty: bool = False) -> dict[str, Any]:
    """Every check of a bundle, using only its own files."""
    res: dict[str, dict[str, Any]] = {}

    def rec(name: str, ok: bool, detail: str = "") -> None:
        res[name] = {"pass": bool(ok), "detail": detail}

    sums = bundle / SUMS
    listed: dict[str, str] = {}
    if sums.is_file():
        for line in sums.read_text().splitlines():
            if line.strip():
                h, _, f = line.partition("  ")
                listed[f.strip()] = h.strip()
    bad = [f for f, h in listed.items() if not (bundle / f).is_file() or _sha(bundle / f) != h]
    present = sorted(str(p.relative_to(bundle)) for p in bundle.rglob("*") if p.is_file() and p.name != SUMS)
    unlisted = [f for f in present if f not in listed]
    rec("sha256sums", sums.is_file() and not bad and not unlisted and bool(listed),
        f"{len(listed)} files listed" + (f"; wrong or missing: {bad}" if bad else "")
        + (f"; not listed: {unlisted}" if unlisted else ""))
    try:
        m = json.loads((bundle / "manifest.json").read_text())
        gates = json.loads((bundle / "gates.json").read_text())
    except (OSError, ValueError) as e:
        rec("records_readable", False, str(e))
        return {"bundle": str(bundle), "pass": False, "checks": res}
    rec("gates_pass", gates.get("pass") is True, f"first failed stage {gates.get('first_failed_stage')}")
    bit = bundle / f"{m.get('top')}.bit"
    bid, _ = manifest.build_id_of(m)
    _, full = manifest.build_id_of(m)
    rec("build_id_is_manifest_hash", m.get("build_id") == bid and m.get("build_id_sha256") == full,
        f"manifest {m.get('build_id')} / {str(m.get('build_id_sha256'))[:16]}..., recomputed {bid} / {full[:16]}...")
    try:
        ua = bitstream.usr_access(bit) if bit.is_file() else None
    except bitstream.BitError as e:
        ua = None
        rec("bitstream_readable", False, str(e))
    rec("bitstream_usr_access_is_build_id", ua is not None and ua.lower() == str(m.get("build_id")).lower(),
        f"USR_ACCESS {ua}, build ID {m.get('build_id')}")
    if bit.is_file():
        try:
            info = bitstream.info(bit)
            rec("bitstream_crc", bool(info["crc_checks"]) and info["crc_all_match"],
                f"{len(info['crc_checks'])} CRC words, recomputed from the packets")
        except bitstream.BitError as e:
            rec("bitstream_crc", False, str(e))
    rec_bit = ((m.get("outputs") or {}).get("bit") or {}).get("sha256")
    rec("bitstream_hash_in_manifest", bit.is_file() and rec_bit == _sha(bit), f"manifest {rec_bit}")
    rel = bundle / "RELEASE.md"
    rec("release_md_names_build_id", rel.is_file() and f"`{m.get('build_id')}`" in rel.read_text())
    rec("tools_consistent", m.get("tools_consistent") is not False,
        f"hashed {m.get('tools', {}).get('vivado')}, ran {m.get('tools', {}).get('vivado_ran')}")
    dirty = (m.get("flow") or {}).get("dirty")
    rec("clean_tree", allow_dirty or dirty is False, f"dirty={dirty}" + (" (allowed)" if allow_dirty else ""))
    if m.get("variant") == "ila":
        rec("ltx_present", (bundle / f"{m.get('top')}.ltx").is_file())
    return {"bundle": str(bundle), "build_id": m.get("build_id"), "pass": all(c["pass"] for c in res.values()),
            "checks": res}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("make")
    s.add_argument("design", type=Path)
    s.add_argument("--variant", default="base", choices=["base", "ila"])
    s.add_argument("--out", type=Path)
    s.add_argument("--trace", type=Path)
    s.add_argument("--allow-dirty", action="store_true")
    s.add_argument("--force", action="store_true", help="replace a previous bundle at --out")
    s = sub.add_parser("check")
    s.add_argument("bundle", type=Path)
    s.add_argument("--allow-dirty", action="store_true")
    s.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "make":
        design = a.design if a.design.is_absolute() else ROOT / a.design
        try:
            out = make(design.resolve(), a.variant, a.out, a.trace, a.allow_dirty, a.force)
        except (ReleaseError, OSError, ValueError, KeyError) as e:
            print(f"release.py: {e}", file=sys.stderr)
            return 2
        print(f"release.py: bundle {out}")
        r = check(out, a.allow_dirty)
    else:
        r = check(a.bundle, a.allow_dirty)
        if a.json:
            a.json.write_text(json.dumps(r, indent=1) + "\n")
    for n, c in r["checks"].items():
        print(f"{'ok ' if c['pass'] else 'BAD'} {n}" + (f": {c['detail']}" if c["detail"] else ""))
    print(f"release: {'PASS' if r['pass'] else 'FAIL'} ({r['bundle']})")
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
