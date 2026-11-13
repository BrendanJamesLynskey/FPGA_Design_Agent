"""Brief 64A: the regmap format's rules, drift detection, and the agreement check (no simulator; needs a C compiler).

Each agreement test edits one generated output the way a person might by hand and checks that `check` names the
disagreement; each validation test breaks one rule of the format."""
from __future__ import annotations

import copy
import shutil
from pathlib import Path

import pytest
import yaml

from hwsw import regmap

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "hwsw" / "examples" / "demo_accel.yaml"
STRESS = Path(__file__).parent / "data" / "stress.yaml"
GEN = ROOT / "hwsw" / "examples" / "generated"
needs_cc = pytest.mark.skipif(not (shutil.which("gcc") or shutil.which("cc")), reason="no C compiler")


def test_committed_example_outputs_are_current_and_agree() -> None:
    """The committed demo_accel outputs are what the YAML generates now, and all four agree with it."""
    assert regmap.check(DEMO, GEN) == []


@needs_cc
@pytest.mark.parametrize("y", [DEMO, STRESS], ids=["demo_accel", "stress"])
def test_round_trip_every_output_agrees(y: Path, tmp_path: Path) -> None:
    m = regmap.load(y)
    regmap.generate(m, tmp_path)
    assert regmap.agreement(m, tmp_path) == []
    assert regmap.drift(m, tmp_path) == []


def test_hash_ignores_comments_but_not_content(tmp_path: Path) -> None:
    text = DEMO.read_text()
    a = tmp_path / "a.yaml"
    a.write_text("# a comment\n" + text)
    assert regmap.load(a).sha256 == regmap.load(DEMO).sha256
    a.write_text(text.replace("reset: 0x100", "reset: 0x101"))
    assert regmap.load(a).sha256 != regmap.load(DEMO).sha256


# ---- the agreement check catches a hand edit in each output ------------------------------------------------------------
EDITS = [
    ("h", "#define DEMO_ACCEL_CTRL_MODE_MASK 0x00000070u", "#define DEMO_ACCEL_CTRL_MODE_MASK 0x000000f0u", "MODE mask"),
    ("h", "#define DEMO_ACCEL_CTRL_SCALE_RESET 0x100u", "#define DEMO_ACCEL_CTRL_SCALE_RESET 0x0u", "CTRL.SCALE.reset"),
    ("h", "#define DEMO_ACCEL_IRQ_STATUS_DONE_ACCESS DEMO_ACCEL_ACCESS_W1C",
     "#define DEMO_ACCEL_IRQ_STATUS_DONE_ACCESS DEMO_ACCEL_ACCESS_RW", "IRQ_STATUS.DONE.access"),
    ("h", "#define DEMO_ACCEL_CTRL_RW_MASK 0x0fff0071u", "#define DEMO_ACCEL_CTRL_RW_MASK 0x0fff0171u", "RW_mask disagrees"),
    ("h", "#define DEMO_ACCEL_SCRATCH_OFFSET 0x0fcu", "#define DEMO_ACCEL_SCRATCH_OFFSET 0x0f8u", "SCRATCH.offset"),
    ("py", "'MODE': {'lsb': 4, 'width': 3", "'MODE': {'lsb': 4, 'width': 4", "CTRL.MODE.width"),
    ("py", "'DOORBELL': {'offset': 44", "'DOORBELL': {'offset': 48", "DOORBELL.offset"),
    ("md", "| 0x02c | DOORBELL |", "| 0x030 | DOORBELL |", "DOORBELL.offset"),
    ("md", "| 8 | OVERFLOW | W1C |", "| 8 | OVERFLOW | RW |", "CTRL.OVERFLOW.access"),
    ("md", "| 27:16 | SCALE | RW | 0x100 |", "| 27:16 | SCALE | RW | 0x80 |", "CTRL.SCALE.reset"),
    ("sv", "localparam logic [31:0] RESET_CTRL = 32'h01000020;", "localparam logic [31:0] RESET_CTRL = 32'h01000000;",
     "CTRL.reset"),
    ("sv", "ADDR_RING_HEAD = 10'ha;", "ADDR_RING_HEAD = 10'hb;", "RING_HEAD.offset"),
    ("sv", "    output logic [2:0]   ctrl_mode_o,", "    output logic [3:0]   ctrl_mode_o,", "ports differ"),
]


@needs_cc
@pytest.mark.parametrize("kind,old,new,expect", EDITS, ids=[f"{e[0]}:{e[3]}" for e in EDITS])
def test_a_hand_edit_is_caught(kind: str, old: str, new: str, expect: str, tmp_path: Path) -> None:
    m = regmap.load(DEMO)
    regmap.generate(m, tmp_path)
    p = tmp_path / regmap.file_names(m)[kind]
    t = p.read_text()
    assert t.count(old) == 1, f"edit target not found once in {p.name}: {old}"
    p.write_text(t.replace(old, new))
    errs = regmap.agreement(m, tmp_path)
    assert any(expect in e for e in errs), errs
    assert any(p.name in e for e in regmap.drift(m, tmp_path))


# ---- validation: each broken rule is refused with a reason ---------------------------------------------------------------
def _demo() -> dict:
    return yaml.safe_load(DEMO.read_text())


def _reg(d: dict, name: str) -> dict:
    return next(r for r in d["registers"] if r["name"] == name)


def _broken(edit) -> str:
    d = copy.deepcopy(_demo())
    edit(d)
    with pytest.raises(regmap.RegmapError) as ex:
        regmap.from_dict(d)
    return str(ex.value)


BREAKS = [
    ("overlapping registers", lambda d: _reg(d, "SCRATCH").update(offset=0x004), "overlaps register CTRL"),
    ("misaligned offset", lambda d: _reg(d, "SCRATCH").update(offset=0x0FE), "not a multiple of 4"),
    ("offset outside window", lambda d: _reg(d, "SCRATCH").update(offset=0x1000), "outside the 0x1000-byte window"),
    ("overlapping fields", lambda d: _reg(d, "CTRL")["fields"][1].update(lsb=0), "overlap field ENABLE"),
    ("field past bit 31", lambda d: _reg(d, "CTRL")["fields"][3].update(lsb=24), "not inside [31:0]"),
    ("reset too wide", lambda d: _reg(d, "CTRL")["fields"][1].update(reset=8), "does not fit in 3 bits"),
    ("const too wide", lambda d: _reg(d, "ID")["fields"][0].update(const=0x1_0000), "does not fit in 16 bits"),
    ("unknown access", lambda d: _reg(d, "CTRL")["fields"][0].update(access="RC"), "must be one of RW, RO, W1C, W1S, W1P"),
    ("const on RW", lambda d: _reg(d, "CTRL")["fields"][0].update(const=1), "const is allowed only on a RO field"),
    ("reset on RO input", lambda d: _reg(d, "STATUS")["fields"][0].update(reset=1), "has no reset value"),
    ("W1P reset", lambda d: _reg(d, "CMD")["fields"][0].update(reset=1), "a W1P field reads 0"),
    ("duplicate register", lambda d: d["registers"].append(dict(_reg(d, "SCRATCH"), offset=0x0F0)), "duplicate register"),
    ("duplicate field", lambda d: _reg(d, "CTRL")["fields"].append({"name": "MODE", "lsb": 30, "width": 1,
                                                                     "access": "RW"}), "duplicate field"),
    ("port name clash", lambda d: d["registers"].append({"name": "CTRL_MODE", "offset": 0x0F0, "fields": [
        {"name": "X", "lsb": 0, "width": 1, "access": "RW"}]}) or _reg(d, "CTRL")["fields"].append(
        {"name": "MODE_X", "lsb": 31, "width": 1, "access": "RW"}), "port name ctrl_mode_x"),
    ("C name clash", lambda d: d["registers"].append({"name": "CTRL_MODE", "offset": 0x0F0, "fields": [
        {"name": "Y", "lsb": 0, "width": 1, "access": "RW"}]}), "is also made by register"),
    ("generated-name clash", lambda d: _reg(d, "CTRL")["fields"][1].update(name="RW_MASK"), "clashes with a generated"),
    ("lower-case register", lambda d: _reg(d, "CTRL").update(name="ctrl"), "name must be upper-case"),
    ("irq status not W1C", lambda d: d.update(interrupt={"status": "CTRL", "enable": "IRQ_ENABLE"}),
     "every field of status register CTRL must be W1C"),
    ("irq bit without enable", lambda d: _reg(d, "IRQ_STATUS")["fields"].append(
        {"name": "LATE", "lsb": 5, "width": 1, "access": "W1C"}), "have no enable bit"),
    ("unknown key", lambda d: _reg(d, "CTRL")["fields"][0].update(acess="RW"), "unknown keys ['acess']"),
    ("bad unmapped policy", lambda d: d.update(unmapped="decerr"), "must be slverr or okay"),
    ("data width 64", lambda d: d.update(data_width=64), "only 32 is supported"),
]


@pytest.mark.parametrize("what,edit,expect", BREAKS, ids=[b[0] for b in BREAKS])
def test_validation_refuses(what: str, edit, expect: str) -> None:
    assert expect in _broken(edit)


def test_malformed_yaml_is_an_error_not_a_traceback(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("regmap: 1\nname: x\nregisters: [ {name: A, offset: 0, fields: [ {name: B, lsb: 0} ] ]\n")
    with pytest.raises(regmap.RegmapError):
        regmap.load(p)
    p.write_text("- just a list\n")
    with pytest.raises(regmap.RegmapError):
        regmap.load(p)


# ---- the driver logic without a bus ---------------------------------------------------------------------------------------
class _Mem:
    def __init__(self, init: dict[int, int]):
        self.m, self.log = dict(init), []

    def read32(self, o):
        self.log.append(("R", o))
        return self.m.get(o, 0)

    def write32(self, o, v):
        self.log.append(("W", o, v))
        self.m[o] = v


def _driver():
    import importlib.util
    spec = importlib.util.spec_from_file_location("demo_drv", GEN / "demo_accel_regs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_driver_writes_w1x_bits_as_zero_and_refuses_misuse() -> None:
    d = _driver()
    bus = _Mem({0x004: 0x0100_0121})                   # CTRL: SCALE 0x100, OVERFLOW pending, MODE 2, ENABLE 1
    regs = d.DemoAccelRegs(bus)
    regs.set("CTRL", "MODE", 5)
    assert bus.log[-1] == ("W", 0x004, 0x0100_0051)     # OVERFLOW (bit 8) written as 0: the event is not cleared
    regs.clear("CTRL", "OVERFLOW")
    assert bus.log[-1] == ("W", 0x004, 0x0100_0151)     # RW bits kept, OVERFLOW written as 1
    n = len(bus.log)
    regs.pulse("CMD", "START")                          # CMD has no RW bits: one write, no read
    assert bus.log[n:] == [("W", 0x008, 0x1)]
    with pytest.raises(d.RegisterError):
        regs.set("STATUS", "BUSY", 1)                   # RO
    with pytest.raises(d.RegisterError):
        regs.set("CTRL", "MODE", 8)                     # too wide
    with pytest.raises(d.RegisterError):
        regs.clear("CTRL", "MODE")                      # not W1C
    with pytest.raises(d.RegisterError):
        regs.read("NOPE")
