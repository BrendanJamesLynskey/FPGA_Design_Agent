// assertions.sv of fft_fastconv (arith brief 161): the simulation checkers its chk_top.sv uses, copied from arith/fft_common by arith/tools/gen_harness_fft.py (do not edit).
// axis_checker: AXI4-Stream protocol checker for simulation (arith brief 148). Immediate assertions evaluated on every rising clock edge; each violation is counted in `errs` and
// reported with $error. Not synthesised (the wrappers instantiate it between `ifndef SYNTHESIS lines).
//
// Rules checked (AMBA AXI4-Stream, ARM IHI 0051, the handshake section, in our own words):
//   H1  once tvalid is high and tready is low, tvalid must still be high in the next clock (a source may not withdraw a beat);
//   H2  while tvalid is high and tready low, tdata and tlast must not change;
//   H3  no unknown (X or Z) on tvalid, tready, or, when tvalid is high, on tdata and tlast, outside reset;
//   F1  with NBEAT > 0, tlast is high on exactly every NBEAT-th beat, counted from the first beat after reset;
//   S1  with NO_STALL = 1 (a pure streaming interface): tready must be high in every clock in which tvalid is high (the sink promises not to stall);
//   C1  with CONTIG = 1: once a frame has started, tvalid must stay high until the beat with tlast has been transferred (a source that must not pause inside a frame).
// "valid must not depend on ready" is a rule about the design, not about a waveform: it is shown by construction in the wrappers (tvalid comes from registers, no path from tready) and
// by H1 under random tready.
module axis_checker #(
    parameter int DW      = 32,
    parameter int NBEAT   = 0,
    parameter int NO_STALL = 0,
    parameter int CONTIG  = 0,
    parameter string NAME = "axis"
) (
    input  logic          clk,
    input  logic          aresetn,
    input  logic          tvalid,
    input  logic          tready,
    input  logic [DW-1:0] tdata,
    input  logic          tlast,
    output int            errs
);
    logic          pv, pr, pl, inited, inframe;
    logic [DW-1:0] pd;
    int            beat;
    initial begin
        errs = 0; pv = 0; pr = 0; pl = 0; pd = '0; inited = 0; inframe = 0; beat = 0;
    end
    task automatic fail(input string rule);
        errs = errs + 1;
        $error("%s: AXI4-Stream rule %s violated at %0t", NAME, rule, $time);
    endtask
    always @(posedge clk) begin
        if (aresetn !== 1'b1) begin
            inited <= 1'b0; pv <= 1'b0; pr <= 1'b0; inframe <= 1'b0; beat <= 0;
        end else begin
            if ((^{tvalid, tready}) === 1'bx) fail("H3 (tvalid or tready unknown)");
            else begin
                if (tvalid && ((^{tdata, tlast}) === 1'bx)) fail("H3 (tdata or tlast unknown while tvalid)");
                if (inited && pv && !pr) begin
                    if (!tvalid) fail("H1 (tvalid withdrawn before tready)");
                    else if (tdata !== pd || tlast !== pl) fail("H2 (tdata or tlast changed while stalled)");
                end
                if (NO_STALL != 0 && tvalid && !tready) fail("S1 (tready low while tvalid for a no-stall interface)");
                if (CONTIG != 0 && inframe && !tvalid) fail("C1 (tvalid low inside a frame)");
                if (tvalid && tready) begin
                    if (NBEAT > 0 && (tlast !== (beat == NBEAT - 1))) fail("F1 (tlast not on the last beat of the frame)");
                    beat <= (tlast === 1'b1 || (NBEAT > 0 && beat == NBEAT - 1)) ? 0 : beat + 1;
                    inframe <= !(tlast === 1'b1);
                end
                pv <= tvalid; pr <= tready; pd <= tdata; pl <= tlast; inited <= 1'b1;
            end
        end
    end
endmodule

// axil_checker: AXI4-Lite protocol checker for simulation (arith brief 161). Immediate assertions on every rising clock edge; each violation is counted in `errs` and reported with $error. Not synthesised
// (the blocks that use it instantiate it between `ifndef SYNTHESIS lines). Watches a slave interface from outside.
//
// Rules checked (AMBA AXI4-Lite, ARM IHI 0022, the handshake and response sections, in our own words):
//   A1  once a request valid (awvalid, wvalid, arvalid) is high and its ready is low, valid must still be high in the next clock and the address, data and strobes must not change;
//   A2  once a response valid (bvalid, rvalid) is high and bready / rready is low, valid must still be high in the next clock and bresp / rdata / rresp must not change;
//   A3  no unknown (X or Z) on any valid or ready outside reset, nor on bresp, rresp, rdata, while the corresponding valid is high;
//   A4  the response codes are OKAY (00) or SLVERR (10) only;
//   A5  a write response appears only after both an address and a data beat have been accepted since the previous response, and there is exactly one response per accepted pair (counted);
//   A6  a read response appears only after a read address has been accepted, one response per address (counted);
//   A7  during reset (aresetn low) bvalid and rvalid are low in the next clock.
// verilator lint_off BLKSEQ
module axil_checker #(
    parameter string NAME = "axil"
) (
    input  logic        clk,
    input  logic        aresetn,
    input  logic        awvalid,
    input  logic        awready,
    input  logic [5:0]  awaddr,
    input  logic        wvalid,
    input  logic        wready,
    input  logic [31:0] wdata,
    input  logic [3:0]  wstrb,
    input  logic        bvalid,
    input  logic        bready,
    input  logic [1:0]  bresp,
    input  logic        arvalid,
    input  logic        arready,
    input  logic [5:0]  araddr,
    input  logic        rvalid,
    input  logic        rready,
    input  logic [31:0] rdata,
    input  logic [1:0]  rresp,
    output int          errs
);
    logic        inited, p_aw, p_awr, p_w, p_wr, p_ar, p_arr, p_b, p_br, p_r, p_rr, p_rst;
    logic [5:0]  p_awa, p_ara;
    logic [31:0] p_wd, p_rd;
    logic [3:0]  p_ws;
    logic [1:0]  p_bresp, p_rresp;
    int          aw_n, w_n, b_n, ar_n, r_n;
    initial begin
        errs = 0; inited = 0; p_rst = 0; aw_n = 0; w_n = 0; b_n = 0; ar_n = 0; r_n = 0;
        p_aw = 0; p_awr = 0; p_w = 0; p_wr = 0; p_ar = 0; p_arr = 0; p_b = 0; p_br = 0; p_r = 0; p_rr = 0;
        p_awa = 0; p_ara = 0; p_wd = 0; p_rd = 0; p_ws = 0; p_bresp = 0; p_rresp = 0;
    end
    task automatic fail(input string rule);
        errs = errs + 1;
        $error("%s: AXI4-Lite rule %s violated at %0t", NAME, rule, $time);
    endtask
    always @(posedge clk) begin
        if (aresetn !== 1'b1) begin
            if (p_rst && (bvalid === 1'b1 || rvalid === 1'b1)) fail("A7 (a response valid during reset)");
            inited <= 1'b0; p_rst <= 1'b1; aw_n = 0; w_n = 0; b_n = 0; ar_n = 0; r_n = 0;
            p_aw <= 0; p_w <= 0; p_ar <= 0; p_b <= 0; p_r <= 0;
        end else begin
            p_rst <= 1'b0;
            if ((^{awvalid, awready, wvalid, wready, bvalid, bready, arvalid, arready, rvalid, rready}) === 1'bx) fail("A3 (a valid or ready is unknown)");
            else begin
                if (inited) begin
                    if (p_aw && !p_awr && (!awvalid || awaddr !== p_awa)) fail("A1 (awvalid withdrawn or awaddr changed before awready)");
                    if (p_w && !p_wr && (!wvalid || wdata !== p_wd || wstrb !== p_ws)) fail("A1 (wvalid withdrawn or wdata/wstrb changed before wready)");
                    if (p_ar && !p_arr && (!arvalid || araddr !== p_ara)) fail("A1 (arvalid withdrawn or araddr changed before arready)");
                    if (p_b && !p_br && (!bvalid || bresp !== p_bresp)) fail("A2 (bvalid withdrawn or bresp changed before bready)");
                    if (p_r && !p_rr && (!rvalid || rdata !== p_rd || rresp !== p_rresp)) fail("A2 (rvalid withdrawn or rdata/rresp changed before rready)");
                end
                if (bvalid && ((^bresp) === 1'bx)) fail("A3 (bresp unknown)");
                if (rvalid && ((^{rdata, rresp}) === 1'bx)) fail("A3 (rdata or rresp unknown)");
                if (bvalid && bresp !== 2'b00 && bresp !== 2'b10) fail("A4 (bresp is not OKAY or SLVERR)");
                if (rvalid && rresp !== 2'b00 && rresp !== 2'b10) fail("A4 (rresp is not OKAY or SLVERR)");
                if (awvalid && awready) aw_n = aw_n + 1;
                if (wvalid && wready) w_n = w_n + 1;
                if (arvalid && arready) ar_n = ar_n + 1;
                if (bvalid && !p_b && !(aw_n > b_n && w_n > b_n)) fail("A5 (a write response without an accepted address and data)");
                if (bvalid && bready) b_n = b_n + 1;
                if (rvalid && !p_r && !(ar_n > r_n)) fail("A6 (a read response without an accepted address)");
                if (rvalid && rready) r_n = r_n + 1;
                p_aw <= awvalid; p_awr <= awready; p_awa <= awaddr;
                p_w <= wvalid; p_wr <= wready; p_wd <= wdata; p_ws <= wstrb;
                p_ar <= arvalid; p_arr <= arready; p_ara <= araddr;
                p_b <= bvalid; p_br <= bready; p_bresp <= bresp;
                p_r <= rvalid; p_rr <= rready; p_rd <= rdata; p_rresp <= rresp;
                inited <= 1'b1;
            end
        end
    end
endmodule
// verilator lint_on BLKSEQ
