"""Brief 231 item 1c (owner, 2026-11-26): initial values and resets agree (STD-INIT-02, setting rtl.reset_model)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml  # noqa: E402

from flow import standards_check as sc  # noqa: E402
from flow.tests.test_standards_check import make  # noqa: E402

HDR = "module m (input logic clk, input logic rst, input logic d, output logic q, output logic v);\n"


def mod(decls, body):
    return HDR + decls + "    always_ff @(posedge clk) begin\n" + body + "    end\n    assign q = d;\n    assign v = 1'b0;\nendmodule\n"


def run(tmp_path, rtl, arch=None, settings=None, spec=None):
    d = make(tmp_path, rtl, arch)
    if spec is not None:
        (d / "spec.yaml").write_text(yaml.safe_dump(spec))
    out = sc.evaluate(d, tmp_path, stages=("rtl",), settings=settings)
    return {r["id"]: r for r in out["rules"]}, out


def msgs(res):
    return [f["message"] for f in res["STD-INIT-02"]["findings"]]


DATA_NO_RESET = mod("    logic [7:0] cnt = '0;\n", "        cnt <= cnt + 8'd1;\n")
SAME = mod("    logic [7:0] cnt = '0;\n", "        if (rst) cnt <= 8'd0; else cnt <= cnt + 8'd1;\n")
DIFF = mod("    logic [7:0] cnt = 8'd5;\n", "        if (rst) cnt <= 8'd0; else cnt <= cnt + 8'd1;\n")
CTRL_INIT_ONLY = mod("    logic busy = 1'b0;\n", "        busy <= d;\n")
CTRL_RESET = mod("    logic busy = 1'b0;\n", "        if (rst) busy <= 1'b0; else busy <= d;\n")
CTRL_NEITHER = mod("    logic busy;\n", "        busy <= d;\n")
DATA_NEITHER = mod("    logic [7:0] sample;\n", "        sample <= {7'd0, d};\n")
ENDS_ONES = mod("    logic [3:0] mask = 4'b1111;\n", "        if (!rst) mask <= '1; else mask <= mask;\n")


def test_data_register_with_initial_value_and_no_reset_passes(tmp_path):
    res, _ = run(tmp_path, DATA_NO_RESET)
    assert res["STD-INIT-02"]["status"] == "pass"


def test_initial_value_equal_to_reset_value_passes(tmp_path):
    assert run(tmp_path, SAME)[0]["STD-INIT-02"]["status"] == "pass"
    assert run(tmp_path / "o", ENDS_ONES)[0]["STD-INIT-02"]["status"] == "pass"          # 4'b1111 and '1 are the same value


def test_reset_and_a_different_initial_value_is_a_finding(tmp_path):
    res, _ = run(tmp_path, DIFF)
    assert res["STD-INIT-02"]["status"] == "fail"
    assert "initial value 8'd5" in msgs(res)[0] and "reset value 8'd0" in msgs(res)[0]
    assert run(tmp_path / "r", DIFF, {"rtl": {"reset_model": "reprogram"}})[0]["STD-INIT-02"]["status"] == "fail"   # in every model


def test_control_state_with_only_an_initial_value_needs_its_reset(tmp_path):
    res, _ = run(tmp_path, CTRL_INIT_ONLY)
    assert res["STD-INIT-02"]["status"] == "fail" and "control register busy" in msgs(res)[0]
    assert "reset_model to reprogram" in msgs(res)[0]
    assert run(tmp_path / "k", CTRL_RESET)[0]["STD-INIT-02"]["status"] == "pass"


def test_reprogram_model_lets_control_state_rely_on_its_initial_value(tmp_path):
    arch = {"rtl": {"reset_model": "reprogram"}}
    res, out = run(tmp_path, CTRL_INIT_ONLY, arch)
    assert res["STD-INIT-02"]["status"] == "pass"
    assert out["settings"]["rtl.reset_model"] == "reprogram" and out["settings"]["source"]["rtl.reset_model"] == "architecture.yaml"
    assert out["notes"]["reset_model"] == "rtl.reset_model = reprogram (architecture.yaml)"


def test_reprogram_model_flags_control_state_with_neither(tmp_path):
    arch = {"rtl": {"reset_model": "reprogram"}}
    res, _ = run(tmp_path, CTRL_NEITHER, arch)
    assert res["STD-INIT-02"]["status"] == "fail" and "neither an initial value nor a reset" in msgs(res)[0]
    assert run(tmp_path / "d", DATA_NEITHER, arch)[0]["STD-INIT-02"]["status"] == "pass"          # a data register is not control state
    assert run(tmp_path / "n", CTRL_NEITHER)[0]["STD-INIT-02"]["status"] == "pass"                 # model reset: this rule is silent


def test_setting_sources_and_validation(tmp_path):
    res, out = run(tmp_path, CTRL_INIT_ONLY, settings={"rtl.reset_model": "reprogram"})
    assert res["STD-INIT-02"]["status"] == "pass" and out["settings"]["source"]["rtl.reset_model"] == "--set"
    _, out = run(tmp_path / "s", CTRL_INIT_ONLY, spec={"reset": {"model": "reprogram"}})
    assert out["settings"]["rtl.reset_model"] == "reprogram" and out["settings"]["source"]["rtl.reset_model"] == "spec.yaml"
    _, out = run(tmp_path / "a", CTRL_INIT_ONLY, {"rtl": {"reset_model": "reset"}}, spec={"reset": {"model": "reprogram"}})
    assert out["settings"]["rtl.reset_model"] == "reset"                                           # architecture.yaml beats spec.yaml
    try:
        run(tmp_path / "bad", CTRL_INIT_ONLY, spec={"reset": {"model": "sometimes"}})
    except ValueError as e:
        assert "rtl.reset_model" in str(e)
    else:
        raise AssertionError("an unknown reset model must be refused")


def test_deny_mode_leaves_it_to_std_init_01_and_a_waiver_excuses(tmp_path):
    res, _ = run(tmp_path, DIFF, {"rtl": {"initial_values": "deny"}})
    assert res["STD-INIT-02"]["status"] == "pass" and res["STD-INIT-01"]["status"] == "fail"
    waived = DIFF.replace("    logic [7:0] cnt = 8'd5;", "    logic [7:0] cnt = 8'd5; // std-waive: STD-INIT-02 test fixture")
    assert run(tmp_path / "w", waived)[0]["STD-INIT-02"]["status"] == "pass"


def test_non_literal_values_are_not_compared(tmp_path):
    rtl = mod("    localparam logic [7:0] START = 8'd5;\n    logic [7:0] cnt = START;\n",
              "        if (rst) cnt <= 8'd0; else cnt <= cnt + 8'd1;\n")
    assert run(tmp_path, rtl)[0]["STD-INIT-02"]["status"] == "pass"


def test_the_rule_is_mapped_in_the_ruleset():
    import flow.lint_ruleset as lr
    rs = lr.load_rules()
    assert any("STD-INIT-02" in (r.get("checks") or {}).get("standards", []) for r in rs["rules"])
