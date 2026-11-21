// pipe_reg.sv: AXI4-Stream pipeline register with back-pressure (brief 151, library entry; owner 2026-11-21: favour AMBA AXI).
//
// The top module pipe_reg is an AXI4-Stream slave port, a chain of N register slices and an AXI4-Stream master port.
// pipe_reg_core below is the same chain on a bare valid/ready/data word; the slice modules are in pipe_reg_slice.sv.
// AXI4-Stream (Arm IHI 0051B) rules kept by every MODE: tvalid never depends on tready (m_axis_tvalid is a flop in every
// slice), a beat offered and not taken stays offered with unchanged signals, tvalid is low during and at the first edge
// after reset. A wire (N = 0) passes the source's tvalid through, so it keeps the rules only if the source does.
//   TLAST_EN 1 carries tlast, TKEEP_EN 1 carries tkeep (W/8 bits, W a multiple of 8), TUSER_W > 0 carries tuser; a sideband
//   that is off is not carried: its output is 0 and its input is ignored. All carried signals move as one packed word.
// Reset is aresetn, active low, synchronous (AXI), one clock aclk. No reset on data. tdata/tkeep/tlast/tuser are undefined
// while tvalid is low.
// N slices in series, of the kind chosen by MODE:
//   0 FWD   forward-only: one shared enable, N stages, ready combinational from m_axis_tready, no side storage
//   1 SKID  skid buffer: tready a flop, full throughput, two beats of storage per slice
//   2 FULL  full register slice: two entries, valid and ready both flops, full throughput (same cycles as SKID)
//   3 HALF  one entry, tready a flop: one beat per two clocks, the cheapest registered-ready slice
//   4 COMB  one entry, tready = !tvalid || m_tready: full throughput, ready combinational from m_axis_tready
// N = 0 is a wire (s_axis_tready = m_axis_tready, no register, no latency).
// Latency: a beat accepted into an empty chain at edge t is visible at m_axis_* after edge t plus N-1 more edges: N clocks.
// Ready response: clocks from m_axis_tready rising (chain full) to s_axis_tready rising: 0 for COMB and FWD (and N = 0),
// N for SKID, FULL and HALF (measured, README).
// Compare with AMD's AXI Register Slice: ip_lib/pipe_reg/DATASHEET.md section "Against the vendor".

module pipe_reg #(
    parameter int W        = 32,
    parameter int N        = 1,
    parameter int MODE     = 1,
    parameter int TLAST_EN = 0,
    parameter int TKEEP_EN = 0,
    parameter int TUSER_W  = 0
) (
    input  logic                         aclk,
    input  logic                         aresetn,
    input  logic                         s_axis_tvalid,
    output logic                         s_axis_tready,
    input  logic [W-1:0]                 s_axis_tdata,
    input  logic                         s_axis_tlast,
    input  logic [(W/8 > 0 ? W/8 : 1)-1:0] s_axis_tkeep,
    input  logic [(TUSER_W > 0 ? TUSER_W : 1)-1:0] s_axis_tuser,
    output logic                         m_axis_tvalid,
    input  logic                         m_axis_tready,
    output logic [W-1:0]                 m_axis_tdata,
    output logic                         m_axis_tlast,
    output logic [(W/8 > 0 ? W/8 : 1)-1:0] m_axis_tkeep,
    output logic [(TUSER_W > 0 ? TUSER_W : 1)-1:0] m_axis_tuser
`ifdef FORMAL
    , output logic [W-1:0] f_in_o, f_out_o
`endif
);
    localparam int KW  = (W/8 > 0) ? W/8 : 1;
    localparam int UW  = (TUSER_W > 0) ? TUSER_W : 1;
    localparam int PWL = (TLAST_EN != 0) ? 1 : 0;
    localparam int PWK = (TKEEP_EN != 0) ? KW : 0;
    localparam int PWU = (TUSER_W > 0) ? TUSER_W : 0;
    localparam int PW  = W + PWL + PWK + PWU;          // the packed word: {tuser, tkeep, tlast, tdata}
    generate
        if (TLAST_EN < 0 || TLAST_EN > 1) begin : g_bad_tl
            initial $error("pipe_reg: TLAST_EN must be 0 or 1 (got %0d)", TLAST_EN);
        end
        if (TKEEP_EN < 0 || TKEEP_EN > 1 || (TKEEP_EN == 1 && (W % 8) != 0)) begin : g_bad_tk
            initial $error("pipe_reg: TKEEP_EN must be 0 or 1, and W a multiple of 8 when it is 1 (got %0d, W %0d)", TKEEP_EN, W);
        end
        if (TUSER_W < 0 || TUSER_W > 64) begin : g_bad_tu
            initial $error("pipe_reg: TUSER_W must be in 0..64 (got %0d)", TUSER_W);
        end
    endgenerate
    logic [PW-1:0] pin, pout;
    logic          rst;
    assign rst = !aresetn;
    // pack: {tuser, tkeep, tlast, tdata}; the pieces that are off are not part of the word
    wire [PW-1:0] pin_w;
    wire [W-1:0]  pout_d = pout[0 +: W];
    assign pin_w[0 +: W] = s_axis_tdata;
    assign m_axis_tdata  = pout_d;
    generate
        if (PWL != 0) begin : g_tl
            assign pin_w[W] = s_axis_tlast;
            assign m_axis_tlast = pout[W];
        end else begin : g_ntl
            assign m_axis_tlast = 1'b0;
        end
        if (PWK != 0) begin : g_tk
            assign pin_w[W+PWL +: (PWK > 0 ? PWK : 1)] = s_axis_tkeep[(PWK > 0 ? PWK : 1)-1:0];
            assign m_axis_tkeep = pout[W+PWL +: (PWK > 0 ? PWK : 1)];
        end else begin : g_ntk
            assign m_axis_tkeep = '0;
        end
        if (PWU != 0) begin : g_tu
            assign pin_w[W+PWL+PWK +: (PWU > 0 ? PWU : 1)] = s_axis_tuser[(PWU > 0 ? PWU : 1)-1:0];
            assign m_axis_tuser = pout[W+PWL+PWK +: (PWU > 0 ? PWU : 1)];
        end else begin : g_ntu
            assign m_axis_tuser = '0;
        end
    endgenerate
    assign pin = pin_w;
    pipe_reg_core #(.W(PW), .N(N), .MODE(MODE)) core (.clk(aclk), .rst, .s_valid(s_axis_tvalid), .s_ready(s_axis_tready),
        .s_data(pin), .m_valid(m_axis_tvalid), .m_ready(m_axis_tready), .m_data(pout)
`ifdef FORMAL
        , .f_in_o, .f_out_o
`endif
        );
endmodule

module pipe_reg_core #(
    parameter int W    = 32,
    parameter int N    = 1,
    parameter int MODE = 1
) (
    input  logic         clk,
    input  logic         rst,
    input  logic         s_valid,
    output logic         s_ready,
    input  logic [W-1:0] s_data,
    output logic         m_valid,
    input  logic         m_ready,
    output logic [W-1:0] m_data
`ifdef FORMAL
    , output logic [W-1:0] f_in_o, f_out_o
`endif
);
    generate
        if (W < 1 || W > 1024) begin : g_bad_w
            initial $error("pipe_reg_core: W must be in 1..1024 (got %0d)", W);
        end
        if (N < 0 || N > 16) begin : g_bad_n
            initial $error("pipe_reg_core: N must be in 0..16 (got %0d)", N);
        end
        if (MODE < 0 || MODE > 4) begin : g_bad_mode
            initial $error("pipe_reg_core: MODE must be in 0..4 (got %0d)", MODE);
        end
    endgenerate

    generate
        if (N == 0) begin : g_wire
            assign m_valid = s_valid;
            assign m_data  = s_data;
            assign s_ready = m_ready;
`ifdef FORMAL
            logic [W-1:0] f_n;
            always_ff @(posedge clk) if (rst) f_n <= '0; else if (s_valid && m_ready) f_n <= f_n + W'(1);
            assign f_in_o = f_n;
            assign f_out_o = f_n;
`endif
        end else if (MODE == 0) begin : g_fwd
            pipe_fwd #(.W(W), .NS(N)) u (.clk, .rst, .s_valid, .s_ready, .s_data, .m_valid, .m_ready, .m_data
`ifdef FORMAL
                                         , .f_in_o, .f_out_o
`endif
                                         );
        end else begin : g_chain
            // link[i] is the interface between slice i-1 and slice i; link[0] is the input, link[N] the output
            logic [N:0]   lv, lr;
            logic [(N+1)*W-1:0] ld;
`ifdef FORMAL
            logic [N*W-1:0] fi, fo;
            assign f_in_o  = fi[0 +: W];
            assign f_out_o = fo[(N-1)*W +: W];
            // the beats a slice delivers are the beats the next slice accepts (one handshake, counted twice)
            logic f_init = 1'b1;
            always_ff @(posedge clk) f_init <= rst;
            genvar q;
            for (q = 0; q + 1 < N; q++) begin : g_link
                always_ff @(posedge clk) if (!f_init && !rst) assert (fo[q*W +: W] == fi[(q+1)*W +: W]);
            end
`endif
            assign lv[0] = s_valid;
            assign ld[0 +: W] = s_data;
            assign s_ready = lr[0];
            assign m_valid = lv[N];
            assign m_data  = ld[N*W +: W];
            assign lr[N]   = m_ready;
            genvar i;
            for (i = 0; i < N; i++) begin : g_slice
                if (MODE == 1) begin : g_skid
                    pipe_slice_skid #(.W(W)) u (.clk, .rst, .s_valid(lv[i]), .s_ready(lr[i]), .s_data(ld[i*W +: W]),
                                                .m_valid(lv[i+1]), .m_ready(lr[i+1]), .m_data(ld[(i+1)*W +: W])
`ifdef FORMAL
                                                , .f_in_o(fi[i*W +: W]), .f_out_o(fo[i*W +: W])
`endif
                                                );
                end else if (MODE == 2) begin : g_full
                    pipe_slice_full #(.W(W)) u (.clk, .rst, .s_valid(lv[i]), .s_ready(lr[i]), .s_data(ld[i*W +: W]),
                                                .m_valid(lv[i+1]), .m_ready(lr[i+1]), .m_data(ld[(i+1)*W +: W])
`ifdef FORMAL
                                                , .f_in_o(fi[i*W +: W]), .f_out_o(fo[i*W +: W])
`endif
                                                );
                end else if (MODE == 3) begin : g_half
                    pipe_slice_half #(.W(W)) u (.clk, .rst, .s_valid(lv[i]), .s_ready(lr[i]), .s_data(ld[i*W +: W]),
                                                .m_valid(lv[i+1]), .m_ready(lr[i+1]), .m_data(ld[(i+1)*W +: W])
`ifdef FORMAL
                                                , .f_in_o(fi[i*W +: W]), .f_out_o(fo[i*W +: W])
`endif
                                                );
                end else begin : g_comb
                    pipe_slice_comb #(.W(W)) u (.clk, .rst, .s_valid(lv[i]), .s_ready(lr[i]), .s_data(ld[i*W +: W]),
                                                .m_valid(lv[i+1]), .m_ready(lr[i+1]), .m_data(ld[(i+1)*W +: W])
`ifdef FORMAL
                                                , .f_in_o(fi[i*W +: W]), .f_out_o(fo[i*W +: W])
`endif
                                                );
                end
            end
        end
    endgenerate
endmodule
