// P15-3 reference RTL: a copy of solutions/p15l06_rmsnorm/rmsnorm_unit.sv (course exercise p15l06_rmsnorm).
// Part 15 lesson 6 exercise: an RMS-norm unit for N = 16 values, an inverse square root from a table and one Newton step, within a stated error budget.
//
// Input: N signed 16-bit values in Q8.8 (x_i / 256 is the real value), packed x[i*16 +: 16]. Output: N signed 16-bit values in Q8.8, y_i = x_i / sqrt(mean(x^2) + eps) with
// eps = 1 LSB of the mean in Q16.16 (the gain gamma is left out: it folds into the next layer's weights). With in_valid high, one clock later (out_valid high; rst_n synchronous,
// active low, clears out_valid only):
//   1. ss = 16 + sum x_i^2                       (unsigned, 35 bits; the 16 is the epsilon: sum x^2 / 16 is the mean in Q16.16, so eps = 16 / 16 = 1 LSB)
//   2. p = index of the highest set bit of ss;  e = p >> 1;  mq = ss * 4^(-e) in Q2.16, i.e. ss << (16 - 2e) if 2e <= 16, else ss >> (2e - 16);   mq is in [65536, 262144)
//   3. y0 = RSQRT_LUT[(mq >> 11) - 32], RSQRT_LUT[k] = round(65536 / sqrt((k + 32.5) / 32)), k = 0..95        (a Q0.16 estimate of 1/sqrt(mq / 65536))
//   4. one Newton step:  t = (y0 * y0) >> 16;  mt = (mq * t) >> 16;  y1 = (y0 * (3 * 65536 - mt)) >> 17
//   5. y_i = clamp((x_i * y1 + 2^(5+e)) >>> (6 + e), -32768, 32767)       (round to nearest, arithmetic shift; y1 / 2^e is 1/sqrt(ss) in Q0.16, and 1024 / 65536 = 2^-6 supplies the 6)
// Golden model: tools/ai_models.rmsnorm_int (bit-exact). Error budget against the float result 1024 * x_i / sqrt(ss): every output within 1 LSB (1/256).
module rmsnorm_unit #(
    parameter int N = 16
) (
    input  logic            clk,
    input  logic            rst_n,
    input  logic            in_valid,
    input  logic [N*16-1:0] x,
    output logic            out_valid,
    output logic [N*16-1:0] y
);
    function automatic [15:0] rsqrt_lut(input [6:0] k);
        case (k)
            7'd0: rsqrt_lut = 16'd65030;
            7'd1: rsqrt_lut = 16'd64052;
            7'd2: rsqrt_lut = 16'd63117;
            7'd3: rsqrt_lut = 16'd62222;
            7'd4: rsqrt_lut = 16'd61363;
            7'd5: rsqrt_lut = 16'd60540;
            7'd6: rsqrt_lut = 16'd59748;
            7'd7: rsqrt_lut = 16'd58987;
            7'd8: rsqrt_lut = 16'd58254;
            7'd9: rsqrt_lut = 16'd57548;
            7'd10: rsqrt_lut = 16'd56867;
            7'd11: rsqrt_lut = 16'd56210;
            7'd12: rsqrt_lut = 16'd55574;
            7'd13: rsqrt_lut = 16'd54960;
            7'd14: rsqrt_lut = 16'd54366;
            7'd15: rsqrt_lut = 16'd53791;
            7'd16: rsqrt_lut = 16'd53233;
            7'd17: rsqrt_lut = 16'd52693;
            7'd18: rsqrt_lut = 16'd52169;
            7'd19: rsqrt_lut = 16'd51660;
            7'd20: rsqrt_lut = 16'd51165;
            7'd21: rsqrt_lut = 16'd50685;
            7'd22: rsqrt_lut = 16'd50218;
            7'd23: rsqrt_lut = 16'd49763;
            7'd24: rsqrt_lut = 16'd49321;
            7'd25: rsqrt_lut = 16'd48890;
            7'd26: rsqrt_lut = 16'd48470;
            7'd27: rsqrt_lut = 16'd48061;
            7'd28: rsqrt_lut = 16'd47663;
            7'd29: rsqrt_lut = 16'd47273;
            7'd30: rsqrt_lut = 16'd46894;
            7'd31: rsqrt_lut = 16'd46523;
            7'd32: rsqrt_lut = 16'd46161;
            7'd33: rsqrt_lut = 16'd45807;
            7'd34: rsqrt_lut = 16'd45462;
            7'd35: rsqrt_lut = 16'd45124;
            7'd36: rsqrt_lut = 16'd44793;
            7'd37: rsqrt_lut = 16'd44470;
            7'd38: rsqrt_lut = 16'd44153;
            7'd39: rsqrt_lut = 16'd43843;
            7'd40: rsqrt_lut = 16'd43540;
            7'd41: rsqrt_lut = 16'd43243;
            7'd42: rsqrt_lut = 16'd42951;
            7'd43: rsqrt_lut = 16'd42666;
            7'd44: rsqrt_lut = 16'd42386;
            7'd45: rsqrt_lut = 16'd42112;
            7'd46: rsqrt_lut = 16'd41843;
            7'd47: rsqrt_lut = 16'd41579;
            7'd48: rsqrt_lut = 16'd41320;
            7'd49: rsqrt_lut = 16'd41065;
            7'd50: rsqrt_lut = 16'd40816;
            7'd51: rsqrt_lut = 16'd40571;
            7'd52: rsqrt_lut = 16'd40330;
            7'd53: rsqrt_lut = 16'd40093;
            7'd54: rsqrt_lut = 16'd39861;
            7'd55: rsqrt_lut = 16'd39632;
            7'd56: rsqrt_lut = 16'd39408;
            7'd57: rsqrt_lut = 16'd39187;
            7'd58: rsqrt_lut = 16'd38970;
            7'd59: rsqrt_lut = 16'd38756;
            7'd60: rsqrt_lut = 16'd38546;
            7'd61: rsqrt_lut = 16'd38340;
            7'd62: rsqrt_lut = 16'd38136;
            7'd63: rsqrt_lut = 16'd37936;
            7'd64: rsqrt_lut = 16'd37739;
            7'd65: rsqrt_lut = 16'd37545;
            7'd66: rsqrt_lut = 16'd37354;
            7'd67: rsqrt_lut = 16'd37166;
            7'd68: rsqrt_lut = 16'd36980;
            7'd69: rsqrt_lut = 16'd36798;
            7'd70: rsqrt_lut = 16'd36618;
            7'd71: rsqrt_lut = 16'd36441;
            7'd72: rsqrt_lut = 16'd36266;
            7'd73: rsqrt_lut = 16'd36093;
            7'd74: rsqrt_lut = 16'd35924;
            7'd75: rsqrt_lut = 16'd35756;
            7'd76: rsqrt_lut = 16'd35591;
            7'd77: rsqrt_lut = 16'd35428;
            7'd78: rsqrt_lut = 16'd35267;
            7'd79: rsqrt_lut = 16'd35109;
            7'd80: rsqrt_lut = 16'd34953;
            7'd81: rsqrt_lut = 16'd34798;
            7'd82: rsqrt_lut = 16'd34646;
            7'd83: rsqrt_lut = 16'd34496;
            7'd84: rsqrt_lut = 16'd34347;
            7'd85: rsqrt_lut = 16'd34201;
            7'd86: rsqrt_lut = 16'd34056;
            7'd87: rsqrt_lut = 16'd33913;
            7'd88: rsqrt_lut = 16'd33772;
            7'd89: rsqrt_lut = 16'd33633;
            7'd90: rsqrt_lut = 16'd33496;
            7'd91: rsqrt_lut = 16'd33360;
            7'd92: rsqrt_lut = 16'd33225;
            7'd93: rsqrt_lut = 16'd33093;
            7'd94: rsqrt_lut = 16'd32962;
            7'd95: rsqrt_lut = 16'd32832;
            default: rsqrt_lut = 16'd0;
        endcase
    endfunction

    logic signed [63:0] ss;
    logic [5:0]         pb;
    logic [5:0]         e;
    logic [63:0]        mq;
    logic [15:0]        y0;
    logic [63:0]        t, mt, y1;
    logic signed [63:0] r, xi;
    logic [N*16-1:0]    yout;
    always_comb begin
        ss = 64'sd16;
        for (int i = 0; i < N; i++) ss = ss + $signed(x[i*16 +: 16]) * $signed(x[i*16 +: 16]);
        pb = 6'd0;
        for (int j = 0; j < 40; j++) if (ss[j]) pb = j;
        e = pb >> 1;
        mq = (e <= 6'd8) ? (ss << (6'd16 - (e << 1))) : (ss >> ((e << 1) - 6'd16));
        y0 = rsqrt_lut(mq[17:11] - 7'd32);
        t = (y0 * y0) >> 16;
        mt = (mq * t) >> 16;
        y1 = (y0 * (64'd196608 - mt)) >> 17;
        for (int i = 0; i < N; i++) begin
            xi = $signed(x[i*16 +: 16]);
            r = (xi * $signed(y1) + (64'sd1 <<< (5 + e))) >>> (6 + e);
            yout[i*16 +: 16] = (r > 64'sd32767) ? 16'sh7FFF : (r < -64'sd32768) ? 16'sh8000 : r[15:0];
        end
    end
    always_ff @(posedge clk) begin
        if (!rst_n) out_valid <= 1'b0;
        else out_valid <= in_valid;
        if (in_valid) y <= yout;
    end
endmodule
