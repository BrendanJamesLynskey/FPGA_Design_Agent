"""One deliberately violating design per checked rule of docs/design_standards.md fails with the rule id; the
reference design (T1) and a clean fixture pass; waivers need a reason (brief 05d)."""

import shutil
from pathlib import Path

import pytest
import yaml

from flow import standards_check as sc

ROOT = Path(__file__).resolve().parents[2]
ARCH = {"schema": "fpga-design-agent/architecture/v1", "blocks": [{"name": "m", "function": "x"}], "interfaces": [],
        "clock_domains": [{"name": "sys", "clock": "clk", "freq_mhz": 100}], "crossings": [],
        "predicted_resources": {"lut": [1, 10], "ff": [1, 10], "bram_tile": 0, "dsp": 0}}
CLEAN = """module m (input logic clk, input logic rst, input logic d, output logic q);
    always_ff @(posedge clk) begin
        if (rst) q <= 1'b0; else q <= d;
    end
endmodule
"""
has_vl = shutil.which("verilator") is not None


def make(tmp_path, rtl, arch=None, name="m"):
    d = tmp_path / "designs" / "x"
    (d / "rtl").mkdir(parents=True)
    (d / "rtl" / "m.sv").write_text(rtl)
    (d / "architecture.yaml").write_text(yaml.safe_dump({**ARCH, **(arch or {})}))
    (d / "build.yaml").write_text(f"top: {name}\npart: p\nsources: [designs/x/rtl/*.sv]\nconstraints: [designs/x/design.xdc]\n")
    return d


def run(tmp_path, rtl, arch=None, name="m"):
    d = make(tmp_path, rtl, arch, name)
    return {r["id"]: r for r in sc.evaluate(d, tmp_path, stages=("rtl",))["rules"]}


def failing(res):
    return {k for k, v in res.items() if v["status"] == "fail"}


def test_clean_design_passes_the_static_rules(tmp_path):
    res = run(tmp_path, CLEAN)
    assert failing(res) == set(), {k: v["findings"] for k, v in res.items() if v["findings"]}


def test_reference_design_passes():
    r = sc.evaluate(ROOT / "designs" / "t1_dimmer_counter", ROOT, stages=("rtl",))
    bad = [(x["id"], x["findings"], x.get("why_not_run")) for x in r["rules"] if x["status"] in ("fail", "not_run")]
    if not has_vl:
        bad = [b for b in bad if b[0] not in ("STD-LATCH-01", "STD-LOOP-01")]
    assert not bad, bad


def test_arch_00_missing_architecture(tmp_path):
    d = make(tmp_path, CLEAN)
    (d / "architecture.yaml").unlink()
    res = {r["id"]: r for r in sc.evaluate(d, tmp_path, stages=("rtl",))["rules"]}
    assert res["STD-ARCH-00"]["status"] == "fail"


def test_clk_01_derived_clock_from_assign(tmp_path):
    rtl = """module m (input logic clk, input logic rst, input logic en, output logic q);
    logic gclk;
    assign gclk = clk & en;
    always_ff @(posedge gclk) q <= ~q;
endmodule
"""
    assert "STD-CLK-01" in failing(run(tmp_path, rtl))


def test_clk_01_derived_clock_from_register(tmp_path):
    rtl = """module m (input logic clk, input logic rst, output logic q);
    logic div;
    always_ff @(posedge clk) div <= ~div;
    always_ff @(posedge div) q <= ~q;
endmodule
"""
    assert "STD-CLK-01" in failing(run(tmp_path, rtl))


def test_clk_01_gating_primitive(tmp_path):
    rtl = """module m (input logic clk, input logic en, output logic q);
    logic g;
    BUFGCE u_g (.I(clk), .CE(en), .O(g));
    always_ff @(posedge clk) q <= ~q;
endmodule
"""
    assert "STD-CLK-01" in failing(run(tmp_path, rtl))


def test_clk_02_undeclared_top_clock(tmp_path):
    rtl = CLEAN.replace("clk", "other_clk")
    assert "STD-CLK-02" in failing(run(tmp_path, rtl))


def test_rst_01_asynchronous_reset(tmp_path):
    rtl = """module m (input logic clk, input logic rst_n, input logic d, output logic q);
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) q <= 1'b0; else q <= d;
    end
endmodule
"""
    assert "STD-RST-01" in failing(run(tmp_path, rtl))
    ok = run(tmp_path / "w", rtl, {"reset": {"synchronisers": ["m"]}})
    assert "STD-RST-01" not in failing(ok)


def test_init_01_initial_block(tmp_path):
    rtl = CLEAN.replace("    always_ff", "    initial q = 1'b0;\n    always_ff")
    assert "STD-INIT-01" in failing(run(tmp_path, rtl))
    rom = CLEAN.replace("    always_ff", "    logic [7:0] rom [0:3];\n    initial $readmemh(\"r.hex\", rom);\n    always_ff")
    assert "STD-INIT-01" not in failing(run(tmp_path / "r", rom))
    off = CLEAN.replace("    always_ff", "    // synthesis translate_off\n    initial q = 1'b0;\n    // synthesis translate_on\n    always_ff")
    assert "STD-INIT-01" not in failing(run(tmp_path / "o", off))


def test_cdc_01_two_clocks_in_one_module_and_unlisted_crossing(tmp_path):
    rtl = """module m (input logic clk, input logic clk2, input logic d, output logic q, output logic q2);
    always_ff @(posedge clk) q <= d;
    always_ff @(posedge clk2) q2 <= q;
endmodule
"""
    arch = {"clock_domains": [{"name": "a", "clock": "clk"}, {"name": "b", "clock": "clk2"}]}
    res = run(tmp_path, rtl, arch)
    assert "STD-CDC-01" in failing(res)
    assert any("no crossing is listed" in f["message"] for f in res["STD-CDC-01"]["findings"])


def test_cdc_01_listed_primitive_not_instantiated(tmp_path):
    arch = {"clock_domains": [{"name": "a", "clock": "clk"}, {"name": "b", "clock": "clk2"}],
            "crossings": [{"from": "a", "to": "b", "signal": "q", "primitive": "sync_2ff"}]}
    res = run(tmp_path, CLEAN, arch)
    assert any("not instantiated" in f["message"] for f in res["STD-CDC-01"]["findings"])


def test_axi_01_missing_and_wrong_direction_ports(tmp_path):
    rtl = """module m (input logic clk, input logic s_axis_tdata, input logic s_axis_tvalid, input logic s_axis_tready,
    output logic q);
    always_ff @(posedge clk) q <= s_axis_tvalid;
endmodule
"""
    arch = {"interfaces": [{"name": "in", "protocol": "axi4-stream", "prefix": "s_axis"}]}
    res = run(tmp_path, rtl, arch)
    assert "STD-AXI-01" in failing(res)
    assert any("tready is input, expected output" in f["message"] for f in res["STD-AXI-01"]["findings"])


def test_axi_02_undeclared_axi_looking_port(tmp_path):
    rtl = """module m (input logic clk, input logic s_axi_awvalid, output logic q);
    always_ff @(posedge clk) q <= s_axi_awvalid;
endmodule
"""
    assert "STD-AXI-02" in failing(run(tmp_path, rtl))


def test_waive_01_needs_a_reason(tmp_path):
    rtl = CLEAN.replace("    always_ff", "    initial q = 1'b0; // std-waive: STD-INIT-01\n    always_ff")
    assert "STD-WAIVE-01" in failing(run(tmp_path, rtl))
    good = CLEAN.replace("    always_ff", "    initial q = 1'b0; // std-waive: STD-INIT-01 simulation-only start value\n    always_ff")
    assert failing(run(tmp_path / "g", good)) == set()


@pytest.mark.skipif(not has_vl, reason="Verilator not installed here (the lint and verification CI jobs have it)")
def test_latch_01_inferred_latch(tmp_path):
    rtl = """module m (input logic clk, input logic en, input logic d, output logic q);
    always_latch if (en) q = d;
endmodule
"""
    assert "STD-LATCH-01" in failing(run(tmp_path, rtl))


@pytest.mark.skipif(not has_vl, reason="Verilator not installed here (the lint and verification CI jobs have it)")
def test_loop_01_combinational_loop(tmp_path):
    rtl = """module m (input logic clk, input logic a, output logic q);
    logic x, y;
    assign x = y ^ a;
    assign y = x & a;
    always_ff @(posedge clk) q <= x;
endmodule
"""
    assert "STD-LOOP-01" in failing(run(tmp_path, rtl))


def test_unchecked_rule_is_not_a_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(sc.Check, "_tool", lambda self, n: None)
    d = make(tmp_path, CLEAN)
    r = sc.evaluate(d, tmp_path, stages=("rtl",))
    st = {x["id"]: x["status"] for x in r["rules"]}
    assert st["STD-LATCH-01"] == "not_run" and r["pass"] is False


def test_post_synth_rules_read_the_reports(tmp_path):
    d = make(tmp_path, CLEAN)
    b = d / "build" / "base"
    b.mkdir(parents=True)
    (b / "gates.json").write_text('{"stages": {"post_synth": {"ran": true, "gates": {"post_synth_cdc_no_critical": false, '
                                  '"post_synth_methodology_no_critical": false}, "cdc": {"rules": [{"id": "CDC-1", '
                                  '"severity": "Critical", "count": 2}]}, "methodology": {"rules": []}}}}')
    (b / "clock_networks_synth.rpt").write_text("Clock gclk (100MHz)(endpoints: 4)\nNet foo/gclk\n")
    r = {x["id"]: x for x in sc.evaluate(d, tmp_path, stages=("post_synth",))["rules"]}
    assert r["STD-CDC-02"]["status"] == "fail" and r["STD-METH-01"]["status"] == "fail"
    assert r["STD-CLK-03"]["status"] == "fail"


def test_every_rule_documents_how_it_is_checked():
    doc = (ROOT / "docs" / "design_standards.md").read_text()
    for rid, (_, _, how) in sc.RULES.items():
        assert rid in doc, rid
