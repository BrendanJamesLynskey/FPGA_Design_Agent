"""pytest entry: the generated b65a_axil_soc_top under cocotb + Icarus, end to end through the UART test shell (8 clocks a
bit), with brief 59's AXI4-Lite checker on every AXI4-Lite link of the top level (the bench is written from
gen/graph.json, so a link the generator adds is watched without editing this file)."""
from __future__ import annotations

import glob
import json
from pathlib import Path

import yaml

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent
ROOT = DESIGN.parents[1]
BUILD = ROOT / "build" / "sim" / "b65a_tb"
CHECKER = [ROOT / "axi_tx" / "rtl" / f for f in ("axil_checker.sv", "axil_rules.sv", "axi_viol_log.sv")]
PARAMS = {"SHELL_CLKS_PER_BIT": 8, "SHELL_TIMEOUT_CYCLES": 400, "TONE_FD_GATE_CLKS": 4000}
SIGS = ["awaddr", "awprot", "awvalid", "awready", "wdata", "wstrb", "wvalid", "wready", "bresp", "bvalid", "bready",
        "araddr", "arprot", "arvalid", "arready", "rdata", "rresp", "rvalid", "rready"]


def write_tb() -> tuple[Path, list[str]]:
    """b65a_tb.sv: the generated top plus one axil_checker per top-level AXI4-Lite link, by hierarchical reference."""
    g = json.loads((DESIGN / "gen" / "graph.json").read_text())
    links = [L["id"] for L in g["levels"][""]["links"] if L["kind"] == "axi4lite"]
    L = ["// b65a_tb.sv: written by tests/test_b65a_rtl.py from gen/graph.json; the generated top and an AXI4-Lite checker per link.",
         "module b65a_tb #(", ",\n".join(f"    parameter int {k} = {v}" for k, v in PARAMS.items()), ") (",
         "    input  logic CLK100MHZ, input logic CPU_RESETN, input logic UART_TXD_IN,",
         "    output logic UART_RXD_OUT, output logic [15:0] LED,",
         f"    output logic [{len(links) - 1}:0] chk_any", ");",
         "    b65a_axil_soc_top #(" + ", ".join(f".{k}({k})" for k in PARAMS) + ") dut (.*);",
         "    logic [31:0] now = '0;", "    always_ff @(posedge CLK100MHZ) now <= now + 1'b1;"]
    for i, ln in enumerate(links):
        conn = ", ".join(f".{s}(dut.{ln}__{s})" for s in SIGS)
        L.append(f"    axil_checker #(.ADDR_W(32), .DATA_W(32)) u_chk_{ln} (.aclk(CLK100MHZ), .aresetn(!dut.rst_sync_sys__rst), "
                 f".clear(1'b0), .en(10'h3FF), .now(now), {conn}, .viol(), .trig(), .any(chk_any[{i}]), .rd_sel(6'd0), .rd_data());")
    L.append("endmodule\n")
    BUILD.mkdir(parents=True, exist_ok=True)
    p = BUILD / "b65a_tb.sv"
    p.write_text("\n".join(L))
    return p, links


def test_generated_design_end_to_end() -> None:
    tb, links = write_tb()
    b = yaml.safe_load((DESIGN / "build.yaml").read_text())
    srcs = [Path(ROOT / f) for g in b["sources"] for f in sorted(glob.glob(str(ROOT / g)))]
    cocotb_run.run("b65a_axil_soc", "b65a_tb", srcs + CHECKER + [tb], "b65a_cocotb", HERE, parameters=PARAMS, seed=1,
                   extra_env={"B65A_LINKS": json.dumps(links)})
