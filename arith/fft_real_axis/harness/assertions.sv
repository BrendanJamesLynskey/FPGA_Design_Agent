// assertions.sv of fft_real_axis (arith brief 161): the simulation checkers its chk_top.sv uses, copied from arith/fft_common by arith/tools/gen_harness_fft.py (do not edit).
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
