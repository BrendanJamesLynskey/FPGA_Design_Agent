// divider_hr_cs_step: one radix-4 SRT step with a carry-save partial remainder (brief 139c), combinational.
//   (us, uc) are the two words of the remainder (W + 3 bits each, modulo 2**(W+3)); the step forms 4*(us+uc) - q*b with one 3:2 compressor
//   (a LUT3 per bit) after the digit is chosen from the top bits of the two words and the divisor's top bits. first = 1 is the first step of a
//   division: the dividend a is in us[W-1:0] and is used unshifted (its estimate is the exact value a >> (W-4)), as the integer digit 0..2.
module divider_hr_cs_step #(
    parameter int W = 16
) (
    input  logic         first,
    input  logic [W+2:0] us,
    input  logic [W+2:0] uc,
    input  logic [W-1:0] b,
    output logic [W+2:0] us_n,
    output logic [W+2:0] uc_n,
    output logic [2:0]   q
);
    localparam int WW = W + 3;
    logic [WW-1:0] xs, xc, z, m1, m2;
    logic [6:0]    est;
    logic          cin;
    logic          unused;

    assign xs  = first ? {3'b000, us[W-1:0]} : {us[WW-3:0], 2'b00};
    assign xc  = first ? '0 : {uc[WW-3:0], 2'b00};
    assign est = first ? {3'b000, us[W-1:W-4]} : (us[W:W-6] + uc[W:W-6]);   // the 7-bit carry-propagate sum of the two truncated words
    assign unused = &{1'b0, us[WW-1:WW-2], uc[WW-1:WW-2]};                  // shifted out

    divider_hr_digit u_digit (.i(b[W-2:W-4]), .k($signed(est)), .q(q));

    assign m1 = {3'b000, b};
    assign m2 = {2'b00, b, 1'b0};
    always_comb begin
        case (q)
            3'b001:  begin z = ~m1; cin = 1'b1; end    // +1: subtract b
            3'b010:  begin z = ~m2; cin = 1'b1; end    // +2: subtract 2b
            3'b111:  begin z = m1;  cin = 1'b0; end    // -1: add b
            3'b110:  begin z = m2;  cin = 1'b0; end    // -2: add 2b
            default: begin z = '0;  cin = 1'b0; end
        endcase
    end
    assign us_n = xs ^ xc ^ z;
    assign uc_n = {(xs[WW-2:0] & xc[WW-2:0]) | (xs[WW-2:0] & z[WW-2:0]) | (xc[WW-2:0] & z[WW-2:0]), cin};
endmodule
