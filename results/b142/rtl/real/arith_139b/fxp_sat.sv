// fxp_sat: fit a signed W_R-bit value to W_OUT bits by wrapping (SAT = 0) or saturating (SAT = 1), combinational (brief 139b).
// Primitive use (intended, not yet measured): the "fits" test is an AND/OR reduction of the W_R - W_OUT + 1 bits above the output's sign
// bit (LUT6 tree, one level up to 6 bits) and the saturated value is a 2:1 mux per output bit (LUT); no carry chain.
module fxp_sat #(
    parameter int W_R   = 8,              // width of the rounded value
    parameter int W_OUT = 6,              // 2 or more
    parameter bit SAT   = 1'b1
) (
    input  logic [W_R-1:0]   r,
    output logic [W_OUT-1:0] y
);
    if (W_OUT >= W_R) begin : g_ext
        assign y = W_OUT'($signed(r));
    end else if (!SAT) begin : g_wrap
        assign y = r[W_OUT-1:0];
        logic unused;
        assign unused = &{1'b0, r[W_R-1:W_OUT]};
    end else begin : g_sat
        logic fits;
        assign fits = (&r[W_R-1:W_OUT-1]) | ~(|r[W_R-1:W_OUT-1]);
        assign y    = fits ? r[W_OUT-1:0] : {r[W_R-1], {(W_OUT-1){~r[W_R-1]}}};
    end
endmodule
