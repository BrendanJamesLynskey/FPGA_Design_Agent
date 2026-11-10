// P15-2 reference RTL: a copy of solutions/p15l06_softmax/softmax_unit.sv (course exercise p15l06_softmax).
// Part 15 lesson 6 exercise: a softmax unit for N = 8 scores, within a stated error budget, using only integer arithmetic, a 64-entry exp table and a 128-entry reciprocal table.
//
// Input: N signed 16-bit scores in Q8.8 (x_i / 256 is the real score), packed x[i*16 +: 16]. Output: N unsigned 16-bit probabilities in Q0.15 (32768 = 1.0), packed p[i*16 +: 16].
// With in_valid high, one clock later (out_valid high; rst_n synchronous, active low, clears out_valid only), p holds:
//   1. m = max(x_i)                                         (the max subtraction: every exponent argument is then <= 0, so the exp never overflows)
//   2. e_i = exp2neg(m - x_i), a 17-bit Q0.16 value:  d = m - x_i (0 .. 65535, Q8.8);  d = 0 gives exactly 65536;
//        otherwise t = (d * 23637 + 8192) >> 14 (d * log2(e) in Q8.8), n = t >> 8, f = t & 255;  e = 0 if n >= 17, else EXP_LUT[f >> 2] >> n,
//        with EXP_LUT[k] = round(65536 * 2^(-(k + 0.5) / 64)), k = 0..63.
//   3. S = sum e_i (at least 65536);  p = index of the highest set bit of S (16 .. 19);  ms = S >> (p - 15) (16 bits, 32768 .. 65535);
//        L = RECIP_LUT[(ms - 32768) >> 8] with RECIP_LUT[k] = round(2^31 / (32768 + 256 k + 128)), k = 0..127  (so 1/S is about L / 2^(p+16)).
//   4. P_i = (e_i * L + 2^p) >> (p + 1)                      (the probability times 32768, rounded)
// Golden model: tools/ai_models.softmax_int (bit-exact). Error budget against the float softmax of the same scores: every probability within 1/128 (0.0078) absolute; the probabilities
// sum to 1 within 1/128. Two sources: the 64-step exp table (at most 0.54 % relative) and the 128-step reciprocal table (at most 0.39 % relative).
module softmax_unit #(
    parameter int N = 8
) (
    input  logic            clk,
    input  logic            rst_n,
    input  logic            in_valid,
    input  logic [N*16-1:0] x,
    output logic            out_valid,
    output logic [N*16-1:0] p
);
    function automatic [15:0] exp_lut(input [5:0] k);
        case (k)
            6'd0: exp_lut = 16'd65182;
            6'd1: exp_lut = 16'd64480;
            6'd2: exp_lut = 16'd63785;
            6'd3: exp_lut = 16'd63098;
            6'd4: exp_lut = 16'd62419;
            6'd5: exp_lut = 16'd61746;
            6'd6: exp_lut = 16'd61081;
            6'd7: exp_lut = 16'd60423;
            6'd8: exp_lut = 16'd59772;
            6'd9: exp_lut = 16'd59128;
            6'd10: exp_lut = 16'd58491;
            6'd11: exp_lut = 16'd57861;
            6'd12: exp_lut = 16'd57238;
            6'd13: exp_lut = 16'd56622;
            6'd14: exp_lut = 16'd56012;
            6'd15: exp_lut = 16'd55408;
            6'd16: exp_lut = 16'd54811;
            6'd17: exp_lut = 16'd54221;
            6'd18: exp_lut = 16'd53637;
            6'd19: exp_lut = 16'd53059;
            6'd20: exp_lut = 16'd52488;
            6'd21: exp_lut = 16'd51922;
            6'd22: exp_lut = 16'd51363;
            6'd23: exp_lut = 16'd50810;
            6'd24: exp_lut = 16'd50262;
            6'd25: exp_lut = 16'd49721;
            6'd26: exp_lut = 16'd49185;
            6'd27: exp_lut = 16'd48655;
            6'd28: exp_lut = 16'd48131;
            6'd29: exp_lut = 16'd47613;
            6'd30: exp_lut = 16'd47100;
            6'd31: exp_lut = 16'd46593;
            6'd32: exp_lut = 16'd46091;
            6'd33: exp_lut = 16'd45594;
            6'd34: exp_lut = 16'd45103;
            6'd35: exp_lut = 16'd44617;
            6'd36: exp_lut = 16'd44137;
            6'd37: exp_lut = 16'd43661;
            6'd38: exp_lut = 16'd43191;
            6'd39: exp_lut = 16'd42726;
            6'd40: exp_lut = 16'd42265;
            6'd41: exp_lut = 16'd41810;
            6'd42: exp_lut = 16'd41360;
            6'd43: exp_lut = 16'd40914;
            6'd44: exp_lut = 16'd40473;
            6'd45: exp_lut = 16'd40037;
            6'd46: exp_lut = 16'd39606;
            6'd47: exp_lut = 16'd39180;
            6'd48: exp_lut = 16'd38757;
            6'd49: exp_lut = 16'd38340;
            6'd50: exp_lut = 16'd37927;
            6'd51: exp_lut = 16'd37518;
            6'd52: exp_lut = 16'd37114;
            6'd53: exp_lut = 16'd36715;
            6'd54: exp_lut = 16'd36319;
            6'd55: exp_lut = 16'd35928;
            6'd56: exp_lut = 16'd35541;
            6'd57: exp_lut = 16'd35158;
            6'd58: exp_lut = 16'd34779;
            6'd59: exp_lut = 16'd34405;
            6'd60: exp_lut = 16'd34034;
            6'd61: exp_lut = 16'd33667;
            6'd62: exp_lut = 16'd33305;
            6'd63: exp_lut = 16'd32946;
            default: exp_lut = 16'd0;
        endcase
    endfunction

    // exp(-d/256) in Q0.16 for d >= 0 in Q8.8 (65536 = 1.0): t = d * log2(e) in Q8.8; n = whole octaves, f = fraction (top 6 bits index the table)
    function automatic [16:0] exp2neg(input [15:0] d);
        reg [31:0] t;
        begin
            if (d == 16'd0) exp2neg = 17'd65536;
            else begin
                t = (d * 32'd23637 + 32'd8192) >> 14;
                if (t[31:8] >= 24'd17) exp2neg = 17'd0;
                else exp2neg = {1'b0, exp_lut(t[7:2])} >> t[12:8];
            end
        end
    endfunction

    function automatic [15:0] recip_lut(input [6:0] k);
        case (k)
            7'd0: recip_lut = 16'd65281;
            7'd1: recip_lut = 16'd64777;
            7'd2: recip_lut = 16'd64281;
            7'd3: recip_lut = 16'd63792;
            7'd4: recip_lut = 16'd63310;
            7'd5: recip_lut = 16'd62836;
            7'd6: recip_lut = 16'd62369;
            7'd7: recip_lut = 16'd61909;
            7'd8: recip_lut = 16'd61455;
            7'd9: recip_lut = 16'd61008;
            7'd10: recip_lut = 16'd60568;
            7'd11: recip_lut = 16'd60133;
            7'd12: recip_lut = 16'd59705;
            7'd13: recip_lut = 16'd59283;
            7'd14: recip_lut = 16'd58867;
            7'd15: recip_lut = 16'd58457;
            7'd16: recip_lut = 16'd58053;
            7'd17: recip_lut = 16'd57654;
            7'd18: recip_lut = 16'd57260;
            7'd19: recip_lut = 16'd56872;
            7'd20: recip_lut = 16'd56489;
            7'd21: recip_lut = 16'd56111;
            7'd22: recip_lut = 16'd55738;
            7'd23: recip_lut = 16'd55370;
            7'd24: recip_lut = 16'd55007;
            7'd25: recip_lut = 16'd54649;
            7'd26: recip_lut = 16'd54295;
            7'd27: recip_lut = 16'd53946;
            7'd28: recip_lut = 16'd53601;
            7'd29: recip_lut = 16'd53261;
            7'd30: recip_lut = 16'd52925;
            7'd31: recip_lut = 16'd52593;
            7'd32: recip_lut = 16'd52265;
            7'd33: recip_lut = 16'd51942;
            7'd34: recip_lut = 16'd51622;
            7'd35: recip_lut = 16'd51306;
            7'd36: recip_lut = 16'd50995;
            7'd37: recip_lut = 16'd50686;
            7'd38: recip_lut = 16'd50382;
            7'd39: recip_lut = 16'd50081;
            7'd40: recip_lut = 16'd49784;
            7'd41: recip_lut = 16'd49490;
            7'd42: recip_lut = 16'd49200;
            7'd43: recip_lut = 16'd48913;
            7'd44: recip_lut = 16'd48630;
            7'd45: recip_lut = 16'd48349;
            7'd46: recip_lut = 16'd48072;
            7'd47: recip_lut = 16'd47798;
            7'd48: recip_lut = 16'd47528;
            7'd49: recip_lut = 16'd47260;
            7'd50: recip_lut = 16'd46995;
            7'd51: recip_lut = 16'd46733;
            7'd52: recip_lut = 16'd46474;
            7'd53: recip_lut = 16'd46218;
            7'd54: recip_lut = 16'd45965;
            7'd55: recip_lut = 16'd45714;
            7'd56: recip_lut = 16'd45467;
            7'd57: recip_lut = 16'd45222;
            7'd58: recip_lut = 16'd44979;
            7'd59: recip_lut = 16'd44739;
            7'd60: recip_lut = 16'd44502;
            7'd61: recip_lut = 16'd44267;
            7'd62: recip_lut = 16'd44035;
            7'd63: recip_lut = 16'd43805;
            7'd64: recip_lut = 16'd43577;
            7'd65: recip_lut = 16'd43352;
            7'd66: recip_lut = 16'd43129;
            7'd67: recip_lut = 16'd42908;
            7'd68: recip_lut = 16'd42690;
            7'd69: recip_lut = 16'd42474;
            7'd70: recip_lut = 16'd42260;
            7'd71: recip_lut = 16'd42048;
            7'd72: recip_lut = 16'd41838;
            7'd73: recip_lut = 16'd41631;
            7'd74: recip_lut = 16'd41425;
            7'd75: recip_lut = 16'd41222;
            7'd76: recip_lut = 16'd41020;
            7'd77: recip_lut = 16'd40820;
            7'd78: recip_lut = 16'd40623;
            7'd79: recip_lut = 16'd40427;
            7'd80: recip_lut = 16'd40233;
            7'd81: recip_lut = 16'd40041;
            7'd82: recip_lut = 16'd39851;
            7'd83: recip_lut = 16'd39662;
            7'd84: recip_lut = 16'd39476;
            7'd85: recip_lut = 16'd39291;
            7'd86: recip_lut = 16'd39108;
            7'd87: recip_lut = 16'd38926;
            7'd88: recip_lut = 16'd38746;
            7'd89: recip_lut = 16'd38568;
            7'd90: recip_lut = 16'd38392;
            7'd91: recip_lut = 16'd38217;
            7'd92: recip_lut = 16'd38044;
            7'd93: recip_lut = 16'd37872;
            7'd94: recip_lut = 16'd37702;
            7'd95: recip_lut = 16'd37533;
            7'd96: recip_lut = 16'd37366;
            7'd97: recip_lut = 16'd37200;
            7'd98: recip_lut = 16'd37036;
            7'd99: recip_lut = 16'd36873;
            7'd100: recip_lut = 16'd36712;
            7'd101: recip_lut = 16'd36552;
            7'd102: recip_lut = 16'd36393;
            7'd103: recip_lut = 16'd36236;
            7'd104: recip_lut = 16'd36080;
            7'd105: recip_lut = 16'd35926;
            7'd106: recip_lut = 16'd35772;
            7'd107: recip_lut = 16'd35620;
            7'd108: recip_lut = 16'd35470;
            7'd109: recip_lut = 16'd35320;
            7'd110: recip_lut = 16'd35172;
            7'd111: recip_lut = 16'd35026;
            7'd112: recip_lut = 16'd34880;
            7'd113: recip_lut = 16'd34735;
            7'd114: recip_lut = 16'd34592;
            7'd115: recip_lut = 16'd34450;
            7'd116: recip_lut = 16'd34309;
            7'd117: recip_lut = 16'd34169;
            7'd118: recip_lut = 16'd34031;
            7'd119: recip_lut = 16'd33893;
            7'd120: recip_lut = 16'd33757;
            7'd121: recip_lut = 16'd33622;
            7'd122: recip_lut = 16'd33487;
            7'd123: recip_lut = 16'd33354;
            7'd124: recip_lut = 16'd33222;
            7'd125: recip_lut = 16'd33091;
            7'd126: recip_lut = 16'd32961;
            7'd127: recip_lut = 16'd32832;
            default: recip_lut = 16'd0;
        endcase
    endfunction

    logic signed [15:0] mx;
    logic [N*17-1:0]    ev;
    logic [31:0]        ssum;
    logic [5:0]         pb;
    logic [31:0]        ms;
    logic [15:0]        rl;
    logic [63:0]        prod;
    logic [N*16-1:0]    pout;
    always_comb begin
        mx = $signed(x[15:0]);
        for (int i = 1; i < N; i++) if ($signed(x[i*16 +: 16]) > mx) mx = $signed(x[i*16 +: 16]);
        ssum = 32'd0;
        for (int i = 0; i < N; i++) begin
            ev[i*17 +: 17] = exp2neg(16'(mx - $signed(x[i*16 +: 16])));
            ssum = ssum + ev[i*17 +: 17];
        end
        pb = 6'd0;
        for (int j = 0; j < 32; j++) if (ssum[j]) pb = j;
        ms = ssum >> (pb - 6'd15);
        rl = recip_lut(ms[14:8]);
        for (int i = 0; i < N; i++) begin
            prod = {47'd0, ev[i*17 +: 17]} * {48'd0, rl} + (64'd1 << pb);
            pout[i*16 +: 16] = prod >> (pb + 6'd1);
        end
    end
    always_ff @(posedge clk) begin
        if (!rst_n) out_valid <= 1'b0;
        else out_valid <= in_valid;
        if (in_valid) p <= pout;
    end
endmodule
