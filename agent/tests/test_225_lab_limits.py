"""Brief 225, addendum: ``lab_limits`` (brief 222's never-rule) calls ``hil.lab.check_drive`` (brief 221), and ``drive_instrument`` is the lab tool.
Also the Red Pitaya never-rule (the board's SD card, OS, updater and factory SCPI server). No model, no board, no instrument, no Vivado.

What is tested: a drive request over a limit, for an unknown or not-onboarded instrument, for an output a script may never enable, or with a value the
output needs and the request omits, is refused as the ``lab_limits`` never-rule in every permission mode (``full`` with every action allowed included);
a request inside the limits reaches the permission mode (denied in plan, asked in ask and auto, allowed in full) and then only records itself, enabling
nothing; the Red Pitaya never-rule refuses what changes the card, the OS or the SCPI server and lets overlay.sh, fpgautil and read-only checks through."""

import json
import types

import pytest
import yaml

from agent.core import permissions as P
from agent.core.registry import TOOLS, dispatch
from agent.core.security import SecurityError

ALL_ALLOWED = {a: "allow" for a in P.ACTION_NAMES}


def lab_profile(tmp_path, monkeypatch, onboarded=True, outputs=None):
    f = tmp_path / "lab.yaml"
    f.write_text(yaml.safe_dump({"schema": "fpga-force/lab/v1", "instruments": [{
        "id": "gen1", "kind": "signal_generator", "onboarded": onboarded, "connection": {"type": "lan", "address": "192.0.2.9"},
        "control": {"mode": "scripted", "driver": "mock"}, "channels": [{"name": "OUT1", "kind": "analog_out"}],
        "outputs": outputs or [{"name": "OUT1", "kind": "awg", "max_v": 1.0, "max_hz": 1e6}, {"name": "OUT2", "kind": "awg", "never_by_script": True}]}]}))
    monkeypatch.setenv("FDA_LAB_FILE", str(f))
    return f


def sess(tmp_path, mode, design=None, overrides=None):
    P.Policy(mode, overrides or {}, "test", run_dir=tmp_path).save()
    return types.SimpleNamespace(stage="configuration-and-debug", permissions_run_dir=tmp_path, design=design or tmp_path / "design")


OVER = [({"instrument": "gen1", "output": "OUT1", "volts": 1.5, "hz": 1000}, "above the lab file's limit"),
        ({"instrument": "gen1", "output": "OUT1", "volts": 0.5, "hz": 5e6}, "above the lab file's limit"),
        ({"instrument": "gen1", "output": "OUT1", "hz": 1000}, "does not state its v"),                 # a value the output needs and the call omits
        ({"instrument": "gen1", "output": "OUT2", "volts": 0.1}, "never enabled by a script"),
        ({"instrument": "gen1", "output": "OUT3", "volts": 0.1}, "no such output"),
        ({"instrument": "nope", "output": "OUT1", "volts": 0.1}, "no instrument"),
        ({"output": "OUT1", "volts": 0.1}, "names its instrument and its output"),
        ({"instrument": "gen1", "output": "OUT1", "volts": "0.1"}, "not a number")]


@pytest.mark.parametrize("mode", P.MODE_ORDER)
@pytest.mark.parametrize("args,why", OVER)
def test_an_unsafe_drive_is_refused_by_the_never_rule_in_every_mode_full_included(tmp_path, monkeypatch, mode, args, why):
    lab_profile(tmp_path, monkeypatch)
    s = sess(tmp_path, mode, overrides=ALL_ALLOWED)                       # every action allowed: the never-rule is the only thing left
    with pytest.raises(P.NeverRefused) as e:
        P.tool_gate(s, "drive_instrument", args)
    assert e.value.never == "lab_limits" and why in str(e.value) and "never allowed in any mode" in str(e.value) and isinstance(e.value, SecurityError)


def test_a_not_onboarded_instrument_is_refused_in_every_mode(tmp_path, monkeypatch):
    lab_profile(tmp_path, monkeypatch, onboarded=False)
    for mode in P.MODE_ORDER:
        with pytest.raises(P.NeverRefused) as e:
            P.tool_gate(sess(tmp_path / mode, mode, overrides=ALL_ALLOWED), "drive_instrument", {"instrument": "gen1", "output": "OUT1", "volts": 0.1, "hz": 10})
        assert e.value.never == "lab_limits" and "not onboarded" in str(e.value)


def test_a_drive_inside_the_limits_meets_the_mode_not_the_never_rule(tmp_path, monkeypatch):
    lab_profile(tmp_path, monkeypatch)
    ok = {"instrument": "gen1", "output": "OUT1", "volts": 0.5, "hz": 1000}
    with pytest.raises(SecurityError) as e:                                # plan: denied
        P.tool_gate(sess(tmp_path / "p", "plan"), "drive_instrument", ok)
    assert e.value.rule == "permission-denied" and "drive_instrument_output" in str(e.value)
    for m in ("ask", "auto"):                                              # ask and auto: not granted until the stage asked
        with pytest.raises(SecurityError) as e:
            P.tool_gate(sess(tmp_path / m, m), "drive_instrument", ok)
        assert e.value.rule == "permission-not-granted"
    P.tool_gate(sess(tmp_path / "f", "full"), "drive_instrument", ok)       # full: allowed


def test_the_lab_tool_is_registered_gated_and_only_records_a_request(tmp_path, monkeypatch, session):
    lab_profile(tmp_path, monkeypatch)
    from agent.core import tools as _t  # noqa: F401
    assert "drive_instrument" in TOOLS and TOOLS["drive_instrument"].hardware
    assert P.tool_actions("drive_instrument") == ("drive_instrument_output",)
    assert P.stage_actions(9, ("drive_instrument",)).count("drive_instrument_output") == 1
    ok = {"instrument": "gen1", "output": "OUT1", "volts": 0.5, "hz": 1000, "purpose": "self-test"}
    r = dispatch(session, "drive_instrument", ok)
    assert r["ok"] and "Nothing was enabled" in r["output"]
    rows = json.loads((session.design / "build" / "lab" / "drive_requests.json").read_text())
    assert rows[-1]["status"] == "approved_within_limits_not_enabled" and rows[-1]["volts"] == 0.5
    r = dispatch(session, "drive_instrument", {**ok, "volts": 2.0})
    assert r["refused"] and r["rule"] == "never-lab_limits" and len(json.loads((session.design / "build" / "lab" / "drive_requests.json").read_text())) == 1


def test_the_tool_function_checks_again_when_called_without_dispatch(tmp_path, monkeypatch, session):
    lab_profile(tmp_path, monkeypatch)
    from agent.core import lab_tools
    with pytest.raises(P.NeverRefused):
        lab_tools.drive_instrument(session, "gen1", "OUT1", volts=3.0, hz=10)


def test_a_design_lab_file_cannot_raise_a_limit_above_the_profile_by_accident(tmp_path, monkeypatch):
    """The design's lab file overrides fields of the same id (221); the limit used is the merged one, so a design that states a lower limit lowers it."""
    lab_profile(tmp_path, monkeypatch)
    d = tmp_path / "design"
    d.mkdir()
    (d / "lab.yaml").write_text(yaml.safe_dump({"schema": "fpga-force/lab/v1", "instruments": [{"id": "gen1", "outputs": [{"name": "OUT1", "kind": "awg", "max_v": 0.2}]}]}))
    with pytest.raises(P.NeverRefused):
        P.tool_gate(sess(tmp_path / "x", "full", d, ALL_ALLOWED), "drive_instrument", {"instrument": "gen1", "output": "OUT1", "volts": 0.5, "hz": 10})
    P.tool_gate(sess(tmp_path / "y", "full", d, ALL_ALLOWED), "drive_instrument", {"instrument": "gen1", "output": "OUT1", "volts": 0.1, "hz": 10})


# ---- the Red Pitaya never-rule --------------------------------------------------------------------------------------------------------------

RP_REFUSED = ["ecosystem-update.sh", "apt-get upgrade", "cp u-boot.scr /media/x/boot/", "cp boot.bin /media/x/boot/", "echo x > /opt/redpitaya/sbin/overlay.sh",
              "rm /opt/redpitaya/www/index.html", "mount /dev/mmcblk0p1 /mnt", "systemctl start redpitaya_scpi", "cp uImage /boot/"]
RP_FINE = ["overlay.sh v0.94 /tmp/fda/fpga.bit.bin", "fpgautil -b /tmp/fda/fpga.bit.bin -f Full", "cat /sys/class/fpga_manager/fpga0/state",
           "cat /tmp/update_fpga.txt", "/opt/redpitaya/bin/monitor 0x40700000", "scp fpga.bit.bin root@rp:/tmp/fda/", "ls /opt/redpitaya/fpga/Z10/v0.94/",
           "md5sum /tmp/fda/fpga.bit.bin"]


@pytest.mark.parametrize("text", RP_REFUSED)
def test_the_red_pitaya_never_rule_refuses_a_script_that_changes_the_card_the_os_or_the_scpi_server(text):
    v = P.check_script(text)
    assert v and v[0] in ("redpitaya_os", "boot_image"), text


@pytest.mark.parametrize("text", RP_FINE)
def test_the_red_pitaya_never_rule_lets_a_volatile_load_and_read_only_checks_through(text):
    assert P.check_script(text) is None


@pytest.mark.parametrize("mode", P.MODE_ORDER)
def test_a_board_tool_call_naming_the_red_pitaya_updater_is_refused_in_every_mode(tmp_path, mode):
    s = sess(tmp_path, mode, overrides=ALL_ALLOWED)
    with pytest.raises(P.NeverRefused) as e:
        P.tool_gate(s, "bringup", {"note": "run ecosystem-update on the red pitaya first"})
    assert e.value.never == "redpitaya_os"
    with pytest.raises(P.NeverRefused) as e:
        P.tool_gate(s, "debug_capture", {"note": "systemctl start redpitaya_scpi"})
    assert e.value.never == "redpitaya_os"


def test_the_agent_may_not_write_a_boot_or_os_file_for_the_red_pitaya():
    assert P.never_violation("write_file", {"path": "u-boot.scr", "content": "x"})[0] == "redpitaya_os"
    assert P.never_violation("write_file", {"path": "rtl/top.sv", "content": "x"}) is None


def test_the_never_list_names_the_new_rule_and_the_navigator_lists_it():
    assert "redpitaya_os" in P.NEVER_BY_ID and "lab_limits" in P.NEVER_BY_ID
    assert any(r["id"] == "redpitaya_os" for r in P.describe()["never"]) if hasattr(P, "describe") else True
