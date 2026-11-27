"""Brief 243: the Red Pitaya user slots did not answer the bus (build 170300fd, board visit 2026-11-27: every read of slots 6 and 7 returned 0).

Cause: the vendor's clock-crossing bridge holds the request until the ack and reads rdata two to three clocks after the ack was raised; a block that follows the
documented one-cycle convention clears rdata the next cycle. The fix is ``rp_bus_adapt`` in front of every block (tools/rp_shell.py) and these tests: the adapter
against a model of the bridge (iverilog, in CI), the whole bus path against the pinned vendor files (xsim, only where the vendor checkout and Vivado exist), the
loader script's new checks (login environment, load_fda.sh, ID read stops on 0) against a fake board.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent.core import permissions as P  # noqa: E402
from hil import redpitaya_checks as C  # noqa: E402
from hil import redpitaya_load as LD  # noqa: E402
from tools import rp_shell as SH  # noqa: E402

SHELL = ROOT / "boards" / "redpitaya_stemlab_125_14" / "shell"
VENDOR_LINES = """assign dac_a_sum = asg_dat[0] + pid_dat[0];
assign dac_b_sum = asg_dat[1] + pid_dat[1];
SBA_T [2-1:0]            pid_dat;
  sys_bus_stub sys_bus_stub_6 (sys[6]);
  sys_bus_stub sys_bus_stub_7 (sys[7]);
"""


@pytest.mark.skipif(shutil.which("iverilog") is None or shutil.which("vvp") is None, reason="iverilog is not installed")
def test_the_adapter_answers_a_held_request_with_a_held_answer_and_the_unadapted_block_returns_zero(tmp_path):
    exe = tmp_path / "ba.vvp"
    subprocess.run(["iverilog", "-g2012", "-o", str(exe), str(SHELL / "tb_rp_bus_adapt.sv"), str(SHELL / "rp_bus_adapt.sv"), str(SHELL / "rp_user_block.sv")], check=True, capture_output=True)
    out = subprocess.run(["vvp", str(exe)], check=True, capture_output=True, text=True).stdout
    assert "BUS ADAPT PASS" in out
    for c in ("case sin2 sout2 PASS", "case sin3 sout4 PASS", "case sin2 sout5 PASS", "case silent block PASS", "case direct (expected FAIL) FAIL"):
        assert c in out, c


def test_every_block_is_patched_in_behind_the_adapter_and_the_adapter_ships_with_the_blocks():
    out = SH.apply_patch(VENDOR_LINES, "rp_freqcount", "rp_patgen")
    for slot, mod in ((7, "rp_freqcount"), (6, "rp_patgen")):
        assert f"rp_bus_adapt i_bus_adapt{slot}" in out and f".s_rdata (sys[{slot}].rdata)" in out and f".sys_ack (u{slot}_ack)" in out
        assert f"{mod} i_user" in out
        assert f".sys_rdata (sys[{slot}].rdata)" not in out.split(f"{mod} i_user")[1]          # the block is not on the shell's bus directly
    assert SH.ADAPT_DEFAULT.is_file() and "module rp_bus_adapt" in SH.ADAPT_DEFAULT.read_text()
    assert "rp_bus_adapt.sv" in (ROOT / "tools" / "rp_shell.py").read_text()


def test_the_adapter_documents_what_a_user_could_guess_wrong():
    t = SH.ADAPT_DEFAULT.read_text()
    for must in ("held", "ONE access", "TIMEOUT", "reset", "latency", "same cycle", "170300fd"):
        assert must in t, must


# ---- the xsim bus path (vendor files at the pin + our blocks) -----------------------------------------------------------------------------------
WORK = os.environ.get("RP_SHELL_WORK")          # a tools/rp_shell.py work directory (vendor/ at the pin, prepared with the blocks)


@pytest.mark.skipif(not WORK or not Path(WORK, "vendor").is_dir() or not Path("/opt/Xilinx/2025.2/Vivado/bin/xsim").exists(), reason="needs RP_SHELL_WORK and xsim")
@pytest.mark.parametrize("phase", ["0.5", "4", "7.5"])
def test_the_bus_path_of_the_patched_top_answers_in_both_slots_and_failed_without_the_adapter(phase):
    run = [sys.executable, str(ROOT / "hil" / "rp_bus_sim" / "run_xsim.py"), WORK, "--phase", phase]
    ok = subprocess.run(run, capture_output=True, text=True)
    assert "BUS PATH PASS" in ok.stdout, ok.stdout + ok.stderr
    bad = subprocess.run(run + ["--no-adapter"], capture_output=True, text=True)
    assert "BUS PATH FAIL" in bad.stdout and "-> 00000000" in bad.stdout            # build 170300fd: every read 0


# ---- the checks' ID read -------------------------------------------------------------------------------------------------------------------------
class FakeWin:
    def __init__(self, v):
        self.v = v
        self.closed = False

    def read(self, off):
        return self.v

    def close(self):
        self.closed = True


@pytest.mark.parametrize("value,rc", [(0xFDA10201, 0), (0, 3), (0xDEADBEEF, 1)])
def test_id_only_exit_codes(monkeypatch, capsys, value, rc):
    monkeypatch.setattr(C, "MemWindow", lambda base: FakeWin(value))
    assert C.main(["rp_patgen", "--base", "0x40600000", "--id-only"]) == rc
    j = json.loads(capsys.readouterr().out)
    assert j["id_read"] == hex(value) and j["id_expected"] == "0xfda10201" and j["pass"] == (rc == 0)


# ---- the loader script ---------------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def pkg(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "fpga.bit.bin").write_bytes(os.urandom(4096))
    (d / "build.json").write_text(json.dumps({"build_id": "cafe0002"}))
    for f in ("redpitaya_checks.py", "redpitaya_regs.py"):
        shutil.copy(ROOT / "hil" / f, d / f)
    return d


def test_load_fda_mirrors_overlay_sh_volatile_steps_and_passes_the_never_list():
    t = LD.render_load_fda("cafe0002")
    assert P.check_script(t) is None
    assert "fpga.bin" in t and "BIN=/tmp/fda_load/fpga.bin" in t                          # the v0.94 overlay asks for firmware named fpga.bin
    assert "fpgautil -b" in t and "-n Full" in t and "operating" in t and "grep -q -i \"fail\"" in t
    assert "v0.94/fpga.dtbo" in t and "/dev/mmcblk" not in t and "boot.bin" not in t
    subprocess.run(["sh", "-n", "-c", t], check=True)


def test_the_script_runs_every_board_command_in_a_login_environment_and_loads_with_load_fda(pkg):
    t = LD.render_script(pkg, "rp_freqcount", also=(("rp_patgen", 6),))
    assert ". /etc/profile" in t and "/opt/redpitaya/sbin:/opt/redpitaya/bin" in t
    assert 'rp "sh /tmp/fda_load/load_fda.sh"' in t and '"$PKG/load_fda.sh"' in t and "overlay.sh v0.94 /tmp" not in t
    assert "check_id rp_freqcount 0x40700000 7" in t and "check_id rp_patgen 0x40600000 6" in t
    assert t.index("check_id rp_freqcount") < t.index("redpitaya_checks.py rp_freqcount")      # the ID read comes before any check
    assert "overlay.sh v0.94" in t                                                         # RESTORE keeps the factory shell


def fake_board(tmp_path, id_rc: int):
    """ssh and scp that pretend to be the board: record every command; the load works; the --id-only read exits with ``id_rc``."""
    b = tmp_path / "bin"
    b.mkdir()
    (b / "scp").write_text("#!/bin/sh\necho scp >> " + str(tmp_path) + "/calls\nexit 0\n")
    (b / "ssh").write_text(f'''#!/bin/sh
last=""; for a in "$@"; do last="$a"; done
echo "$last" >> {tmp_path}/calls
case "$last" in
  *"cat /sys/class/fpga_manager/fpga0/state"*) echo operating;;
  *"grep -qi fail"*) exit 1;;
  *"grep -q "*) exit 0;;
  *"--id-only"*) echo '{{"id_read": "0x0"}}'; exit {id_rc};;
  *"redpitaya_checks.py"*) echo '{{"rows": [], "pass": true}}';;
esac
exit 0
''')
    for n in ("ssh", "scp"):
        (b / n).chmod(0o755)
    return b


@pytest.mark.parametrize("id_rc,stops,word", [(3, True, "reads 0"), (1, True, "does not read"), (0, False, "")])
def test_the_script_stops_at_an_id_that_reads_zero_before_any_check_runs(pkg, tmp_path, id_rc, stops, word):
    f = pkg / "load.sh"
    f.write_text(LD.render_script(pkg, "rp_patgen", also=(("rp_freqcount", 7),), slot=6))
    env = {**os.environ, "PATH": f"{fake_board(tmp_path, id_rc)}:{os.environ['PATH']}", "OUT": str(tmp_path / "out.json")}
    r = subprocess.run(["bash", str(f)], input="yes\nyes\n", capture_output=True, text=True, env=env, cwd=tmp_path)
    calls = (tmp_path / "calls").read_text()
    assert "sh /tmp/fda_load/load_fda.sh" in calls and "/etc/profile" in calls
    if stops:
        assert r.returncode == 1 and "STOP: slot 6 (0x40600000, rp_patgen)" in r.stderr and word in r.stderr and "Nothing was written" in r.stderr
        assert "redpitaya_checks.py rp_patgen --base 0x40600000 --drive-ok" not in calls and "--drive-ok" not in calls          # no check ran, OUT1 untouched
    else:
        assert "--id-only" in calls and "STOP" not in r.stderr


def test_the_script_command_writes_load_fda_beside_the_script_and_refuses_nothing(pkg, tmp_path):
    assert LD.main(["script", str(pkg), "--block", "rp_freqcount", "--also", "rp_patgen:6"]) == 0
    assert (pkg / "load_fda.sh").is_file() and (pkg / "load_cafe0002.sh").stat().st_mode & stat.S_IXUSR
    assert "check_id rp_patgen 0x40600000 6" in (pkg / "load_cafe0002.sh").read_text()


def test_the_committed_adapter_is_the_file_both_recorded_builds_were_made_from():
    import hashlib
    want = hashlib.sha256(SH.ADAPT_DEFAULT.read_bytes()).hexdigest()
    for d in sorted((ROOT / "results" / "243_redpitaya" / "shell_timing").iterdir()):
        info = json.loads((d / "build.json").read_text())
        assert info["blocks"]["rp_bus_adapt.sv"] == want, d.name
        assert info["timing"]["timing_met"] is False and info["bit_bin_sha256"].startswith(info["build_id"])
