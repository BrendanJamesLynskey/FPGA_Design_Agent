"""Brief 73: the `axi_profile` check. Each test builds a small design in a temporary folder (a spec.yaml with an
`interfaces:` section, the demo register map, the block generated from it) and breaks one thing: a block that claims a
profile and behaves as another, an edited claim, a design that mixes profiles, an old block, AMD IP behind a strict region.
No simulator: the check regenerates the RTL and compares text; the behaviour of each profile is simulated in
hwsw/tests/test_64a_regmap_rtl.py."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from flow import checks as C
from flow.checks import axi_profile as AP
from hwsw import regmap

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "hwsw" / "examples" / "demo_accel.yaml"


def _design(tmp_path: Path, interfaces: dict | None, profile_of_rtl: str | None = "design", map_extra: dict | None = None,
            keep_map: bool = True) -> Path:
    """A design folder: spec.yaml (+ interfaces), the demo map without its `unmapped:`, and rtl/demo_accel_regs.sv generated
    under `profile_of_rtl` ('design' = the design's own choice, or a profile name given in a spec of its own)."""
    d = tmp_path / "dsn"
    (d / "rtl").mkdir(parents=True)
    spec = {"name": "dsn"}
    if interfaces is not None:
        spec["interfaces"] = interfaces
    (d / "spec.yaml").write_text(yaml.safe_dump(spec))
    mp = yaml.safe_load(DEMO.read_text())
    mp.pop("unmapped")
    mp.update(map_extra or {})
    y = tmp_path / "m.yaml"
    y.write_text(yaml.safe_dump(mp, sort_keys=False))
    if keep_map:
        (d / "demo_accel.yaml").write_text(y.read_text())
    if profile_of_rtl == "design":
        m = regmap.load(y, spec=d / "spec.yaml")
    else:
        other = tmp_path / "other_spec.yaml"
        other.write_text(yaml.safe_dump({"interfaces": {"axi_lite_profile": profile_of_rtl}}))
        m = regmap.load(y, spec=other)
    (d / "rtl" / "demo_accel_regs.sv").write_text(regmap.emit_sv(m))
    return d


def _run(d: Path) -> dict:
    return C.run(d, names=["axi_profile"], scope="rtl", level="detail")


def _status_r(r: dict) -> str:
    return r["checks"][0]["status"]


def _status(d: Path) -> str:
    return _run(d)["checks"][0]["status"]


def _codes(d: Path) -> list[str]:
    return [f["code"] for f in AP.run_checks(d, ROOT)]


def test_a_clean_design_passes_under_each_profile(tmp_path: Path) -> None:
    for i, p in enumerate(regmap.PROFILES):
        d = _design(tmp_path / str(i), {"axi_lite_profile": p})
        assert _codes(d) == [], p
        r = _run(d)
        assert _status_r(r) == "pass", r["digest"]


def test_a_block_that_claims_strict_but_was_edited_is_caught(tmp_path: Path) -> None:
    d = _design(tmp_path, {"axi_lite_profile": "strict"})
    sv = d / "rtl" / "demo_accel_regs.sv"
    t = sv.read_text()
    assert "RESP_UNMAPPED_WR = 2'b10" in t
    sv.write_text(t.replace("RESP_UNMAPPED_WR = 2'b10", "RESP_UNMAPPED_WR = 2'b00"))        # behaves as house, claims strict
    assert _codes(d) == ["AXI-PROFILE-DRIFT"]
    r = _run(d)
    assert _status_r(r) == "fail"
    assert "AXI-PROFILE-DRIFT" in r["digest"] and "HDL-IF-04" in r["digest"]


def test_a_logic_edit_anywhere_in_the_block_is_caught_not_just_the_claim_lines(tmp_path: Path) -> None:
    d = _design(tmp_path, {"axi_lite_profile": "strict"})
    sv = d / "rtl" / "demo_accel_regs.sv"
    t = sv.read_text()
    sv.write_text(t.replace("if (aw_lo != 2'b00) begin", "if (1'b0) begin"))                  # unaligned writes accepted
    assert _codes(d) == ["AXI-PROFILE-DRIFT"]


def test_a_block_generated_under_another_profile_than_the_design_declares(tmp_path: Path) -> None:
    d = _design(tmp_path, {"axi_lite_profile": "strict"}, profile_of_rtl="house")
    assert _codes(d) == ["AXI-PROFILE-MISMATCH"]
    d2 = _design(tmp_path / "b", {"axi_lite_profile": "house"}, profile_of_rtl="amd_compatible")
    assert _codes(d2) == ["AXI-PROFILE-MISMATCH"]


def test_an_edited_claim_line_is_caught(tmp_path: Path) -> None:
    d = _design(tmp_path, {"axi_lite_profile": "house"})
    sv = d / "rtl" / "demo_accel_regs.sv"
    sv.write_text(sv.read_text().replace("// PROFILE house", "// PROFILE strict"))
    assert _codes(d) == ["AXI-PROFILE-MISMATCH"]
    sv.write_text(sv.read_text().replace("// PROFILE strict", "// PROFILE house").replace("partial_write=accept", "partial_write=slverr"))
    assert _codes(d) == ["AXI-PROFILE-MISMATCH"]


def test_a_design_with_no_interfaces_section_is_house(tmp_path: Path) -> None:
    d = _design(tmp_path, None, profile_of_rtl="house")
    assert _codes(d) == []                                       # house by default
    d2 = _design(tmp_path / "b", None, profile_of_rtl="strict")
    assert _codes(d2) == ["AXI-PROFILE-MISMATCH"]                # strict RTL where nothing was declared


def test_a_map_that_names_its_own_profile_is_a_mix_unless_declared(tmp_path: Path) -> None:
    d = _design(tmp_path, {"axi_lite_profile": "strict"}, map_extra={"profile": "house"})
    assert _codes(d) == ["AXI-PROFILE-MIX"]
    assert _status(d) == "fail"         # the design chose a profile: a block that differs must be declared
    d0 = _design(tmp_path / "n", None, map_extra={"profile": "strict"}, profile_of_rtl="design")
    assert _codes(d0) == ["AXI-PROFILE-MIX"] and _status(d0) == "pass"     # no design profile chosen: advice only
    d2 = _design(tmp_path / "b", {"axi_lite_profile": "strict", "blocks": {"demo_accel": {"profile": "house"}}},
                 map_extra={"profile": "house"})
    assert _codes(d2) == []                                      # declared: the design says so


def test_a_per_block_entry_in_the_spec_is_the_block_profile(tmp_path: Path) -> None:
    d = _design(tmp_path, {"axi_lite_profile": "house", "blocks": {"demo_accel": {"profile": "strict", "unmapped": "okay"}}})
    assert _codes(d) == []
    sv = (d / "rtl" / "demo_accel_regs.sv").read_text()
    assert "// PROFILE strict" in sv and "unmapped=okay" in sv
    # the map's own profile wins over the design's block entry, and the check says they disagree
    d2 = _design(tmp_path / "b", {"axi_lite_profile": "house", "blocks": {"demo_accel": {"profile": "strict"}}},
                 map_extra={"profile": "amd_compatible"}, profile_of_rtl="design")
    assert "// PROFILE amd_compatible" in (d2 / "rtl" / "demo_accel_regs.sv").read_text()
    assert _codes(d2) == ["AXI-PROFILE-MISMATCH"]


def test_a_block_generated_before_profiles_existed(tmp_path: Path) -> None:
    d = _design(tmp_path, {"axi_lite_profile": "house"})
    sv = d / "rtl" / "demo_accel_regs.sv"
    sv.write_text("".join(ln for ln in sv.read_text().splitlines(True) if not ln.startswith(("// PROFILE", "// SETTINGS"))))
    assert _codes(d) == ["AXI-PROFILE-STALE"] and _status(d) == "fail"


def test_a_block_with_no_source_map_is_reported_not_trusted(tmp_path: Path) -> None:
    d = _design(tmp_path, {"axi_lite_profile": "strict"}, keep_map=False)
    c = AP.run_checks(d, tmp_path / "elsewhere")                # the repo's own example maps are not searched either
    assert [f["code"] for f in c] == ["AXI-PROFILE-NOSRC"] and c[0]["blocking"]


def test_an_invalid_interfaces_section_fails(tmp_path: Path) -> None:
    d = _design(tmp_path, {"axi_lite_profile": "lenient"}, profile_of_rtl="house")
    codes = _codes(d)
    assert "AXI-PROFILE-SPEC" in codes
    assert _status(d) == "fail"


def _amd(d: Path) -> None:
    (d / "ip.tcl").write_text("create_ip -name axi_gpio -vendor xilinx.com -library ip -module_name gpio0\n")


def test_amd_ip_in_a_strict_design_is_flagged_until_acknowledged(tmp_path: Path) -> None:
    d = _design(tmp_path, {"axi_lite_profile": "strict"})
    _amd(d)
    c = AP.run_checks(d, ROOT)
    assert [f["code"] for f in c] == ["AXI-PROFILE-AMD-STRICT"] and "axi_gpio" in c[0]["message"] and not c[0]["blocking"]
    d2 = _design(tmp_path / "b", {"axi_lite_profile": "strict", "amd_ip_acknowledged": ["axi_gpio"]})
    _amd(d2)
    assert _codes(d2) == []
    d3 = _design(tmp_path / "c", {"axi_lite_profile": "amd_compatible"})                 # AMD IP beside amd_compatible blocks is the point
    _amd(d3)
    assert _codes(d3) == []


def test_a_strict_block_makes_the_design_strict_for_the_amd_rule(tmp_path: Path) -> None:
    d = _design(tmp_path, {"axi_lite_profile": "house", "blocks": {"demo_accel": {"profile": "strict"}}})
    _amd(d)
    assert _codes(d) == ["AXI-PROFILE-AMD-STRICT"]


def test_the_check_does_not_apply_without_blocks_or_interfaces(tmp_path: Path) -> None:
    d = tmp_path / "plain"
    d.mkdir()
    (d / "spec.yaml").write_text("name: plain\n")
    assert AP.applies(d, ROOT) and "no generated" in AP.applies(d, ROOT)
    chosen, skipped = C.select("all", "rtl", d)
    assert "axi_profile" in skipped and "axi_profile" not in chosen
    assert AP.applies(_design(tmp_path / "x", None), ROOT) is None


def test_the_axi_amd_ip_note_check_reports_ip_it_finds(tmp_path: Path) -> None:
    """Brief 71's `axi` check read a key the scan does not return, so it never reported anything (found by brief 73)."""
    d = tmp_path / "amd"
    d.mkdir()
    _amd(d)
    r = C.run(d, names=["axi"], scope="rtl", level="detail")
    assert "AXI-AMD-IP" in r["digest"] and "AXI GPIO" in r["digest"]


def test_the_tool_schema_lists_the_check() -> None:
    from agent.core import tools
    assert "axi_profile" in tools.CHECK_NAMES
    assert all(n in tools.CHECK_NAMES for n in C.CHECKS) or set(C.CHECKS) - set(tools.CHECK_NAMES) == set()


def test_the_committed_example_block_checks_clean_in_a_house_design(tmp_path: Path) -> None:
    """The committed demo_accel outputs are what the check expects of a design that chooses house."""
    d = tmp_path / "ex"
    (d / "rtl").mkdir(parents=True)
    (d / "spec.yaml").write_text(yaml.safe_dump({"interfaces": {"axi_lite_profile": "house"}}))
    (d / "rtl" / "demo_accel_regs.sv").write_text((ROOT / "hwsw" / "examples" / "generated" / "demo_accel_regs.sv").read_text())
    (d / "demo_accel.yaml").write_text(DEMO.read_text())
    assert AP.run_checks(d, ROOT) == []


def test_the_clarify_gate_refuses_a_bad_interfaces_section_and_accepts_a_good_one() -> None:
    from agent.graph import spec_schema as SS
    spec = yaml.safe_load((ROOT / "designs" / "t1_dimmer_counter" / "spec.yaml").read_text())
    assert not [e for e in SS.validate(spec, allow_rates=True) if "interfaces" in e]
    spec["interfaces"] = {"axi_lite_profile": "strict", "blocks": {"demo_accel": {"unmapped": "okay"}}}
    assert not [e for e in SS.validate(spec, allow_rates=True) if "interfaces" in e]
    spec["interfaces"] = {"axi_lite_profile": "lenient"}
    errs = [e for e in SS.validate(spec, allow_rates=True) if "interfaces" in e]
    assert errs and "'lenient' must be one of house, amd_compatible, strict" in errs[0]


def test_the_clarify_and_rtl_prompts_describe_the_three_profiles() -> None:
    from agent.graph.run import PROMPTS
    c = PROMPTS["clarify"]
    for k in ("house", "amd_compatible", "strict", "AMD IP", "bring-up, safety or verification-heavy"):
        assert k in c
    assert "axi_profile" in PROMPTS["rtl"] and "never edit a generated block" in PROMPTS["rtl"]


# ---- the reviewer's attempts to make a block claim a profile and behave otherwise (brief 73 review round) ----------------------
def _edit_strict(d: Path) -> Path:
    sv = d / "rtl" / "demo_accel_regs.sv"
    sv.write_text(sv.read_text().replace("RESP_UNMAPPED_WR = 2'b10", "RESP_UNMAPPED_WR = 2'b00"))
    return sv


def test_a_banner_far_into_the_file_is_still_scanned(tmp_path: Path) -> None:
    d = _design(tmp_path, {"axi_lite_profile": "strict"})
    sv = _edit_strict(d)
    sv.write_text("// " + "x" * 700 + "\n" + sv.read_text())
    assert _codes(d) == ["AXI-PROFILE-DRIFT"]


def test_a_block_in_a_file_with_another_name_is_scanned(tmp_path: Path) -> None:
    d = _design(tmp_path, {"axi_lite_profile": "strict"})
    sv = _edit_strict(d)
    sv.rename(d / "rtl" / "top_bus.sv")
    assert _codes(d) == ["AXI-PROFILE-DRIFT"]


def test_removing_or_garbling_the_claim_lines_fails(tmp_path: Path) -> None:
    d = _design(tmp_path, {"axi_lite_profile": "strict"})
    sv = _edit_strict(d)
    t = sv.read_text()
    sv.write_text(t.replace("// PROFILE strict\n", ""))
    assert _codes(d) == ["AXI-PROFILE-STALE"] and _status(d) == "fail"
    sv.write_text(t.replace("// PROFILE strict\n", "// PROFILE strict  \n"))        # a trailing space is not an escape
    assert _codes(d) == ["AXI-PROFILE-DRIFT"]
    sv.write_text(t.replace("// Generated by hwsw", "// Written by hwsw"))             # the banner removed, the claim kept
    assert _codes(d) == ["AXI-PROFILE-DRIFT"]


def test_a_banner_naming_a_map_that_does_not_exist_fails(tmp_path: Path) -> None:
    d = _design(tmp_path, {"axi_lite_profile": "strict"})
    sv = _edit_strict(d)
    sv.write_text(sv.read_text().replace("from regmap demo_accel", "from regmap zzz"))
    assert _codes(d) == ["AXI-PROFILE-NOSRC"] and _status(d) == "fail"


def test_a_maps_own_settings_cannot_weaken_the_designs_profile_silently(tmp_path: Path) -> None:
    weak = {"partial_write": "accept", "unaligned": "ignore", "reserved_write": "ignore", "unmapped": "okay",
            "error_capture": False}
    d = _design(tmp_path, {"axi_lite_profile": "strict"}, map_extra=weak)
    c = AP.run_checks(d, ROOT)
    assert {f["code"] for f in c} == {"AXI-PROFILE-OVERRIDE"} and len(c) == 5 and all(f["blocking"] for f in c)
    # declared by the design (a settings-only blocks entry) it is accepted
    d2 = _design(tmp_path / "b", {"axi_lite_profile": "strict", "blocks": {"demo_accel": {"partial_write": "accept"}}},
                 map_extra={"partial_write": "accept"})
    assert _codes(d2) == []
    # a design's block settings are ignored by a map that names its own profile: reported, not dropped
    d3 = _design(tmp_path / "c", {"axi_lite_profile": "strict", "blocks": {"demo_accel": {"partial_write": "accept"}}},
                 map_extra={"profile": "strict"})
    assert _codes(d3) == ["AXI-PROFILE-OVERRIDE"]


def test_a_design_that_declares_strict_in_build_yaml_alone_is_enforced(tmp_path: Path) -> None:
    d = _design(tmp_path, None, profile_of_rtl="house")
    (d / "spec.yaml").unlink()
    (d / "build.yaml").write_text(yaml.safe_dump({"top": "t", "sources": [], "interfaces": {"axi_lite_profile": "strict"}}))
    assert "AXI-PROFILE-MISMATCH" in _codes(d)


def test_a_typo_in_blocks_and_an_unparseable_spec_fail(tmp_path: Path) -> None:
    d = _design(tmp_path, {"axi_lite_profile": "house", "blocks": {"demo_acel": {"profile": "strict"}}}, profile_of_rtl="house")
    assert _codes(d) == ["AXI-PROFILE-SPEC"]
    d2 = _design(tmp_path / "b", {"axi_lite_profile": "house"}, profile_of_rtl="house")
    (d2 / "spec.yaml").write_text("name: [unclosed\ninterfaces: {axi_lite_profile: strict}\n")
    assert "AXI-PROFILE-SPEC" in _codes(d2)


def test_a_list_as_a_profile_is_a_finding_not_a_crash(tmp_path: Path) -> None:
    from hwsw import regmap
    assert regmap.interfaces_errors({"axi_lite_profile": ["strict"], "blocks": {"x": {"profile": {"a": 1}}}})
    with pytest.raises(regmap.RegmapError, match="profile"):
        regmap.from_dict(yaml.safe_load(DEMO.read_text()) | {"profile": ["strict"]})


def test_placing_the_capture_keeps_the_profiles_interrupt() -> None:
    from hwsw import regmap
    m = regmap.from_dict(yaml.safe_load(DEMO.read_text()) | {"profile": "strict", "error_capture": {"offset": 0xE0}}
                         | {"unmapped": "slverr"})
    assert regmap.capture_irq(m) and regmap.settings(m)["error_capture"] == "on+irq"


def test_two_halves_of_a_value_in_different_snapshot_groups_are_refused() -> None:
    from hwsw import regmap
    d = yaml.safe_load(DEMO.read_text()) | {"profile": "strict"}
    d["unmapped"] = "slverr"
    d["snapshot"] = [{"name": "A", "trigger": "CMD.SNAP", "fields": ["JOB_CYCLES_LO.VALUE"]},
                     {"name": "B", "trigger": "CMD.START", "fields": ["JOB_CYCLES_HI.VALUE"]}]
    with pytest.raises(regmap.RegmapError, match="different snapshot groups"):
        regmap.from_dict(d)
