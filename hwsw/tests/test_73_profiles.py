"""Brief 73: the interface profiles (house, amd_compatible, strict) of the register generator: resolution order, validation,
the generated text, and that every output of every profile agrees with its map. No simulator (the RTL is simulated in
test_64a_regmap_rtl.py)."""
from __future__ import annotations

import copy
import shutil
from pathlib import Path

import pytest
import yaml

from hwsw import regmap

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "hwsw" / "examples" / "demo_accel.yaml"
SPECS = ROOT / "hwsw" / "examples" / "profiles"
needs_cc = pytest.mark.skipif(not (shutil.which("gcc") or shutil.which("cc")), reason="no C compiler")


def _d(**over) -> dict:
    d = yaml.safe_load(DEMO.read_text())
    d.pop("unmapped")                                  # the demo states the house value; a profile test wants the profile's
    d.update(over)
    return d


def _m(inherit=None, **over) -> regmap.RegMap:
    return regmap.from_dict(_d(**over), inherit=inherit)


# ---- the profile table (the brief's) --------------------------------------------------------------------------------------
def test_profiles_are_the_documented_bundles() -> None:
    assert regmap.PROFILES["house"] == {"unmapped": "split", "error_capture": "on", "partial_write": "accept",
                                        "unaligned": "ignore", "reserved_write": "ignore", "wide_values": "optional"}
    assert regmap.PROFILES["amd_compatible"] == {**regmap.PROFILES["house"], "unmapped": "okay", "error_capture": "off"}
    assert regmap.PROFILES["strict"] == {"unmapped": "slverr", "error_capture": "on+irq", "partial_write": "slverr",
                                         "unaligned": "slverr", "reserved_write": "slverr", "wide_values": "snapshot"}


@pytest.mark.parametrize("name", list(regmap.PROFILES))
def test_a_profile_resolves_to_its_settings(name: str) -> None:
    m = _m(profile=name)
    assert m.profile == name and regmap.settings(m) == regmap.PROFILES[name]
    assert regmap.profile_overrides(m) == []
    assert (m.error_capture is not None) == (name != "amd_compatible")
    assert regmap.capture_irq(m) == (name == "strict")


def test_no_profile_is_house_and_changes_nothing_in_the_hash() -> None:
    """A map that names no profile is house, and a house map hashes exactly as before brief 73 (older outputs stay current)."""
    a, b = regmap.from_dict(yaml.safe_load(DEMO.read_text())), _m(unmapped="split")
    assert a.profile == "house" and "interface" not in a.canonical()
    assert a.sha256 == b.sha256
    assert "interface" in _m(profile="strict").canonical()
    assert _m(profile="strict").sha256 != a.sha256


# ---- resolution order: map settings > map profile > design block > design profile > house -------------------------------
def test_resolution_order() -> None:
    ifs = {"axi_lite_profile": "amd_compatible", "blocks": {"demo_accel": {"profile": "strict", "unmapped": "okay"}}}
    inh = regmap.inherit_for(ifs, "demo_accel")
    assert inh == {"profile": "strict", "settings": {"unmapped": "okay"}}
    m = _m(inherit=inh)                                          # the design's block entry: strict, but unmapped okay
    assert m.profile == "strict" and m.unmapped == "okay"
    assert regmap.profile_overrides(m) == [("unmapped", "okay", "slverr")]
    other = regmap.inherit_for(ifs, "another_block")              # a block with no entry takes the design's profile
    assert _m(inherit=other).profile == "amd_compatible"
    own = _m(inherit=inh, profile="house")                        # the map's own profile wins; the block entry is not applied
    assert own.profile == "house" and own.unmapped == "split"
    one = _m(inherit=inh, unmapped="split")                       # a map's own single setting wins over everything
    assert one.unmapped == "split" and one.profile == "strict"
    assert regmap.inherit_for(None, "x") == {"profile": None, "settings": {}}


def test_single_setting_overrides_are_listed_in_the_datasheet() -> None:
    m = _m(profile="strict", unmapped="okay", partial_write="accept", error_capture={"interrupt": False})
    ov = regmap.profile_overrides(m)
    assert ("unmapped", "okay", "slverr") in ov and ("partial_write", "accept", "slverr") in ov
    assert ("error_capture", "on", "on+irq") in ov
    text = "\n".join(s for _, s in regmap.behaviour(m)[:1])
    for k in ("unmapped = okay (profile: slverr)", "partial_write = accept (profile: slverr)",
              "error_capture = on (profile: on+irq)"):
        assert k in text
    assert "No setting differs" in dict(regmap.behaviour(_m(profile="strict")))["profile"]


def test_the_datasheet_names_the_profile_and_states_each_strict_behaviour() -> None:
    topics = dict(regmap.behaviour(_m(profile="strict")))
    assert "`strict`" in topics["profile"]
    assert "answers SLVERR and changes nothing" in topics["strobes"] and "CTRL.SCALE" in topics["strobes"]
    assert "address whose bits [1:0] are not 0 answers SLVERR" in topics["access"]
    assert "answers SLVERR and changes nothing at all" in topics["reserved"]
    assert "requires a snapshot group" in topics["multiword"]
    assert "recorded in the same way" in topics["error_capture"] and "`irq_o` is high while STICKY" in topics["error_capture"]
    house = dict(regmap.behaviour(_m(profile="house")))
    assert "bits [1:0] are not decoded" in house["access"] and "ignore writes" in house["reserved"]
    amd = dict(regmap.behaviour(_m(profile="amd_compatible")))
    assert "answers OKAY and reads 0" in amd["unmapped"] and amd["error_capture"].startswith("**Error capture.** None")


# ---- validation ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("over,msg", [
    ({"profile": "lenient"}, "profile: 'lenient' must be one of house, amd_compatible, strict"),
    ({"partial_write": "reject"}, "partial_write: 'reject' must be one of accept, slverr"),
    ({"unaligned": 1}, "unaligned: 1 must be one of ignore, slverr"),
    ({"reserved_write": None}, "reserved_write: None must be one of ignore, slverr"),
    ({"wide_values": "all"}, "wide_values: 'all' must be one of optional, snapshot"),
])
def test_bad_profile_values_are_refused(over: dict, msg: str) -> None:
    with pytest.raises(regmap.RegmapError, match=msg.replace("[", r"\[").replace("]", r"\]")):
        _m(**over)


def test_a_documentation_only_map_has_no_profile() -> None:
    d = {"regmap": 1, "name": "hand", "addr_width": 7, "unmapped": "okay", "profile": "strict",
         "registers": [{"name": "A", "offset": 0, "fields": [{"name": "X", "lsb": 0, "width": 1, "access": "WO"}]}]}
    with pytest.raises(regmap.RegmapError, match="a profile and its settings are for generated blocks"):
        regmap.from_dict(d, doc_only=True)
    d.pop("profile")
    d["conventions"] = {"partial_write": "slverr", "unaligned": "slverr"}           # it states a hand-written block's own
    m = regmap.from_dict(d, doc_only=True)
    assert m.profile == "" and "profile" not in dict(regmap.behaviour(m))
    assert "answers SLVERR and changes nothing" in dict(regmap.behaviour(m))["strobes"]


def test_strict_refuses_a_wide_value_outside_a_snapshot_group() -> None:
    d = _d(profile="strict")
    d.pop("snapshot")
    with pytest.raises(regmap.RegmapError, match="JOB_CYCLES_LO and JOB_CYCLES_HI look like the two halves of one value"):
        regmap.from_dict(d)
    d["wide_values"] = "optional"                                                # the way out is stated by the message
    regmap.from_dict(d)
    d.pop("profile")
    regmap.from_dict(d)                                                           # house: a wide value in two registers is allowed


def test_interfaces_section_validation() -> None:
    assert regmap.interfaces_errors(None) == [] and regmap.interfaces_errors({"axi_lite_profile": "strict"}) == []
    bad = regmap.interfaces_errors({"axi_lite_profile": "loose", "blocks": {"x": {"profile": "nope", "wide": 1,
                                                                                  "unmapped": "maybe"}},
                                    "amd_ip_acknowledged": "axi_gpio", "extra": 1})
    text = " ".join(bad)
    for k in ("unknown keys ['extra']", "axi_lite_profile: 'loose'", "blocks.x.profile: 'nope'", "blocks.x.wide: unknown",
              "blocks.x.unmapped: 'maybe'", "amd_ip_acknowledged: must be a list"):
        assert k in text, (k, text)


def test_a_spec_with_a_bad_interfaces_section_is_refused_by_load(tmp_path: Path) -> None:
    sp = tmp_path / "spec.yaml"
    sp.write_text("interfaces: {axi_lite_profile: loose}\n")
    with pytest.raises(regmap.RegmapError, match="axi_lite_profile: 'loose'"):
        regmap.load(DEMO, spec=sp)


# ---- generated text follows the settings; every output of every profile agrees with the map -----------------------------------
def _gen(tmp_path: Path, profile: str) -> tuple[regmap.RegMap, Path]:
    d = _d()
    y = tmp_path / "m.yaml"
    y.write_text(yaml.safe_dump(d, sort_keys=False))
    m = regmap.load(y, spec=SPECS / f"spec_{profile}.yaml")
    out = tmp_path / profile
    regmap.generate(m, out)
    return m, out


@needs_cc
@pytest.mark.parametrize("profile", list(regmap.PROFILES))
def test_every_output_of_every_profile_agrees(profile: str, tmp_path: Path) -> None:
    m, out = _gen(tmp_path, profile)
    assert m.profile == profile
    assert regmap.agreement(m, out) == [] and regmap.drift(m, out) == []
    sv = (out / "demo_accel_regs.sv").read_text()
    assert f"// PROFILE {profile}\n" in sv and f"// SETTINGS {regmap.settings_text(m)}\n" in sv
    assert f'#define DEMO_ACCEL_PROFILE "{profile}"' in (out / "demo_accel_regs.h").read_text()
    assert f"PROFILE = {profile!r}" in (out / "demo_accel_regs.py").read_text()
    assert f"Interface profile: `{profile}`" in (out / "demo_accel_regs.md").read_text()


def test_the_rtl_follows_the_settings(tmp_path: Path) -> None:
    sv = {p: (_gen(tmp_path, p)[1] / "demo_accel_regs.sv").read_text() for p in regmap.PROFILES}
    for p in ("house", "amd_compatible"):                    # no new logic unless a setting asks for it
        assert "wr_rej" not in sv[p] and "aw_lo" not in sv[p] and "RESP_SLVERR" not in sv[p]
    assert "RESP_UNMAPPED_RD = 2'b00" in sv["amd_compatible"] and "ecap_" not in sv["amd_compatible"]
    assert "RESP_UNMAPPED_RD = 2'b10" in sv["house"] and "RESP_UNMAPPED_WR = 2'b00" in sv["house"]
    s = sv["strict"]
    assert "RESP_UNMAPPED_WR = 2'b10" in s and "aw_lo != 2'b00" in s and "rd_unal" in s and "ecap_irq_en" in s
    assert "(w_strb & 4'b1100) != 4'b0000" in s and "32'hf000fe8e" in s


@needs_cc
def test_an_overridden_setting_is_in_every_output_and_the_check_sees_it(tmp_path: Path) -> None:
    d = _d(profile="strict", partial_write="accept")
    y = tmp_path / "m.yaml"
    y.write_text(yaml.safe_dump(d, sort_keys=False))
    m = regmap.load(y)
    out = tmp_path / "o"
    regmap.generate(m, out)
    assert regmap.agreement(m, out) == []
    assert "partial_write=accept" in (out / "demo_accel_regs.sv").read_text()
    assert "partial_write = accept (profile: slverr)" in (out / "demo_accel_regs.md").read_text()
    # editing the claim in one output is a disagreement
    p = out / "demo_accel_regs.py"
    p.write_text(p.read_text().replace("'partial_write': 'accept'", "'partial_write': 'slverr'"))
    assert any("Python driver: profile and settings" in e for e in regmap.agreement(m, out))


def test_the_cli_takes_the_design_spec(tmp_path: Path) -> None:
    y = tmp_path / "m.yaml"
    y.write_text(yaml.safe_dump(_d(), sort_keys=False))
    assert regmap.main(["gen", str(y), "--spec", str(SPECS / "spec_strict.yaml"), "--out", str(tmp_path / "o")]) == 0
    assert "// PROFILE strict" in (tmp_path / "o" / "demo_accel_regs.sv").read_text()
    assert regmap.main(["check", str(y), "--spec", str(SPECS / "spec_strict.yaml"), "--out", str(tmp_path / "o")]) == 0
    assert regmap.main(["check", str(y), "--spec", str(SPECS / "spec_house.yaml"), "--out", str(tmp_path / "o")]) == 1   # drift
