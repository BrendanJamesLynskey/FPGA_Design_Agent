// fp_norm: leading-zero count and left normalisation of an NW-bit vector (arith brief 139e; used by the floating-point variants and by fp_pack's callers).
// n = v << lz so that n[NW-1] is the leading one (v nonzero); v = 0 gives lz = 0 and n = 0.
//
// Intended primitive use (stated before any Vivado run; not yet measured): LUTs only: a priority encoder (about NW LUTs) and an NW-wide left barrel shifter
// (about NW * log2(NW) / 2 LUT6 on a 7-series part, 4:1 mux stages in LUT6). No DSP, block RAM or flip-flop; purely combinational.
module fp_norm #(
    parameter int NW = 8,
    parameter int LW = $clog2(NW) + 1
) (
    input  logic [NW-1:0] v,
    output logic [NW-1:0] n,
    output logic [LW-1:0] lz
);
    always_comb begin
        logic found;
        found = 1'b0;
        lz    = '0;
        for (int i = NW - 1; i >= 0; i--) begin
            if (v[i] && !found) begin
                found = 1'b1;
                lz    = LW'(NW - 1 - i);
            end
        end
        n = v << lz;
    end
endmodule

