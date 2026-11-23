"""The production_secure demonstration design under Icarus (brief 196): the safe shutdown of b196_top, the generated SYSMON package, and the
documented limit that the SYSMONE4 instance is synthesis-only."""

import subprocess
from pathlib import Path

import pytest

D = Path(__file__).resolve().parents[1]
ROOT = D.parents[1]
ICARUS = subprocess.run(["which", "iverilog"], capture_output=True).returncode == 0

RTL = [D / "rtl" / "b196_sysmon_pkg.sv", *sorted((ROOT / "designs" / "b194_assurance" / "rtl").glob("*.sv")), D / "rtl" / "b196_shutdown.sv",
       D / "rtl" / "b196_sysmon_guard.sv", D / "rtl" / "b196_top.sv"]


def test_the_generated_package_is_what_the_board_file_gives():
    from flow import security
    assert (D / "rtl" / "b196_sysmon_pkg.sv").read_text() == security.sysmon_header("kr260")


@pytest.mark.skipif(not ICARUS, reason="iverilog not installed")
def test_one_alarm_latches_the_safe_shutdown(tmp_path):
    exe = tmp_path / "s.out"
    # a194_secded.sv holds the functions the FIFO uses; order: package first, then the core files
    order = [RTL[0], *[f for f in RTL[1:] if f.name == "a194_secded.sv"], *[f for f in RTL[1:] if f.name != "a194_secded.sv"]]
    subprocess.run(["iverilog", "-g2012", "-o", str(exe), *map(str, order), str(D / "tb" / "tb_shutdown.sv"), "-s", "tb_shutdown"], check=True)
    out = subprocess.run(["vvp", str(exe)], capture_output=True, text=True, timeout=600).stdout
    assert "TB PASS" in out, out[-600:]
