// xpm_formal.sv (brief 115): formal stand-ins for the three AMD clock-crossing macros that rate_match_gp.sv instantiates.
// Proof model, not the macros: each crossing is a chain of flip-flops in the destination clock (the source side of xpm_cdc_gray is one register in the source clock, as in AMD's macro).
//
// Metastability / skew abstraction (documented in docs/formal_study_notes.md, section 4). Physically: each bit has its own small delay (routing, clock-to-out, a flop resolving), less than one source clock;
//   a destination edge that falls in the window after a source edge may therefore see the OLD value of any bit that changed at that source edge, independently per bit.
//   Model: dlast is the value d had at the previous source edge, so d != dlast exactly in the interval after a source edge that changed it. At a destination edge, every bit that differs may show its old value
//   (the free choice sk), at most once per change, and never after it has shown the new value (held, s[0]: a flop whose input is stable resolves within a clock, and a value does not go back). A bit that changed more than one source clock ago is settled and never shows old.
//   A multi-bit binary value can therefore be seen torn (some bits old, some new); a gray value, which changes one bit per source clock, cannot be seen as anything but the old or the new code.
//   What is NOT modelled: skew larger than one source clock; per-bit differences in how long a flop takes to resolve beyond one destination clock (the timing constraints and report_cdc cover those).
// FV_BIN_CROSSING (mutant only): the pointer crosses as plain binary instead of gray.
module fv_sync_chain #(parameter int W = 1, parameter int N = 2, parameter bit SHARED = 1'b0) (
    input  wire         src_clk,
    input  wire         dest_clk,
    input  wire [W-1:0] d,
    output wire [W-1:0] q
);
    // SHARED = 1 (the entry copies): one free choice for the whole word. Sound for the data-integrity claim because lateness only hurts: the set of clocks at which some bit still shows old is largest when every bit that changed is
    // late together, so the all-late schedule dominates every per-bit schedule; it is ~74x fewer free bits per entry for the solver. SHARED = 0 (pointers, single bits): one free choice per bit (tearing matters there).
    (* anyseq *) logic [W-1:0] sk_bits;
    (* anyseq *) logic         sk_one;
    wire [W-1:0] sk = SHARED ? {W{sk_one}} : sk_bits;
    logic [N-1:0][W-1:0] s = '0;
    logic [W-1:0] dlast = '0;
    logic [W-1:0] held = '0;
    logic [W-1:0] late;
    assign late = (d ^ dlast) & sk & ~held & ~(s[0] ^ dlast);    // only a bit that has not yet shown its new value can still show the old one, and only once
    always_ff @(posedge src_clk) dlast <= d;
    always_ff @(posedge dest_clk) begin
        s[0] <= (d & ~late) | (dlast & late);
        held <= late;
        for (int i = 1; i < N; i++) s[i] <= s[i-1];
    end
    assign q = s[N-1];
endmodule

module xpm_cdc_single #(parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0, parameter integer SIM_ASSERT_CHK = 0, parameter integer SRC_INPUT_REG = 1) (
    input wire src_clk, input wire src_in, input wire dest_clk, output wire dest_out);
    fv_sync_chain #(.W(1), .N(DEST_SYNC_FF)) u (.src_clk, .dest_clk, .d(src_in), .q(dest_out));
endmodule

module xpm_cdc_array_single #(parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0, parameter integer SIM_ASSERT_CHK = 0, parameter integer SRC_INPUT_REG = 1, parameter integer WIDTH = 2) (
    input wire src_clk, input wire [WIDTH-1:0] src_in, input wire dest_clk, output wire [WIDTH-1:0] dest_out);
    fv_sync_chain #(.W(WIDTH), .N(DEST_SYNC_FF), .SHARED(1'b1)) u (.src_clk, .dest_clk, .d(src_in), .q(dest_out));
endmodule

module xpm_cdc_gray #(parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0, parameter integer REG_OUTPUT = 0, parameter integer SIM_ASSERT_CHK = 0,
                      parameter integer SIM_LOSSLESS_GRAY_CHK = 0, parameter integer WIDTH = 2) (
    input wire src_clk, input wire [WIDTH-1:0] src_in_bin, input wire dest_clk, output wire [WIDTH-1:0] dest_out_bin);
    logic [WIDTH-1:0] g = '0, dg;
    wire  [WIDTH-1:0] b;
`ifdef FV_BIN_CROSSING
    always_ff @(posedge src_clk) g <= src_in_bin;
`else
    always_ff @(posedge src_clk) g <= src_in_bin ^ (src_in_bin >> 1);
`endif
    fv_sync_chain #(.W(WIDTH), .N(DEST_SYNC_FF)) u (.src_clk, .dest_clk, .d(g), .q(dg));
`ifdef FV_BIN_CROSSING
    assign b = dg;
`else
    for (genvar i = 0; i < WIDTH; i++) begin : dec
        assign b[i] = ^dg[WIDTH-1:i];
    end
`endif
    logic [WIDTH-1:0] o = '0;
    always_ff @(posedge dest_clk) o <= b;
    assign dest_out_bin = REG_OUTPUT ? o : b;
endmodule
