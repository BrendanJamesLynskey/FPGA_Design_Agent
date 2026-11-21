// brief 96F1b: lint-only stand-in for AMD's xpm_cdc_async_rst (UG974: asynchronous assert, synchronous release; the flow's cdc_models do not have this macro). Ports and parameters as the macro's; written from its
// documented behaviour, not from AMD's source. Vivado builds use the real macro.
/* verilator lint_off UNUSEDPARAM */   // INIT_SYNC_FF and VERSION exist for the macro's interface only
module xpm_cdc_async_rst #(
    parameter integer DEST_SYNC_FF    = 4,
    parameter integer INIT_SYNC_FF    = 0,
    parameter integer RST_ACTIVE_HIGH = 0,
    parameter integer VERSION         = 0
) (
    input  wire src_arst,
    input  wire dest_clk,
    output wire dest_arst
);
    wire arst = (RST_ACTIVE_HIGH != 0) ? src_arst : !src_arst;                 // 1 = reset asserted
    logic [DEST_SYNC_FF-1:0] st = '1;
    always_ff @(posedge dest_clk or posedge arst) begin
        if (arst) st <= '1;
        else      st <= {st[DEST_SYNC_FF-2:0], 1'b0};
    end
    assign dest_arst = (RST_ACTIVE_HIGH != 0) ? st[DEST_SYNC_FF-1] : !st[DEST_SYNC_FF-1];
endmodule
/* verilator lint_on UNUSEDPARAM */
