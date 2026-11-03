"""f2-stage3-io: why the cvdp-profile run 20261103-112924-04e2 never got past post_synth_no_unconstrained_endpoints.

Four causes, one test group each: (1) a successful tool result reached Claude Code as its structured fields only, so the
text (file contents, reports, skills) never arrived; (2) the gate failure named no port; (3) ``load_skill(["constraints"])``
found nothing because that section's skill sits in a vendor set the bank never read; (4) stage 3 had no ``report`` tool
and the prompt did not say that board_constraints rewrites design.xdc and that design.xdc is the only constraints file."""

from __future__ import annotations

import json
from pathlib import Path

import anyio
from mcp import Client

from agent.core.bank import LocalBank
from agent.graph import run as gr
from agent.graph.stages import MACHINE, _stage_pass
from agent.mcp_server.server import build_server
from flow import gates

DATA = Path(__file__).resolve().parents[2] / "flow" / "tests" / "data"
REPORT = (DATA / "check_timing_synth_unconstrained_io.rpt").read_text()


# --- (2) the ports ----------------------------------------------------------------------------------------------------

def test_check_timing_ports_are_read_from_the_detail_sections() -> None:
    ports = gates.parse_check_timing_ports(REPORT)
    assert set(ports) == {"no_input_delay", "no_output_delay"}            # the zero-count checks are left out
    assert len(ports["no_input_delay"]) == 21 and len(ports["no_output_delay"]) == 32
    assert ports["no_input_delay"][0] == "btnc" and "uart_rxd" in ports["no_input_delay"] and "sw[9]" in ports["no_input_delay"]
    assert ports["no_output_delay"][-1] == "uart_txd" and "an[0]" in ports["no_output_delay"]
    assert gates.parse_check_timing(REPORT)["no_input_delay"] == 21        # the counts parser is unchanged


def test_a_clean_check_timing_report_lists_no_ports() -> None:
    assert gates.parse_check_timing_ports((DATA / "good_check_timing_synth.rpt").read_text()) == {}


def test_unconstrained_text_is_plain_names_and_counts_only() -> None:
    t = gates.unconstrained_text({"no_input_delay": ["a", "b"], "no_output_delay": [f"p{i}" for i in range(50)]}, limit=3)
    assert "input ports with no input delay (2): a, b" in t
    assert "output ports with no output delay (50): p0, p1, p2, ... 47 more" in t
    assert "set_" not in t and "false_path" not in t                           # raw facts, no fix hints


def test_the_repair_reason_names_the_ports() -> None:
    st = {"ran": True, "gates": {"post_synth_no_unconstrained_endpoints": False, "post_synth_drc_clean": True},
          "unconstrained_ports": {"no_input_delay": ["btnc"], "no_output_delay": ["led[0]", "uart_txd"]}}
    ok, why = _stage_pass({"stages": {"post_synth": st}}, "post_synth")
    assert not ok and len(why) == 1
    assert why[0].startswith("post_synth:post_synth_no_unconstrained_endpoints (")
    assert "btnc" in why[0] and "led[0], uart_txd" in why[0]


def test_the_gates_text_prints_the_ports_under_the_failed_gate(tmp_path, monkeypatch, capsys) -> None:
    st = {"ran": True, "pass": False, "gates": {"post_synth_no_unconstrained_endpoints": False},
          "unconstrained_ports": gates.parse_check_timing_ports(REPORT)}
    res = {"top": "t", "variant": "base", "pass": False, "timing": None, "utilization": None,
           "first_failed_stage": "post_synth",
           "stages": {n: ({"ran": False, "gates": {}} if n != "post_synth" else st) for n in gates.STAGES}}
    monkeypatch.setattr(gates, "evaluate", lambda *a, **k: res)
    assert gates.main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "FAIL post_synth_no_unconstrained_endpoints" in out
    assert "input ports with no input delay (21): btnc, btnd, btnu, cpu_resetn, sw[0]" in out


# --- (1) text reaches Claude Code ---------------------------------------------------------------------------------------

def test_a_successful_mcp_result_carries_its_text_in_the_structured_fields(session) -> None:
    """Claude Code shows the model the structured result instead of the text: the real stream in
    fixtures/cc_real_stream_haiku_clarify.jsonl shows only {"ok":true,...,"bytes":N} for a write."""
    async def go():
        async with Client(build_server(session)) as c:
            return await c.call_tool("read_file", {"path": "spec.yaml", "max_bytes": 40})
    r = anyio.run(go)
    assert not r.is_error
    assert r.structured_content["output"] == r.content[0].text and "Structured spec" in r.structured_content["output"]
    assert json.dumps(r.structured_content)                                  # still plain JSON


# --- (3) the vendor skills --------------------------------------------------------------------------------------------

class _Skill:
    def __init__(self, path: str, section: str) -> None:
        self.path, self.axis, self.section, self.name, self.description = path, "vendor", section, "n", "d"


def test_the_bank_also_reads_the_sectioned_vendor_sets(tmp_path) -> None:
    (tmp_path / "vendor" / "ross_distilled" / "constraints" / "x").mkdir(parents=True)
    (tmp_path / "vendor/ross_distilled/constraints/x/SKILL.md").write_text("# xdc basics\n")
    calls = []

    class Select:
        def select(self, **kw):
            calls.append(kw)
            if kw.get("vendor") == "ross_distilled":
                return [_Skill("vendor/ross_distilled/constraints/x/SKILL.md", "constraints")]
            return []

    b = object.__new__(LocalBank)
    b.root, b._select = tmp_path, Select()
    got = b.skills("nexys_a7_100t", "artix7", ["constraints"])
    assert [g["path"] for g in got] == ["vendor/ross_distilled/constraints/x/SKILL.md"] and got[0]["text"] == "# xdc basics\n"
    assert calls[1]["vendor"] == "ross_distilled" and calls[1]["generic"] is False and calls[1]["sections"] == ["constraints"]


def test_load_skill_constraints_reaches_the_real_bank_when_it_is_present() -> None:
    import pytest
    from agent.core.bank import DEFAULT_BANK
    if not (DEFAULT_BANK / "tools" / "select_skills.py").exists():
        pytest.skip("no knowledge bank checkout")
    got = LocalBank(DEFAULT_BANK).skills("nexys_a7_100t", "artix7", ["constraints"])
    assert any(g["path"].endswith("xdc-constraints-basics/SKILL.md") for g in got)


# --- (4) stage 3 and the prompt ------------------------------------------------------------------------------------------

def test_stage_3_can_read_a_report_and_the_prompt_says_how_the_io_timing_is_written() -> None:
    assert "report" in MACHINE[3].tools and "board_constraints" in MACHINE[3].tools
    text = gr.conventions_text({"design_rel": "designs/x", "name": "x"})
    flat = " ".join(text.split())
    assert "REWRITES the whole of design.xdc" in flat and "only design.xdc is yours to write" in flat
    assert "post_synth_no_unconstrained_endpoints" in text
