"""The allow-list for build.yaml `ip_tcl:` (flow/ip_tcl_allow.yaml): Tcl that flow/build.tcl sources inside Vivado.

check(entries) returns the resolved files, or raises IpTclRefused if any entry is absolute, has '..', matches nothing,
or resolves to a file that is not listed in the allow-list with its current SHA-256. Used by flow/prepare.py (every build)
and by the agent core (agent/core/tools.py load_build_cfg, agent/core/artefacts.py), so an agent cannot add Tcl of its own.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ALLOW = ROOT / "flow" / "ip_tcl_allow.yaml"


class IpTclRefused(ValueError):
    pass


def allowed() -> dict[str, str]:
    return {e["path"]: e["sha256"] for e in (yaml.safe_load(ALLOW.read_text()) or [])}


def check(entries: list, root: Path = ROOT) -> list[Path]:
    if not isinstance(entries, list):
        raise IpTclRefused("ip_tcl must be a list of repo-relative paths")
    ok = allowed()
    out: list[Path] = []
    for e in entries:
        if not isinstance(e, str) or e.startswith("/") or ".." in Path(e).parts or "\x00" in e or any(c in e for c in "*?["):
            raise IpTclRefused(f"ip_tcl entry {e!r} must be a plain repo-relative path (no glob, no '..')")
        f = (root / e).resolve()
        if not f.is_file():
            raise IpTclRefused(f"ip_tcl entry {e!r} matches no file")
        rel = str(f.relative_to(root.resolve())) if root.resolve() in f.parents else e
        want = ok.get(rel)
        if want is None:
            raise IpTclRefused(f"ip_tcl entry {e!r} is not in flow/ip_tcl_allow.yaml (only reviewed Tcl may run in Vivado)")
        if hashlib.sha256(f.read_bytes()).hexdigest() != want:
            raise IpTclRefused(f"ip_tcl entry {e!r} differs from its reviewed version (SHA-256 in flow/ip_tcl_allow.yaml)")
        out.append(f)
    return out


def materialise(entries: list, out: Path, root: Path = ROOT) -> list[Path]:
    """Read each allowed file once, check the SHA-256 of exactly those bytes, and write them to <out>/ip_tcl/: Vivado
    sources the copy, so the file that was checked is the file that runs (no window between check and use)."""
    files = check(entries, root)                # path rules and the allow-list entry
    ok = allowed()
    dst_dir = Path(out) / "ip_tcl"
    dst_dir.mkdir(parents=True, exist_ok=True)
    copies = []
    for i, f in enumerate(files):
        data = f.read_bytes()
        rel = str(f.relative_to(root.resolve()))
        if hashlib.sha256(data).hexdigest() != ok[rel]:
            raise IpTclRefused(f"ip_tcl entry {rel!r} changed while it was being read; not building")
        dst = dst_dir / f"{i:02d}_{f.name}"
        dst.write_bytes(data)
        copies.append(dst)
    return copies
