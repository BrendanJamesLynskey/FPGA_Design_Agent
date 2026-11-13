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
    # the snapshot group, in each output that states it
    ("py", "{'trigger': ['CMD', 'SNAP']", "{'trigger': ['CMD', 'START']", "snapshot JOB_CYCLES"),
    ("md", "| JOB_CYCLES | CMD.SNAP |", "| JOB_CYCLES | CMD.START |", "snapshot JOB_CYCLES"),
    ("h", "#define DEMO_ACCEL_SNAP_JOB_CYCLES_WIDTH 64u", "#define DEMO_ACCEL_SNAP_JOB_CYCLES_WIDTH 32u",
     "snapshot JOB_CYCLES"),
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
    ("unknown access", lambda d: _reg(d, "CTRL")["fields"][0].update(access="XX"), "must be one of RW, RO, W1C, W1S, W1P"),
    # no read side effects (owner, 2026-11-13): clear-on-read, pop-on-read and an on_read action are refused
    ("clear on read", lambda d: _reg(d, "IRQ_STATUS")["fields"][0].update(access="RC"), "changes state on a read"),
    ("pop on read", lambda d: _reg(d, "STATUS")["fields"][1].update(access="POP"), "pop or acknowledge with a W1P bit"),
    ("on_read action", lambda d: _reg(d, "STATUS")["fields"][1].update(on_read="pop"), "a read must not change state"),
    ("write-only outside a datasheet", lambda d: _reg(d, "SCRATCH")["fields"][0].update(access="WO"), "must be one of"),
    # snapshot groups
    ("snapshot trigger not W1P", lambda d: d["snapshot"][0].update(trigger="CTRL.ENABLE"), "must be a one-bit W1P field"),
    ("snapshot of a RW field", lambda d: d["snapshot"][0]["fields"].append("SCRATCH.VALUE"),
     "must be a RO field read from a hardware input"),
    ("snapshot of a constant", lambda d: d["snapshot"][0]["fields"].append("ID.MAGIC"), "not a constant"),
    ("snapshot unknown field", lambda d: d["snapshot"][0]["fields"].append("JOB_CYCLES_HI.NOPE"), "not a declared field"),
    ("snapshot field twice", lambda d: d["snapshot"].append({"name": "AGAIN", "trigger": "CMD.FLUSH",
                                                             "fields": ["JOB_CYCLES_LO.VALUE"]}), "already in snapshot"),
    ("snapshot trigger twice", lambda d: d["snapshot"].append({"name": "AGAIN", "trigger": "CMD.SNAP",
                                                               "fields": ["STATUS.LEVEL"]}), "already triggers"),
    ("snapshot over 64 bits", lambda d: d["snapshot"][0]["fields"].append("STATUS.LEVEL"), "at most 64"),
    ("conventions in a generated map", lambda d: d.update(conventions={"strobes": "ignored"}),
     "conventions and staging are for documentation-only maps"),
    ("const on RW", lambda d: _reg(d, "CTRL")["fields"][0].update(const=1), "const is allowed only on a RO field"),
    ("reset on RO input", lambda d: _reg(d, "STATUS")["fields"][0].update(reset=1), "has no reset value"),
    ("W1P reset", lambda d: _reg(d, "CMD")["fields"][0].update(reset=1), "a W1P field reads 0"),
    ("duplicate register", lambda d: d["registers"].append(dict(_reg(d, "SCRATCH"), offset=0x0F0)), "duplicate register"),
    ("duplicate field", lambda d: _reg(d, "CTRL")["fields"].append({"name": "MODE", "lsb": 30, "width": 1,
                                                                     "access": "RW"}), "duplicate field"),
    ("port name clash", lambda d: d["registers"].append({"name": "CTRL_MODE", "offset": 0x0F0, "fields": [
        {"name": "X", "lsb": 0, "width": 1, "access": "RW"}]}) or _reg(d, "CTRL")["fields"].append(
        {"name": "MODE_X", "lsb": 31, "width": 1, "access": "RW"}), "port name ctrl_mode_x"),
    # a register's own signal against another register's field port: A_O makes wr_a_o, WR field A makes port wr_a_o
    ("register signal meets a field port", lambda d: d["registers"].extend([
        {"name": "A_O", "offset": 0x0F0, "fields": [{"name": "X", "lsb": 0, "width": 1, "access": "RW"}]},
        {"name": "WR", "offset": 0x0F4, "fields": [{"name": "A", "lsb": 0, "width": 1, "access": "RW"}]}]),
     "its signal wr_a_o is also the port made by WR.A"),
    # the full names: field B's `_set_i` port is field B_SET's `_i` port
    ("full port names meet", lambda d: d["registers"].append({"name": "Q", "offset": 0x0F0, "fields": [
        {"name": "B", "lsb": 0, "width": 1, "access": "W1S"}, {"name": "B_SET", "lsb": 1, "width": 1, "access": "RO"}]}),
     "q_b_set_i is also made by Q.B"),
    ("C name clash", lambda d: d["registers"].append({"name": "CTRL_MODE", "offset": 0x0F0, "fields": [
        {"name": "Y", "lsb": 0, "width": 1, "access": "RW"}]}), "is also made by register"),
    ("generated-name clash", lambda d: _reg(d, "CTRL")["fields"][1].update(name="RW_MASK"), "clashes with a generated"),
    ("lower-case register", lambda d: _reg(d, "CTRL").update(name="ctrl"), "name must be upper-case"),
    ("irq status not W1C", lambda d: d.update(interrupt={"status": "CTRL", "enable": "IRQ_ENABLE"}),
     "every field of status register CTRL must be W1C"),
    ("irq bit without enable", lambda d: _reg(d, "IRQ_STATUS")["fields"].append(
        {"name": "LATE", "lsb": 5, "width": 1, "access": "W1C"}), "have no enable bit"),
    ("unknown key", lambda d: _reg(d, "CTRL")["fields"][0].update(acess="RW"), "unknown keys ['acess']"),
    ("bad unmapped policy", lambda d: d.update(unmapped="decerr"), "must be okay or slverr"),
    ("data width 64", lambda d: d.update(data_width=64), "only 32 is supported"),
    # names the generated block uses itself (wr_hit, wr_commit, rd_value), and text that would break an output
    ("register HIT", lambda d: _reg(d, "SCRATCH").update(name="HIT"), "rd_hit, wr_hit would meet one of its own"),
    ("register COMMIT", lambda d: _reg(d, "SCRATCH").update(name="COMMIT"), "wr_commit would meet"),
    ("register VALUE", lambda d: _reg(d, "SCRATCH").update(name="VALUE"), "rd_value would meet"),
    ("newline in summary", lambda d: d.update(summary="two\nlines"), "summary: a newline"),
    ("comment end in register summary", lambda d: _reg(d, "CTRL").update(summary="x */ #define Y 1 /*"),
     "'*/', '/*' would end a comment"),
    ("docstring end in summary", lambda d: d.update(summary='a """ b'), "'\"\"\"' would end"),
    ("backslash in field summary", lambda d: _reg(d, "CTRL")["fields"][0].update(summary="C:\\Name"), "would end"),
    ("bar in field summary", lambda d: _reg(d, "CTRL")["fields"][0].update(summary="a | b"), "table cell"),
    ("version with spaces", lambda d: d.update(version="1.0 */"), "version:"),
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


def test_driver_snapshot_pulses_then_reads_low_part_first() -> None:
    d = _driver()
    bus = _Mem({0x030: 0x89AB_CDEF, 0x034: 0x0123_4567})
    regs = d.DemoAccelRegs(bus)
    assert regs.snapshot("JOB_CYCLES") == 0x0123_4567_89AB_CDEF
    assert bus.log == [("W", 0x008, 0x4), ("R", 0x030), ("R", 0x034)]     # CMD.SNAP (no RW bits in CMD: no read)
    with pytest.raises(d.RegisterError):
        regs.snapshot("NOPE")


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


def test_generate_refuses_text_that_breaks_an_output(tmp_path: Path) -> None:
    """A RegMap built in code skips from_dict; gen still refuses a summary that would end a comment or docstring."""
    import dataclasses
    m = regmap.load(DEMO)
    bad = dataclasses.replace(m, summary='ends the docstring """ here')
    with pytest.raises(regmap.RegmapError, match="cannot generate"):
        regmap.generate(bad, tmp_path)


@pytest.mark.skipif(not shutil.which("iverilog"), reason="needs Icarus Verilog")
def test_check_compiles_the_systemverilog(tmp_path: Path) -> None:
    """check reads the SV for ports and constants only; it also compiles it, so a broken block is not 'agree'."""
    m = regmap.load(DEMO)
    regmap.generate(m, tmp_path)
    sv = tmp_path / regmap.file_names(m)["sv"]
    t = sv.read_text()
    sv.write_text(t.replace("    logic [31:0] rd_value;", "    logic [31:0] rd_value;\n    logic rd_value;", 1))
    errs = regmap.agreement(m, tmp_path)
    assert any("does not compile" in e for e in errs), errs


# ---- the datasheet: every behaviour a user could guess wrong, generated from a setting -------------------------------------
def test_unmapped_defaults_to_okay_and_the_document_follows_the_setting(tmp_path: Path) -> None:
    """Owner, 2026-11-13: holes inside a block answer OKAY with 0, provided the datasheet says so."""
    d = _demo()
    d.pop("unmapped")
    m = regmap.from_dict(d)
    assert m.unmapped == "okay"
    ok = regmap.emit_md(m)
    assert "Unmapped addresses answer OKAY and read 0." in ok and "answers OKAY and reads 0" in ok
    assert "follows the house register conventions" in ok
    sl = regmap.emit_md(regmap.from_dict(dict(d, unmapped="slverr")))
    assert "Unmapped addresses answer SLVERR and read 0." in sl and "answers SLVERR and reads 0" in sl
    assert "differs from the house register conventions (docs/hwsw.md) in 1 way: unmapped addresses" in sl
    assert "RESP_UNMAPPED = 2'b00;" in regmap.emit_sv(m)
    assert "RESP_UNMAPPED = 2'b10;" in regmap.emit_sv(regmap.from_dict(dict(d, unmapped="slverr")))


def _doc(**conv) -> dict:
    """A documentation-only map (a hand-written block) with the given conventions."""
    return {"regmap": 1, "name": "hand", "addr_width": 7, "conventions": conv, "registers": [
        {"name": "DATA", "offset": 0, "count": 2, "fields": [{"name": "W", "lsb": 0, "width": 32, "access": "WO"}]},
        {"name": "CMD", "offset": 0x40, "fields": [{"name": "OP", "lsb": 0, "width": 4, "access": "WO"}]},
        {"name": "STATUS", "offset": 0x44, "fields": [{"name": "BUSY", "lsb": 0, "width": 1, "access": "RO", "reset": 0},
                                                      {"name": "RAW", "lsb": 4, "width": 4, "access": "RO"}]}],
            "staging": [{"name": "DATA", "registers": ["DATA0", "DATA1"], "commit": "CMD"}]}


def _says(m, topic: str) -> str:
    return dict(regmap.behaviour(m))[topic]


# (topic, map a, map b, text in a's sentence, text in b's sentence): the same topic, one setting changed
FOLLOWS = [
    ("unmapped", lambda: regmap.from_dict(_demo()), lambda: regmap.from_dict(dict(_demo(), unmapped="slverr")),
     "answers OKAY and reads 0", "answers SLVERR and reads 0"),
    ("reserved", lambda: regmap.from_dict(_doc(), doc_only=True),
     lambda: regmap.from_dict(_doc(reserved="undefined"), doc_only=True), "read 0 and ignore writes", "undefined value"),
    ("side_effects", lambda: regmap.from_dict(_demo()), lambda: regmap.from_dict(_doc(), doc_only=True),
     "W1P bit: CMD.START, CMD.FLUSH, CMD.SNAP", "Actions happen on writes only: a write to CMD."),
    ("priority", lambda: regmap.from_dict(_demo()), lambda: regmap.from_dict(_doc(), doc_only=True),
     "W1C bits (CTRL.OVERFLOW, IRQ_STATUS.DONE, IRQ_STATUS.ERROR): a hardware set", "no W1C or W1S bits"),
    ("strobes", lambda: regmap.from_dict(_doc(), doc_only=True),
     lambda: regmap.from_dict(_doc(strobes="ignored"), doc_only=True), "are honoured on every register",
     "are ignored on every register"),
    ("access", lambda: regmap.from_dict(_demo()), lambda: regmap.from_dict(dict(_demo(), addr_width=13)),
     "only bits [11:2] are decoded, so the window repeats every 0x1000 bytes",
     "only bits [12:2] are decoded, so the window repeats every 0x2000 bytes"),
    ("multiword", lambda: regmap.from_dict(_demo()), lambda: regmap.from_dict({k: v for k, v in _demo().items()
                                                                               if k != "snapshot"}),
     "write 1 to CMD.SNAP to copy the whole value", "No snapshot groups: every register is read on its own"),
    ("multiword", lambda: regmap.from_dict(_doc(), doc_only=True), lambda: regmap.from_dict(_demo()),
     "only for a command (a write to CMD)", "A read without a new snapshot returns the copy from the last one (stale)"),
    ("reset", lambda: regmap.from_dict(_doc(), doc_only=True),
     lambda: regmap.from_dict(_doc(reset="rst", reset_active="high"), doc_only=True),
     "`aresetn`, synchronous, active low", "`rst`, synchronous, active high"),
    ("reset", lambda: regmap.from_dict(_doc(reset_style="asynchronous"), doc_only=True), lambda: regmap.from_dict(_demo()),
     "asynchronous, active low.", "Not reset by this block: the RO fields that read a hardware input (STATUS.BUSY"),
    ("reset", lambda: regmap.from_dict(_doc(), doc_only=True), lambda: regmap.from_dict(_demo()),
     "(STATUS.RAW)", "snapshot copies read 0"),
    ("interrupt", lambda: regmap.from_dict(_demo()), lambda: regmap.from_dict({k: v for k, v in _demo().items()
                                                                               if k != "interrupt"}),
     "high while any bit of IRQ_STATUS (DONE, ERROR) is set together with the same bit of IRQ_ENABLE",
     "None: this block has no interrupt output"),
    ("clock", lambda: regmap.from_dict(_doc(), doc_only=True), lambda: regmap.from_dict(_doc(clock="clk"), doc_only=True),
     "in the `aclk` domain", "in the `clk` domain"),
]


@pytest.mark.parametrize("topic,a,b,in_a,in_b", FOLLOWS, ids=[f"{f[0]}-{i}" for i, f in enumerate(FOLLOWS)])
def test_each_behaviour_sentence_follows_its_setting(topic, a, b, in_a, in_b) -> None:
    sa, sb = _says(a(), topic), _says(b(), topic)
    assert in_a in sa and in_b not in sa, sa
    assert in_b in sb and in_a not in sb, sb


def test_every_topic_is_stated_and_differences_lead_the_document() -> None:
    topics = ["unmapped", "reserved", "side_effects", "priority", "strobes", "access", "multiword", "reset", "interrupt",
              "clock"]
    assert [k for k, _ in regmap.behaviour(regmap.from_dict(_demo()))] == topics
    m = regmap.from_dict(_doc(strobes="ignored", reset="rst", reset_active="high", clock="clk"), doc_only=True)
    first = regmap.convention_sentence(m)
    assert first.startswith("It differs from the house register conventions (docs/hwsw.md) in 2 ways: byte strobes")
    assert "the reset is `rst`, synchronous, active high" in first
    assert regmap.convention_sentence(regmap.from_dict(_demo())).startswith("It follows the house register conventions")


def test_documentation_only_maps() -> None:
    m = regmap.from_dict(_doc(), doc_only=True)
    assert [r.name for r in m.registers] == ["DATA0", "DATA1", "CMD", "STATUS"]
    assert m.reg("DATA1").offset == 4
    text = "\n".join(regmap.datasheet(m))
    assert "| WO | write-only" in text and "| W1C |" not in text            # only the access types it uses
    with pytest.raises(regmap.RegmapError, match="documentation-only"):
        regmap.generate(m, Path("/nonexistent"))
    with pytest.raises(regmap.RegmapError, match="must be one of low, high"):
        regmap.from_dict(_doc(reset_active="low-ish"), doc_only=True)
