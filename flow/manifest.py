#!/usr/bin/env python3
"""The build manifest and build ID (brief 54).

    python3 flow/manifest.py pre  <build dir> --vivado <path> --threads N      before Vivado (flow/run_vivado.sh)
    python3 flow/manifest.py post <build dir>                                   after Vivado, or on a cache hit
    python3 flow/manifest.py show designs/<name> [--variant base|ila] [--vivado-version 2026.1] [--threads N]
                                                                                 the manifest a build would get, no Vivado
    python3 flow/manifest.py check <manifest.json> [--bit <file.bit>]            the build ID is the manifest's hash
                                                                                 (and the bitstream's USR_ACCESS)

``pre`` reads the build directory that flow/prepare.py filled (``inputs.tcl``, ``prepare.json``), writes
``manifest.json`` and appends ``set build_id <8 hex>`` to ``inputs.tcl``; flow/build.tcl puts it in the bitstream's
USR_ACCESS register (``BITSTREAM.CONFIG.USR_ACCESS``), which the configuration logic holds and the test shell reads back
through the USR_ACCESSE2 primitive (register 0x05). Because the line is in inputs.tcl, the build cache's flow key
(flow/build_cache.py) covers the build ID: a build whose identity changed is never a cache hit.

**What the build ID covers** (``build_id_covers``): every input file's SHA-256 (RTL, XDC, data, IP, probes, build.yaml,
every flow/*.tcl and the flow Python that writes the Tcl), the normalised ``inputs.tcl`` (the order of the sources, the
generics, part, top, power environment, timing margin, stop stage; absolute paths replaced by ``$ROOT`` and ``$OUT``),
the settings that change the result (thread count, implementation directives as build.tcl passes them, the incremental
and ILA-insertion switches) and the Vivado version. ``build_id`` is the first 8 hex digits of the SHA-256 of that part of
the manifest as canonical JSON (sorted keys, no spaces).

**What it records but does not hash:** the flow's git commit and whether the tree was dirty, the knowledge-bank pin,
Python and package versions, Vivado's build number and licence tier (read from the log after the run), the build
cache's keys (they contain absolute paths), the report-only switches, the build directory and the times. A commit that
changes no input does not change the bitstream, so it does not change the build ID.

The top-level ``inputs``, ``tools``, ``kb_pin`` and ``flow`` keys are the ones brief 53's traceability record reads
(flow/change_record.py ``read_manifest``): ``inputs`` maps a repo-relative path to its SHA-256, ``tools`` a tool name to
its version, ``kb_pin`` is the knowledge-bank commit, ``flow`` is ``{commit, dirty}``.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "fda-build-manifest/1"
COVERS = ("schema", "design", "variant", "top", "part", "inputs", "inputs_tcl", "settings", "tools.vivado")
# flow Python whose output is part of the build (the Tcl it writes, or the .ltx it repairs)
FLOW_PY = ("flow/prepare.py", "flow/srcorder.py", "flow/ltx_fix.py")
# switches that change the result (in the build ID) and switches that only add reports (recorded)
RESULT_SWITCHES = ("FDA_INCREMENTAL", "FDA_ILA_INSERT")
REPORT_SWITCHES = ("FDA_XPROBE", "FDA_RESULT_HASH", "FDA_BUILD_CACHE")
SKIP_TCL = ("set out ", "set resume_from ", "set resume_dir ", "set incremental_ref ", "set build_id ")
IMPL_COMMANDS = ("synth_design", "opt_design", "place_design", "phys_opt_design", "route_design", "write_bitstream")
RTL_EXT = {".sv", ".v", ".svh", ".vh", ".vhd", ".vhdl"}


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _get(m: dict, dotted: str) -> Any:
    cur: Any = m
    for k in dotted.split("."):
        cur = cur.get(k) if isinstance(cur, dict) else None
    return cur


def identity(m: dict) -> dict:
    """The part of the manifest the build ID is the hash of."""
    return {k: _get(m, k) for k in m.get("build_id_covers", COVERS)}


def build_id_of(m: dict) -> tuple[str, str]:
    """(build ID, full SHA-256) of a manifest."""
    h = hashlib.sha256(canonical(identity(m))).hexdigest()
    return h[:8], h


def role(rel: str) -> str:
    p = Path(rel)
    if p.suffix == ".xdc":
        return "xdc"
    if p.suffix == ".xci":
        return "ip"
    if p.suffix == ".tcl":
        return "tcl"
    if p.name in ("build.yaml",):
        return "build_yaml"
    if p.name == "probes.yaml":
        return "probes"
    if rel.startswith("flow/") and p.suffix == ".py":
        return "flow_py"
    if p.suffix in RTL_EXT:
        return "rtl"
    return "data"


def vivado_version_from_path(vivado: str) -> str | None:
    m = re.search(r"/(\d{4}\.\d)/", vivado)
    return m.group(1) if m else None


def normalise_tcl(text: str, root: Path, out: Path) -> list[str]:
    """inputs.tcl without the lines that name where it ran, and with absolute paths made relative."""
    lines = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#") or line.startswith(SKIP_TCL):
            continue
        lines.append(line.replace(str(out), "$OUT").replace(str(root), "$ROOT"))
    return lines


def flow_tcl(root: Path) -> list[str]:
    """flow/build.tcl and every flow script it sources (``source $flow_dir/<name>.tcl``): the Tcl that makes the
    bitstream. The board-side scripts (program.tcl, ila_capture.tcl, ...) are not inputs of a build."""
    build = root / "flow" / "build.tcl"
    names = re.findall(r"source\s+\$flow_dir/([\w.]+\.tcl)", build.read_text())
    out = ["flow/build.tcl"]
    for n in names:
        if (root / "flow" / n).is_file() and f"flow/{n}" not in out:
            out.append(f"flow/{n}")
    return out


def impl_commands(build_tcl: Path) -> dict[str, list[str]]:
    """How flow/build.tcl calls each implementation command (its options as written), so a directive or option added
    there is visible in the manifest as well as in build.tcl's hash."""
    out: dict[str, list[str]] = {}
    for line in build_tcl.read_text().splitlines():
        code = line.split("#", 1)[0].strip()
        for c in IMPL_COMMANDS:
            if code.startswith(c + " ") or code == c:
                out.setdefault(c, []).append(code)
    return out


def directives(cmds: dict[str, list[str]]) -> dict[str, str]:
    res = {}
    for c in IMPL_COMMANDS[:-1]:
        ds = {m.group(1) for line in cmds.get(c, []) for m in [re.search(r"-directive\s+(\S+)", line)] if m}
        res[c] = ",".join(sorted(ds)) if ds else "Default"
    return res


def _git(root: Path, *a: str) -> str | None:
    try:
        r = subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.rstrip("\n") if r.returncode == 0 else None


def flow_record(root: Path, inputs: list[str] | None = None) -> dict[str, Any]:
    """The flow's git commit, and whether the tree is dirty: a tracked file changed, or an input file is not tracked."""
    head = _git(root, "rev-parse", "HEAD")
    st = _git(root, "status", "--porcelain", "--untracked-files=no")
    untracked: list[str] = []
    if inputs and head is not None:
        tracked = set((_git(root, "ls-files", "--", *inputs) or "").splitlines())
        untracked = [f for f in inputs if f not in tracked]
    dirty = None if st is None else (bool(st) or bool(untracked))
    return {"commit": head[:12] if head else None, "commit_full": head, "dirty": dirty,
            "dirty_files": sorted(l[3:] for l in (st or "").splitlines())[:50], "inputs_untracked": untracked}


def kb_pin(root: Path) -> str | None:
    """The knowledge-bank commit named in knowledge/PACKS.md (the same reading as brief 53's change record)."""
    try:
        m = re.search(r"Private repo commit:\s*`([0-9a-f]{7,40})`", (root / "knowledge" / "PACKS.md").read_text())
    except OSError:
        return None
    return m.group(1) if m else None


def python_tools() -> dict[str, str | None]:
    t: dict[str, str | None] = {"python": platform.python_version()}
    from importlib import metadata
    for name, dist in (("pyyaml", "PyYAML"),):
        try:
            t[name] = metadata.version(dist)
        except Exception:                                   # noqa: BLE001 (absent: recorded as None)
            t[name] = None
    return t


def compute(out: Path, vivado: str, threads: int | str, env: dict[str, str] | None = None,
            root: Path = ROOT) -> dict[str, Any]:
    """The manifest of the build prepared in ``out`` (inputs.tcl and prepare.json from flow/prepare.py)."""
    env = os.environ if env is None else env
    out = out.resolve()
    prep = json.loads((out / "prepare.json").read_text())
    design = prep["design"]
    files = list(prep["files"])
    files.append(f"{design}/build.yaml")
    if prep["variant"] == "ila":
        bcfg = _yaml(root / design / "build.yaml")
        if bcfg.get("probes"):
            files.append(str(bcfg["probes"]))
    files += flow_tcl(root)
    files += [f for f in FLOW_PY if (root / f).is_file()]
    seen: dict[str, None] = {}
    for f in files:
        seen.setdefault(f, None)
    inputs = {f: sha256_file(root / f) for f in seen}
    tcl_lines = normalise_tcl((out / "inputs.tcl").read_text(), root, out)
    probes_tcl = out / "probes.tcl"
    if probes_tcl.is_file():
        tcl_lines += ["# probes.tcl"] + normalise_tcl(probes_tcl.read_text(), root, out)
    cmds = impl_commands(root / "flow" / "build.tcl")
    vver = vivado_version_from_path(vivado) or str(vivado)
    m: dict[str, Any] = {
        "schema": SCHEMA,
        "design": design, "variant": prep["variant"], "top": prep["top"], "part": prep["part"],
        "build_id": None, "build_id_sha256": None, "build_id_covers": list(COVERS),
        "inputs": inputs,
        "input_roles": {f: role(f) for f in inputs},
        "inputs_tcl": tcl_lines,
        "settings": {
            "threads": int(threads),
            "directives": directives(cmds),
            "seeds": {},
            "switches": {k: (env.get(k) or "") for k in RESULT_SWITCHES},
            "build_stamp": prep.get("build_stamp"),
        },
        "settings_recorded": {
            "commands": cmds,
            "report_switches": {k: (env.get(k) or "") for k in REPORT_SWITCHES},
            "seeds_note": "flow/build.tcl sets no seed option on any command; the result is fixed by the inputs, "
                          "the settings and the tool",
        },
        "tools": {"vivado": vver, **python_tools()},
        "kb_pin": kb_pin(root),
        "flow": flow_record(root, list(inputs)),
        "build_dir": str(out),
        "created": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    bid, full = build_id_of(m)
    m["build_id"], m["build_id_sha256"] = bid, full
    return m


def _yaml(p: Path) -> dict:
    import yaml
    return yaml.safe_load(p.read_text()) or {}


_SWB = re.compile(r"SW Build (\d+) on")
_VER = re.compile(r"Vivado v(\d{4}\.\d)")


def finalise(out: Path) -> dict[str, Any]:
    """Add what only the run knows: Vivado's build number and licence tier (tool.txt / vivado.log), the bitstream's
    hash and USR_ACCESS value, the cache decision and keys. Never changes the build ID."""
    out = out.resolve()
    mf = out / "manifest.json"
    m = json.loads(mf.read_text())
    log = out / "vivado.log"
    text = log.read_text(errors="replace")[:20000] if log.is_file() else ""
    tool = {}
    tf = out / "tool.txt"
    if tf.is_file():
        for line in tf.read_text().splitlines():
            if " " in line:
                k, v = line.split(" ", 1)
                tool[k] = v.strip()
    ver = _VER.search(text)
    swb = _SWB.search(text)
    m["tools"]["vivado_ran"] = tool.get("version") or (ver.group(1) if ver else None)
    m["tools"]["vivado_sw_build"] = swb.group(1) if swb else None
    m["tools"]["vivado_licence_tier"] = tool.get("tier")
    ran = m["tools"]["vivado_ran"]
    m["tools_consistent"] = None if not ran else ran.startswith(m["tools"]["vivado"])
    outputs: dict[str, Any] = {}
    top = m["top"]
    bit = out / f"{top}.bit"
    if bit.is_file():
        try:
            from flow import bitstream
        except ImportError:                                 # run as a script
            import bitstream                                # type: ignore[no-redef]
        outputs["bit"] = {"file": bit.name, "sha256": sha256_file(bit), "usr_access": bitstream.usr_access(bit)}
    ltx = out / f"{top}.ltx"
    if ltx.is_file():
        outputs["ltx"] = {"file": ltx.name, "sha256": sha256_file(ltx)}
    m["outputs"] = outputs
    cache = {}
    for name, key in (("flow_key.txt", "flow_key"), ("synth_key.txt", "synth_key")):
        if (out / name).is_file():
            cache[key] = (out / name).read_text().strip()
    if (out / "cache.json").is_file():
        cache["action"] = json.loads((out / "cache.json").read_text()).get("action")
    m["cache"] = cache
    m["finalised"] = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    mf.write_text(json.dumps(m, indent=1) + "\n")
    return m


def check(m: dict, bit: Path | None = None) -> list[str]:
    """Problems with a manifest: the build ID is not its hash, the bitstream's USR_ACCESS is not the build ID, the
    bitstream's hash is not the recorded one, the Vivado that ran is not the one hashed. Empty: consistent."""
    errs = []
    bid, full = build_id_of(m)
    if m.get("build_id") != bid or m.get("build_id_sha256") != full:
        errs.append(f"build_id {m.get('build_id')} is not the hash of the manifest's identity ({bid})")
    if m.get("tools_consistent") is False:
        errs.append(f"Vivado {m['tools'].get('vivado_ran')} ran, but the manifest names {m['tools'].get('vivado')}")
    if bit is not None:
        try:
            from flow import bitstream
        except ImportError:
            import bitstream                                # type: ignore[no-redef]
        ua = bitstream.usr_access(bit)
        if ua is None or ua.lower() != str(m.get("build_id")).lower():
            errs.append(f"bitstream USR_ACCESS {ua} is not the build ID {m.get('build_id')}")
        rec = (m.get("outputs") or {}).get("bit") or {}
        if rec.get("sha256") and rec["sha256"] != sha256_file(bit):
            errs.append("bitstream SHA-256 differs from the manifest's record")
    return errs


def show(design: Path, variant: str, vivado_version: str, threads: int, root: Path = ROOT) -> dict[str, Any]:
    """The manifest a build of ``design`` would get now, without Vivado (prepare.py into a scratch directory)."""
    with tempfile.TemporaryDirectory(prefix="fda_manifest_") as td:
        out = Path(td) / variant
        r = subprocess.run([sys.executable, str(root / "flow" / "prepare.py"), str(design), "--variant", variant,
                            "--out", str(out)], capture_output=True, text=True, cwd=root)
        if r.returncode:
            raise SystemExit(f"manifest.py: prepare.py failed: {r.stderr.strip()}")
        (out / "prepare.json").write_text(r.stdout)
        m = compute(out, f"/opt/Xilinx/{vivado_version}/Vivado/bin/vivado", threads, root=root)
        m["build_dir"] = None
        return m


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("pre")
    s.add_argument("out", type=Path)
    s.add_argument("--vivado", required=True)
    s.add_argument("--threads", required=True)
    s = sub.add_parser("post")
    s.add_argument("out", type=Path)
    s = sub.add_parser("show")
    s.add_argument("design", type=Path)
    s.add_argument("--variant", default="base", choices=["base", "ila"])
    s.add_argument("--vivado-version", default=None)
    s.add_argument("--threads", type=int, default=2)
    s.add_argument("--json", type=Path)
    s = sub.add_parser("check")
    s.add_argument("manifest", type=Path)
    s.add_argument("--bit", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "pre":
        m = compute(a.out, a.vivado, a.threads)
        (a.out / "manifest.json").write_text(json.dumps(m, indent=1) + "\n")
        with (a.out / "inputs.tcl").open("a") as f:
            f.write(f"set build_id {m['build_id']}\n")
        print(json.dumps({"build_id": m["build_id"], "build_id_sha256": m["build_id_sha256"]}))
        return 0
    if a.cmd == "post":
        m = finalise(a.out)
        errs = check(m, a.out / f"{m['top']}.bit" if (m.get("outputs") or {}).get("bit") else None)
        print(json.dumps({"build_id": m["build_id"], "outputs": m.get("outputs"), "problems": errs}))
        return 1 if errs else 0
    if a.cmd == "show":
        try:
            from flow import version_pin
        except ImportError:
            import version_pin                              # type: ignore[no-redef]
        design = a.design if a.design.is_absolute() else (ROOT / a.design)
        m = show(design.resolve(), a.variant, a.vivado_version or version_pin.DEFAULT_VIVADO_VERSION, a.threads)
        text = json.dumps(m, indent=1)
        if a.json:
            a.json.write_text(text + "\n")
        print(text)
        return 0
    m = json.loads(a.manifest.read_text())
    errs = check(m, a.bit)
    for e in errs:
        print(f"manifest: {e}")
    print(f"manifest {a.manifest}: {'OK' if not errs else 'FAIL'} (build ID {m.get('build_id')})")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
