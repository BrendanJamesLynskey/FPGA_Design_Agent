// assertions.sv of fft_bfp (arith brief 161): the simulation checkers its chk_top.sv uses, copied from arith/fft_common by arith/tools/gen_harness_fft.py (do not edit).
// frame_checker: frame-structure checker for the plain-port frame blocks of the FFT suite (arith brief 161), for simulation: immediate assertions on every rising clock edge; each violation is counted
// in `errs` and reported with $error. A block of this kind presents frames of NBEAT consecutive output beats, the first with `sof`, optionally with an exponent word held over the frame.
//
// Rules (a beat is a clock with valid high and, for a block with an output ready, ready high; without one tie ready high):
//   P1  sof is high only together with valid;
//   P2  a frame is NBEAT consecutive beats: after the first (sof) the valid stays high until the NBEAT-th beat has been transferred, and no sof comes inside a frame;
//   P3  between frames valid may be low; a beat that is not a first beat outside a frame (valid without sof while no frame is open) is an error;
//   P4  while valid is high and ready low (a stalled sink) valid, sof and exp must hold in the next clock;
//   P5  HAS_EXP: exp does not change from one beat of a frame to the next;
//   P6  no unknown (X or Z) on valid or sof outside reset, and none on exp while valid.
module frame_checker #(
    parameter int NBEAT   = 64,
    parameter int HAS_EXP = 0,
    parameter int EW      = 1,
    parameter string NAME = "frame"
) (
    input  logic          clk,
    input  logic          rst,
    input  logic          valid,
    input  logic          sof,
    input  logic          ready,
    input  logic [EW-1:0] exp,
    output int            errs
);
    logic          inframe, p_valid, p_ready, p_sof, inited;
    logic [EW-1:0] p_exp, e0;
    int            beat;
    initial begin
        errs = 0; inframe = 0; p_valid = 0; p_ready = 0; p_sof = 0; inited = 0; p_exp = '0; e0 = '0; beat = 0;
    end
    task automatic fail(input string rule);
        errs = errs + 1;
        $error("%s: frame rule %s violated at %0t", NAME, rule, $time);
    endtask
    always @(posedge clk) begin
        if (rst !== 1'b0) begin
            inframe <= 1'b0; p_valid <= 1'b0; inited <= 1'b0; beat <= 0;
        end else begin
            if ((^{valid, sof}) === 1'bx) fail("P6 (valid or sof unknown)");
            else begin
                if (valid && HAS_EXP != 0 && ((^exp) === 1'bx)) fail("P6 (exp unknown while valid)");
                if (sof && !valid) fail("P1 (sof without valid)");
                if (inited && p_valid && !p_ready && (!valid || sof !== p_sof || (HAS_EXP != 0 && exp !== p_exp))) fail("P4 (valid, sof or exp changed while the sink was not ready)");
                if (valid && sof && inframe) fail("P2 (sof inside a frame)");
                if (valid && !sof && !inframe) fail("P3 (a beat outside a frame without sof)");
                if (inframe && !valid) fail("P2 (valid dropped inside a frame)");
                if (valid && !sof && inframe && HAS_EXP != 0 && exp !== e0) fail("P5 (exp changed inside a frame)");
                if (valid && ready) begin
                    if (sof) begin e0 <= exp; beat <= 1; inframe <= (NBEAT > 1); end
                    else begin
                        beat <= beat + 1;
                        if (beat + 1 == NBEAT) inframe <= 1'b0;
                    end
                end
                p_valid <= valid; p_ready <= ready; p_sof <= sof; p_exp <= exp; inited <= 1'b1;
            end
        end
    end
endmodule
