"""The Vivado version the knowledge bank was measured on, and the check a build makes against the version that ran it.

The bank (private repo, named in knowledge/PACKS.md) records each version-bound fact with the Vivado version it was verified
on. This module holds only the one version the pinned bank says, so a build's gates.json can state whether the Vivado that
ran it is the one the skills' measured numbers, rule severities and option names refer to (brief 21). Changing it is
step 8 of the bank's upgrade procedure (docs/VERSION_UPGRADE.md in the knowledge repo): after the probe, the diff, the
review, the re-pin and a clean regression on the new version.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

KB_MEASURED_VERSION = "2026.1"

# The one place the Vivado install path comes from (brief 48). Order: $VIVADO (a full path to the vivado binary), else
# $FDA_VIVADO_VERSION (a version under /opt/Xilinx), else DEFAULT_VIVADO_VERSION. Keep 2025.2 runnable with
# FDA_VIVADO_VERSION=2025.2 to reproduce old results. flow/run_vivado.sh, hil/cdc_soak/run_build.sh and flow/hw.py all read it.
DEFAULT_VIVADO_VERSION = "2026.1"
VIVADO_ROOT = "/opt/Xilinx"

def vivado_path(env: dict | None = None) -> str:
    """Path of the vivado binary: $VIVADO, else $FDA_VIVADO_VERSION under /opt/Xilinx, else the default version."""
    env = os.environ if env is None else env
    if env.get("VIVADO"):
        return env["VIVADO"]
    return f"{VIVADO_ROOT}/{env.get('FDA_VIVADO_VERSION') or DEFAULT_VIVADO_VERSION}/Vivado/bin/vivado"


_TOOL = re.compile(r"Tool Version\s*:\s*Vivado v\.?(\d{4}\.\d)")
_LOG = re.compile(r"Vivado v(\d{4}\.\d)")


def build_version(build_dir: Path, run: dict | None) -> str | None:
    """The Vivado version that made a build: run.json's `vivado_version`, else the Tool Version line of a report."""
    if run and run.get("vivado_version"):
        m = re.match(r"\d{4}\.\d", str(run["vivado_version"]))
        return m.group(0) if m else str(run["vivado_version"])
    for rpt in sorted(build_dir.glob("*.rpt")):
        try:
            m = _TOOL.search(rpt.read_text(errors="replace")[:2000])
        except OSError:
            continue
        if m:
            return m.group(1)
    return None


def record(build_dir: Path, run: dict | None) -> dict:
    """Fields for gates.json: the running version, the version the bank was measured on, and whether they agree."""
    ver = build_version(build_dir, run)
    return {"vivado_version": ver, "kb_measured_version": KB_MEASURED_VERSION,
            "kb_version_match": None if ver is None else ver == KB_MEASURED_VERSION}


def note(rec: dict) -> str | None:
    """One line for the console when the versions differ (never a gate: the regression on the new version decides)."""
    if rec.get("kb_version_match") is False:
        return (f"note: built with Vivado {rec['vivado_version']}, but the knowledge bank's measured numbers, rule severities and "
                f"option names are for {rec['kb_measured_version']}; see the bank's docs/VERSION_UPGRADE.md")
    return None


if __name__ == "__main__":
    # shell callers: python3 flow/version_pin.py --vivado
    if sys.argv[1:] == ["--vivado"]:
        print(vivado_path())
    else:
        sys.exit("usage: version_pin.py --vivado")
