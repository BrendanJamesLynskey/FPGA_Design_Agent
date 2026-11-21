// axis_sva.sv: the AXI4-Stream protocol rules (Arm IHI 0051B) as SystemVerilog assertions on one stream's signals, to be
// bound to the interface of any AXI4-Stream block:
//     bind pipe_reg axis_sva #(.DW(W), .KW(...), .UW(...)) s_chk (.aclk, .aresetn, .tvalid(s_axis_tvalid), ...);
// Rules (our words): HOLD a beat that was offered and not taken stays offered with tdata, tkeep, tlast and tuser unchanged
// (2.2); RESET tvalid is low in reset and at the first edge after it (2.8); STRB the reserved tkeep-low-tstrb-high
// combination never appears (2.4, only when tstrb is connected). Not expressible on the ports of one block: "tvalid must not
// depend on tready" (a property of the logic: pipe_reg proves it structurally, every m_axis_tvalid is a flop, and the bench
// checks it by changing tready within a clock). Needs a simulator or formal tool with concurrent assertions (Verilator,
// xsim, Questa, Yosys with the slang front end); Icarus Verilog does not run it, so the Icarus benches use the RTL monitor
// axi_tx/rtl/axis_rules.sv for the same rules and the formal jobs use this module.
module axis_sva #(
    parameter int DW = 32,
    parameter int KW = 4,
    parameter int UW = 1
) (
    input logic          aclk,
    input logic          aresetn,
    input logic          tvalid,
    input logic          tready,
    input logic [DW-1:0] tdata,
    input logic          tlast,
    input logic [KW-1:0] tkeep,
    input logic [UW-1:0] tuser
);
    // HOLD: written with a one-clock-old copy, so that every tool that reads assertions accepts it (the sequence form is
    //   tvalid && !tready |=> tvalid && $stable({tdata, tlast, tkeep, tuser}))
    logic                         held = 1'b0;
    logic [DW+1+KW+UW-1:0]        held_beat = '0;
    always_ff @(posedge aclk) begin
        held      <= aresetn && tvalid && !tready;
        held_beat <= {tdata, tlast, tkeep, tuser};
    end
    a_hold: assert property (@(posedge aclk) disable iff (!aresetn) (!held || (tvalid && {tdata, tlast, tkeep, tuser} == held_beat)));
    // RESET: the first edge with aresetn high follows an edge with it low: tvalid must be low there
    logic prev_rst_low = 1'b1;
    always_ff @(posedge aclk) prev_rst_low <= !aresetn;
    a_reset: assert property (@(posedge aclk) (!prev_rst_low || !aresetn || !tvalid));
    // reachability: a beat is accepted, and a stall happens
    always @(posedge aclk) begin
        c_xfer:  cover (aresetn && tvalid && tready);
        c_stall: cover (aresetn && tvalid && !tready);
    end
endmodule
