"""The RapidWright install brief 100 measured, and where it lives (the counterpart of flow/version_pin.py for Vivado).

RapidWright (AMD Research; Apache 2.0 for the framework, the API library jar carries an AMD EULA part, see the LICENSE.TXT
inside the wheel) is installed by ``tools/rapidwright_env/setup.sh`` into a git-ignored venv. Nothing here is a vendor binary:
only the versions, hashes and paths. The jar and the device files are downloaded by RapidWright itself from AMD's public
GitHub release and download site on first use and are never committed.

Java: the JRE that ships inside Vivado 2026.1 (Temurin 24.0.2+12), so no separate Java is installed.
"""

from __future__ import annotations

import os
from pathlib import Path

RAPIDWRIGHT_VERSION = "2026.1.2"          # the Vivado 2026.1 line (RapidWright releases follow the Vivado year.minor)
JPYPE_VERSION = "1.7.1"
WHEEL_SHA256 = "f9e8e6fb613c838d2d2206ec66b56597f193224018e2c1e93d4aaf8106257659"
JAR_SHA256 = "f5108093ae59d6dfacf9128d0f35e2e0a4340af492f6af185af8dfc197258d41"   # rapidwright-2026.1.2-standalone-lin64.jar
VIVADO_VERSION = "2026.1"
ROOT = Path(__file__).resolve().parents[1]
ENV_DIR = ROOT / "tools" / "rapidwright_env"
VENV_PYTHON = ENV_DIR / "venv" / "bin" / "python"
JAVA_HOME = Path(os.environ.get("FDA_RW_JAVA_HOME", f"/opt/Xilinx/{VIVADO_VERSION}/Vivado/tps/lnx64/jre24.0.2_12"))


def available() -> tuple[bool, str]:
    """(True, '') when the venv python and the JRE exist; else (False, why). CI has neither and skips with this notice."""
    if not VENV_PYTHON.is_file():
        return False, f"RapidWright venv not installed ({VENV_PYTHON}); run tools/rapidwright_env/setup.sh"
    if not (JAVA_HOME / "bin" / "java").is_file():
        return False, f"no Java at {JAVA_HOME} (the JRE inside Vivado {VIVADO_VERSION}); set FDA_RW_JAVA_HOME"
    return True, ""


def env() -> dict[str, str]:
    """Environment for running a RapidWright script: JAVA_HOME, RapidWright's device-file directory under the env dir."""
    e = dict(os.environ)
    e["JAVA_HOME"] = str(JAVA_HOME)
    e["PATH"] = f"{JAVA_HOME / 'bin'}:{e.get('PATH', '')}"
    e.setdefault("RW_DATA_DIR", str(ENV_DIR / "data"))
    return e


def argv(script: str | Path, *args: str) -> list[str]:
    """The fixed argv for a RapidWright script: the venv python in isolated mode (-I), the script, its arguments."""
    return [str(VENV_PYTHON), "-I", str(script), *args]
