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


def warning_rules(res):
    return {k for k, v in res.items() if v["status"] == "warn"}


DENY = {"rtl": {"initial_values": "deny"}}
WARN = {"rtl": {"initial_values": "warn"}}
INIT_Q = CLEAN.replace("    always_ff", "    initial q = 1'b0;\n    always_ff")
DECL_Q = CLEAN.replace("output logic q);", "output logic q);\n    logic valid = 1'b0;")
MEM_FILL = CLEAN.replace("    always_ff", "    logic [7:0] mem [0:3];\n    initial begin\n        for (int i = 0; i < 4; i++) mem[i] = 8'h00;\n    end\n    always_ff")
ROM = CLEAN.replace("    always_ff", "    logic [7:0] rom [0:3];\n    initial $readmemh(\"r.hex\", rom);\n    always_ff")
OFF = CLEAN.replace("    always_ff", "    // synthesis translate_off\n    initial q = 1'b0;\n    // synthesis translate_on\n    always_ff")
MORE = {"a delay": "initial begin q = 1'b0; #10 q = 1'b1; end", "$display": "initial begin q = 1'b0; $display(\"x\"); end",
        "if": "initial begin if (rst) q = 1'b1; else q = 1'b0; end", "wait": "initial begin wait (rst); q = 1'b0; end",
        "forever": "initial forever q = ~q;", "$finish": "initial begin q = 1'b0; $finish; end"}


def with_initial(text, block):
    return CLEAN.replace("    always_ff", f"    {block}\n    always_ff")


def test_init_01_default_is_allow(tmp_path):
    res = run(tmp_path, INIT_Q)
    assert res["STD-INIT-01"]["status"] == "pass"
    out = sc.evaluate(make(tmp_path / "e", INIT_Q), tmp_path / "e", stages=("rtl",))
    assert out["settings"]["rtl.initial_values"] == "allow" and out["settings"]["source"]["rtl.initial_values"] == "default"
    assert out["notes"]["initial_values"] == "rtl.initial_values = allow (default)"
    assert sc.DEFAULT_INITIAL_VALUES == "allow"


def test_init_01_allow_passes_power_up_values_and_memory_fill(tmp_path):
    for i, rtl in enumerate((INIT_Q, DECL_Q, MEM_FILL, ROM, OFF)):
        assert "STD-INIT-01" not in failing(run(tmp_path / str(i), rtl, {"rtl": {"initial_values": "allow"}})), i


@pytest.mark.parametrize("what", sorted(MORE))
def test_init_01_allow_still_flags_an_initial_block_that_does_more(tmp_path, what):
    res = run(tmp_path, with_initial(CLEAN, MORE[what]))
    assert "STD-INIT-01" in failing(res)
    assert "does more than set power-up values" in res["STD-INIT-01"]["findings"][0]["message"]


def test_init_01_allow_accepts_constant_maths_in_a_table(tmp_path):
    rtl = with_initial(CLEAN, "logic [7:0] t [0:3];\n    initial begin for (int i = 0; i < 4; i++) t[i] = 8'($sin(i)); end")
    assert "STD-INIT-01" not in failing(run(tmp_path, rtl))


def test_init_01_deny_is_the_earlier_behaviour(tmp_path):
    assert "STD-INIT-01" in failing(run(tmp_path, INIT_Q, DENY))
    assert "STD-INIT-01" in failing(run(tmp_path / "m", MEM_FILL, DENY))
    assert "STD-INIT-01" in failing(run(tmp_path / "d", DECL_Q, DENY))
    assert "STD-INIT-01" in failing(run(tmp_path / "x", with_initial(CLEAN, MORE["a delay"]), DENY))
    assert "STD-INIT-01" not in failing(run(tmp_path / "r", ROM, DENY))
    assert "STD-INIT-01" not in failing(run(tmp_path / "o", OFF, DENY))
    assert "STD-INIT-01" not in failing(run(tmp_path / "c", CLEAN, DENY))


def test_init_01_warn_reports_without_failing(tmp_path):
    for i, rtl in enumerate((INIT_Q, DECL_Q, MEM_FILL, with_initial(CLEAN, MORE["a delay"]))):
        d = make(tmp_path / str(i), rtl, WARN)
        out = sc.evaluate(d, tmp_path / str(i), stages=("rtl",))
        r = {x["id"]: x for x in out["rules"]}["STD-INIT-01"]
        assert r["status"] == "warn" and r["findings"] == [] and r["warnings"], i
        assert out["pass"] and out["stages"]["rtl"]
    assert "STD-INIT-01" not in warning_rules(run(tmp_path / "r", ROM, WARN))
    assert run(tmp_path / "c", CLEAN, WARN)["STD-INIT-01"]["status"] == "pass"


def test_init_01_rom_initialisation_passes_in_every_mode(tmp_path):
    for mode in sc.INITIAL_VALUES_MODES:
        assert run(tmp_path / mode, ROM, {"rtl": {"initial_values": mode}})["STD-INIT-01"]["status"] == "pass", mode


def test_init_01_local_variables_are_not_register_initial_values(tmp_path):
    rtl = CLEAN.replace("    always_ff", "    function automatic logic f(input logic a);\n        logic t = a;\n        return t;\n    endfunction\n    always_ff")
    assert "STD-INIT-01" not in failing(run(tmp_path, rtl, DENY))


def test_init_01_the_run_setting_beats_the_design_and_the_flow_default(tmp_path):
    d = make(tmp_path, INIT_Q, DENY)
    out = sc.evaluate(d, tmp_path, stages=("rtl",), settings={"rtl.initial_values": "allow"})
    assert out["pass"] and out["settings"]["source"]["rtl.initial_values"] == "--set"
    out = sc.evaluate(d, tmp_path, stages=("rtl",))
    assert not out["pass"] and out["settings"]["source"]["rtl.initial_values"] == "architecture.yaml"
    flow = tmp_path / "flow"
    flow.mkdir()
    (flow / "gates.yaml").write_text("rtl:\n  initial_values: deny\n")
    d2 = make(tmp_path / "g", INIT_Q)
    out = sc.evaluate(d2, tmp_path, stages=("rtl",))
    assert not out["pass"] and out["settings"]["source"]["rtl.initial_values"] == "flow/gates.yaml"


def test_init_01_an_unknown_value_is_refused(tmp_path):
    d = make(tmp_path, INIT_Q, {"rtl": {"initial_values": "maybe"}})
    with pytest.raises(ValueError, match="rtl.initial_values"):
        sc.evaluate(d, tmp_path, stages=("rtl",))
    assert sc.main([str(d), "--stage", "rtl"]) == 1                      # the CLI reports it as STD-ARCH-00, not a traceback
    assert "rtl" in sc.arch_mod.check_architecture({**ARCH, "rtl": {"initial_values": "maybe"}})[0]
    assert sc.arch_mod.check_architecture({**ARCH, "rtl": {"initial_values": "warn"}}) == []


def test_init_01_cli_set(tmp_path, capsys):
    d = make(tmp_path, INIT_Q, DENY)
    assert sc.main([str(d), "--stage", "rtl", "--root", str(tmp_path), "--set", "rtl.initial_values=allow"]) == 0
    assert "rtl.initial_values" not in capsys.readouterr().err
    assert sc.main([str(d), "--stage", "rtl", "--root", str(tmp_path)]) == 1
    with pytest.raises(SystemExit):
        sc.main([str(d), "--set", "rtl.initial_values=bogus"])
    d2 = make(tmp_path / "w", INIT_Q, WARN)
    assert sc.main([str(d2), "--stage", "rtl", "--root", str(tmp_path / "w")]) == 0
    assert "warn" in capsys.readouterr().out


def test_init_01_the_reset_rules_do_not_change(tmp_path):
    """An initial value is a power-up state, not a reset: an asynchronous reset still fails in every mode."""
    rtl = """module m (input logic clk, input logic rst_n, input logic d, output logic q);
    logic v = 1'b0;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) q <= 1'b0; else q <= d;
    end
endmodule
"""
    for mode in sc.INITIAL_VALUES_MODES:
        res = run(tmp_path / mode, rtl, {"rtl": {"initial_values": mode}})
        assert "STD-RST-01" in failing(res), mode


def test_init_01_the_check_suite_shows_a_warning_that_does_not_block(tmp_path):
    from flow import checks as C
    d = make(tmp_path, INIT_Q, WARN)
    res = C.CHECKS["standards"].run(C.Ctx(design=d, scope="rtl"))
    fs = [f for f in res["findings"] if f["code"] == "STD-INIT-01"]
    assert fs and all(f["blocking"] is False and f["severity"] == "warning" for f in fs)
    d2 = make(tmp_path / "d", INIT_Q, DENY)
    res = C.CHECKS["standards"].run(C.Ctx(design=d2, scope="rtl"))
    assert any(f["code"] == "STD-INIT-01" and f["blocking"] for f in res["findings"])


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
    assert "STD-INIT-01" in failing(run(tmp_path / "d", rtl, DENY))                  # a waiver without a reason excuses nothing
    assert failing(run(tmp_path / "e", good, DENY)) == set()                         # existing waivers keep working under deny


@pytest.mark.skipif(not has_vl, reason="Verilator not installed here (the lint and verification CI jobs have it)")
def test_latch_01_inferred_latch(tmp_path):
    rtl = """module m (input logic clk, input logic en, input logic d, output logic q);
    always_comb if (en) q = d;
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


def test_cdc_01_inline_in_may_name_a_shell_module(tmp_path):
    (tmp_path / "shell" / "rtl").mkdir(parents=True)
    (tmp_path / "shell" / "rtl" / "reset_sync.sv").write_text("module reset_sync(input logic clk, input logic a, output logic rst);\nendmodule\n")
    (tmp_path / "b" / "shell" / "rtl").mkdir(parents=True)
    (tmp_path / "b" / "shell" / "rtl" / "reset_sync.sv").write_text("module reset_sync(input logic clk, input logic a, output logic rst);\nendmodule\n")
    arch = {"crossings": [{"from": "async", "to": "sys", "signal": "rst", "primitive": "reset_sync", "inline_in": "reset_sync"}]}
    assert "STD-CDC-01" not in failing(run(tmp_path, CLEAN, arch))
    arch["crossings"][0]["inline_in"] = "no_such_module"
    assert "STD-CDC-01" in failing(run(tmp_path / "b", CLEAN, arch))
