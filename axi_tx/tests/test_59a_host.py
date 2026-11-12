"""Brief 59A host side without a simulator: the program format, the model, the register map against the RTL, the tools."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from axi_tx.host import host, model, regs
from axi_tx.host.program import OP, ProgramError, assemble, disassemble

ROOT = Path(__file__).resolve().parents[2]
PROGS = sorted((ROOT / "axi_tx" / "programs").glob("*.yaml"))


def test_lfsr_matches_the_rtl_definition() -> None:
    # Galois right shift, mask 0x80200003 (axi_tx_lfsr.sv); a zero seed loads 1
    s, seen = 1, set()
    for _ in range(1000):
        seen.add(s)
        s = model.lfsr_next(s)
    assert len(seen) == 1000 and model.lfsr_next(1) == 0x8020_0003
    rtl = (ROOT / "axi_tx" / "rtl" / "axi_tx_lfsr.sv").read_text()
    assert "32'h8020_0003" in rtl and hex(model.LFSR_MASK) == "0x80200003"


@pytest.mark.parametrize("path", [p for p in PROGS if p.name != "board_plan.yaml"], ids=lambda p: p.stem)
def test_every_shipped_program_assembles_and_runs_in_the_model(path: Path) -> None:
    p = assemble(path)
    assert p.n_instr <= 256 and p.words[-4:] == [0, 0, 0, 0]
    pred = model.run(p)
    assert pred.ended == "done" and pred.counts["n_txn"] + pred.counts["stream_packets"] > 0
    assert len(disassemble(p.words)) == p.n_instr


def test_encoding_of_one_write_and_one_read() -> None:
    p = assemble({"name": "t", "target": "periph", "steps": [
        {"write": {"addr": 0x10, "data": 0xAB, "strb": 0x3, "order": "w_first", "gap": 5, "sb": True, "resp": "SLVERR"}},
        {"read": {"addr": 0x10, "expect": {"data": 0xAB, "bytes": 0x1}}}]})
    w0 = p.words[0]
    assert w0 >> 28 == OP["write"] and w0 & 0xF == 0x3 and (w0 >> 4) & 3 == 2 and w0 >> 6 & 1
    assert (w0 >> 10) & 3 == 2 and (w0 >> 12) & 0xFF == 5 and w0 >> 22 & 1
    r0 = p.words[4]
    assert r0 >> 28 == OP["read"] and r0 >> 24 & 1 and r0 & 0xF == 1 and p.words[6] == 0xAB


@pytest.mark.parametrize("bad, msg", [
    ({"steps": [{"write": {"addr": 3}}]}, "aligned"),
    ({"steps": [{"write": {"addr": 0, "order": "sideways"}}]}, "order"),
    ({"steps": [{"read": {"addr": 0, "inject": "data_change"}}]}, "inject"),
    ({"steps": [{"set": {"valid_p": 300}}]}, "outside"),
    ({"steps": [{"loop": 2}]}, "body"),
    ({"steps": [{"bogus": 1}]}, "one of"),
    ({"target": "dram", "steps": []}, "target"),
    ({"steps": [{"loop": 2, "body": [{"loop": 2, "body": [{"loop": 2, "body": [{"loop": 2, "body": [
        {"loop": 2, "body": [{"wait": 1}]}]}]}]}]}]}, "nest"),
])
def test_bad_programs_are_refused_with_the_step_named(bad: dict, msg: str) -> None:
    with pytest.raises(ProgramError, match=msg):
        assemble({"name": "bad", **bad})


def test_model_scoreboard_and_peripheral_bugs() -> None:
    p = assemble(ROOT / "axi_tx" / "programs" / "periph_regs.yaml")
    clean = model.run(p).counts
    assert clean["sb_mism"] == 0 and clean["resp_mism"] == 0 and clean["exp_mism"] == 0
    p.lite_bug = "no_strb"
    assert model.run(p).counts["sb_mism"] > 0
    p.lite_bug = "exokay"
    assert model.run(p).counts["resp_mism"] > 0


def test_digest_is_the_rtl_crc() -> None:
    e = [(model.log_word0("write", "OKAY", False, False, False, 7), 0x100, 0xDEADBEEF)]
    import zlib
    assert model.digest(e) == zlib.crc32(b"".join(x.to_bytes(4, "little") for x in e[0]))


def test_register_map_matches_the_rtl_comments() -> None:
    core = (ROOT / "axi_tx" / "rtl" / "axi_tx_core.sv").read_text()
    for off, name in ((regs.VERSION, "VERSION"), (regs.LOG_DATA, "lg_q"), (regs.SINK_DATA, "sinkq")):
        assert re.search(rf"7'h{off:02X}: win_rdata <= ", core), name
    assert f"32'h{regs.VERSION_VALUE >> 16:04X}_{regs.VERSION_VALUE & 0xFFFF:04X}" in core
    assert len(regs.lite_mon_names()) == 76
    mon = (ROOT / "axi_tx" / "rtl" / "axis_mon.sv").read_text()
    assert "NC = 17 + KW" in mon and len(regs.stream_mon_names(4)) == 21
    rules = (ROOT / "axi_tx" / "rtl" / "axil_rules.sv").read_text()
    for i, (name, _, _) in enumerate(regs.LITE_RULES):
        assert re.search(rf"//\s+{i} {name}\b", rules), name


class FakeShell:
    """A register file standing in for the board: VERSION answers, STATUS says done, everything else reads 0."""
    def __init__(self) -> None:
        self.w: dict[int, int] = {}
        self.prog: list[int] = []

    def write(self, addr: int, v: int) -> None:
        off = addr - regs.WINDOW
        if off == regs.PROG_DATA:
            self.prog.append(v)
        self.w[off] = v

    def read(self, addr: int) -> int:
        off = addr - regs.WINDOW
        if off == regs.VERSION:
            return regs.VERSION_VALUE
        if off == regs.STATUS:
            return 2
        if off == regs.PROG_DATA:
            a = self.w.get(regs.PROG_ADDR, 0)
            return self.prog[a] if a < len(self.prog) else 0
        return 0


def test_host_drives_a_register_file_and_reads_every_counter() -> None:
    p = assemble(ROOT / "axi_tx" / "programs" / "periph_regs.yaml")
    sh = FakeShell()
    r = host.SyncHost(sh).run(host.run_program(p, capture=True))
    assert sh.prog == p.words and sh.w[regs.SYS_CTRL] == regs.TARGETS["periph"]
    assert r["status"]["flags"] == ["done"] and len(r["lite_mon"]) == 76 and r["capture"] == {"triggered": False}


def test_tools_are_registered_and_check_a_program(tmp_path: Path) -> None:
    from agent.core import tools as _t  # noqa: F401
    from agent.core.registry import TOOLS
    assert {"axi_program_check", "axi_simulate", "axi_board_run"} <= set(TOOLS)
    assert TOOLS["axi_board_run"].hardware and not TOOLS["axi_program_check"].hardware
    from agent.core.axi_tools import axi_program_check
    out = axi_program_check(None, {"name": "x", "target": "bram", "steps": [{"write": {"addr": 0, "data": 1, "sb": True}},
                                                                             {"read": {"addr": 0, "sb": True}}]})
    assert out["ok"] and out["predicted"]["sb_checked"] == 1 and out["instructions"] == 3
