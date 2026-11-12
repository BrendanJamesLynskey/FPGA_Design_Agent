// fir: a FIR filter with implementation variants behind one contract.
//
//   y[n] = sum_{k=0}^{TAPS-1} h[k] * x[n-k]      full precision, ACC_W = DATA_W + COEF_W + clog2(TAPS) bits, no rounding
//
// Every variant has the same ports, parameters and function (bit-exact against ip_lib/fir/model.py); they differ in
// resources, latency, throughput and Fmax. IMPL selects one:
//   "dsp_bram"  MACS = ceil(TAPS/FOLD) DSP multiply-accumulates, coefficients and delay line in block RAM; one output
//               every FOLD + 3 clocks
//   "dist_ram"  the same folded core with the memories in LUT RAM (small coefficient sets)
//   "serial"    one DSP multiply-accumulate time-shared over all taps (FOLD = TAPS); memory style left to synthesis
//   "lut_mult"  fully parallel direct form, multipliers in LUTs and carry chains; one output every clock
//
// Interfaces: coefficients and samples in, results out, each valid/ready (AXI4-Stream style, one beat per value).
//   - Coefficient load: h[0] first, then h[1] ..; c_last on the final beat (or the count reaching TAPS) ends the load.
//     A beat is taken only when no sample is in the multiply stages; while c_valid is high no sample is accepted, so
//     every sample accepted after a beat uses the coefficients written so far.
//   - After rst the history and the coefficients are zero; busy is high while a variant clears its memories (FOLD
//     clocks for the folded variants, one clock for lut_mult). Nothing is accepted while busy.
//   - LATENCY (clocks from the s_valid && s_ready clock to the first clock m_valid is high for that sample, with
//     m_ready high) and II (clocks between accepted samples when the input never waits) are localparams of this
//     module and part of the contract: a caller reads them (or ip_lib/fir/model.py fir_timing) and never assumes them.
module fir #(
    parameter        IMPL   = "dsp_bram",   // a string (untyped: Icarus 12 mis-sizes typed string parameters)
    parameter int    TAPS   = 16,
    parameter int    DATA_W = 16,
    parameter int    COEF_W = 16,
    parameter int    FOLD   = 4,           // taps per MAC engine (dsp_bram, dist_ram); serial uses TAPS, lut_mult ignores it
    localparam int   ACC_W  = DATA_W + COEF_W + $clog2(TAPS)
) (
    input  logic                     clk,
    input  logic                     rst,
    output logic                     busy,
    input  logic                     c_valid,
    output logic                     c_ready,
    input  logic signed [COEF_W-1:0] c_data,
    input  logic                     c_last,
    input  logic                     s_valid,
    output logic                     s_ready,
    input  logic signed [DATA_W-1:0] s_data,
    output logic                     m_valid,
    input  logic                     m_ready,
    output logic signed [ACC_W-1:0]  m_data
);
    localparam bit IS_PAR  = (IMPL == "lut_mult");
    localparam int F_EFF   = (IMPL == "serial") ? TAPS : FOLD;
    localparam int MACS    = IS_PAR ? TAPS : (TAPS + F_EFF - 1) / F_EFF;
    localparam int TREE    = (MACS > 1) ? $clog2(MACS) : 0;
    localparam int LATENCY = IS_PAR ? 2 + $clog2(TAPS) : F_EFF + 8 + TREE;
    localparam int II      = IS_PAR ? 1 : F_EFF + 3;

    initial begin
        if (!(IMPL == "dsp_bram" || IMPL == "dist_ram" || IMPL == "serial" || IMPL == "lut_mult"))
            $error("fir: IMPL %s is not dsp_bram, dist_ram, serial or lut_mult", IMPL);
        if (TAPS < 2 || TAPS > 256) $error("fir: TAPS %0d outside 2..256", TAPS);
        if (DATA_W < 4 || DATA_W > 24) $error("fir: DATA_W %0d outside 4..24", DATA_W);
        if (COEF_W < 4 || COEF_W > 18) $error("fir: COEF_W %0d outside 4..18", COEF_W);
        if (!(IMPL == "serial" || IS_PAR) && (FOLD < 2 || FOLD > 256 || FOLD > TAPS))   // FOLD is used by dsp_bram, dist_ram only
            $error("fir: FOLD %0d outside 2..min(TAPS,256)", FOLD);
        if (ACC_W > 48) $error("fir: DATA_W + COEF_W + clog2(TAPS) = %0d exceeds 48", ACC_W);
        if (IS_PAR && TAPS > 64) $error("fir: lut_mult supports TAPS up to 64, not %0d", TAPS);
    end

    generate
        if (IS_PAR) begin : g_lut_mult
            fir_parallel #(.TAPS(TAPS), .DATA_W(DATA_W), .COEF_W(COEF_W), .ACC_W(ACC_W)) u_core (.*);
        end else begin : g_fold
            fir_fold #(.TAPS(TAPS), .DATA_W(DATA_W), .COEF_W(COEF_W), .FOLD(F_EFF), .ACC_W(ACC_W),
                       .MEM_STYLE(IMPL == "dsp_bram" ? 1 : IMPL == "dist_ram" ? 2 : 0)) u_core (.*);
        end
    endgenerate
endmodule
