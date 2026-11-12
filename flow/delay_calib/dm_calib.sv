// Delay-model calibration design. Each block is registered on both sides (fabric FFs in, fabric FFs or the
// DSP/BRAM's own registers out) so report_timing gives one operator's delay between two clock edges. Built out of
// context by flow/delay_calib/calib.tcl; flow/delay_calib/fit.py turns the paths into the per-family delay model.
// Every block's input registers carry dont_touch, so each measured path starts inside its own block (without it Vivado
// merged operand registers that tap the same shift-register bits across blocks). The DSP variants with AREG/BREG keep
// their operand registers free so synthesis can pull them into the slice.
// Blocks:
//   u_add16/u_add32/u_add64   adder between FFs (carry chain)
//   u_cmp32                   a < b between FFs (carry chain)
//   u_tab                     4-bit index -> 9-bit signed constant table (LUT levels)
//   u_mux16                   16:1 mux of 16 bits (LUT/MUXF levels)
//   u_mul9_lut, u_mul18_lut   multiply in LUTs and carry chains (use_dsp "no")
//   u_mul9_dsp0               multiply in a DSP48E1 with no internal register (fabric FFs kept by dont_touch)
//   u_mul18_dsp2              A/B and P registers in the DSP (two-stage)
//   u_mul18_dsp3              A/B, M and P registers in the DSP (three-stage)
//   u_bram0, u_bram1          1024 x 16 block RAM read without and with the output register
module dm_add #(parameter int W = 32) (input logic clk, input logic [W-1:0] a, b, output logic [W-1:0] s);
    (* dont_touch = "true" *) logic [W-1:0] ar, br;
    always_ff @(posedge clk) begin ar <= a; br <= b; s <= ar + br; end
endmodule

module dm_cmp #(parameter int W = 32) (input logic clk, input logic [W-1:0] a, b, output logic lt);
    (* dont_touch = "true" *) logic [W-1:0] ar, br;
    always_ff @(posedge clk) begin ar <= a; br <= b; lt <= ar < br; end
endmodule

module dm_tab (input logic clk, input logic [3:0] k, output logic signed [8:0] c);
    (* dont_touch = "true" *) logic [3:0] kr;
    function automatic signed [8:0] ctab(input [3:0] i);
        case (i)
            4'd0: ctab = 128;  4'd1: ctab = 126;  4'd2: ctab = 118;  4'd3: ctab = 106;
            4'd4: ctab = 91;   4'd5: ctab = 71;   4'd6: ctab = 49;   4'd7: ctab = 25;
            4'd8: ctab = 0;    4'd9: ctab = -25;  4'd10: ctab = -49; 4'd11: ctab = -71;
            4'd12: ctab = -91; 4'd13: ctab = -106; 4'd14: ctab = -118; default: ctab = -126;
        endcase
    endfunction
    always_ff @(posedge clk) begin kr <= k; c <= ctab(kr); end
endmodule

module dm_mux16 (input logic clk, input logic [255:0] d, input logic [3:0] sel, output logic [15:0] y);
    (* dont_touch = "true" *) logic [255:0] dr;
    (* dont_touch = "true" *) logic [3:0] sr;
    always_ff @(posedge clk) begin dr <= d; sr <= sel; y <= dr[sr*16 +: 16]; end
endmodule

module dm_mul_lut #(parameter int W = 9) (input logic clk, input logic signed [W-1:0] a, b, output logic signed [2*W-1:0] p);
    (* dont_touch = "true" *) logic signed [W-1:0] ar, br;
    (* use_dsp = "no" *) logic signed [2*W-1:0] m;
    assign m = ar * br;
    always_ff @(posedge clk) begin ar <= a; br <= b; p <= m; end
endmodule

module dm_mul_dsp0 #(parameter int W = 9) (input logic clk, input logic signed [W-1:0] a, b, output logic signed [2*W-1:0] p);
    (* dont_touch = "true" *) logic signed [W-1:0] ar, br;
    (* dont_touch = "true" *) logic signed [2*W-1:0] pr;
    (* use_dsp = "yes" *) logic signed [2*W-1:0] m;
    assign m = ar * br;
    always_ff @(posedge clk) begin ar <= a; br <= b; pr <= m; end
    assign p = pr;
endmodule

module dm_mul_dsp2 #(parameter int W = 18) (input logic clk, input logic signed [W-1:0] a, b, output logic signed [2*W-1:0] p);
    logic signed [W-1:0] ar, br;
    always_ff @(posedge clk) begin ar <= a; br <= b; p <= ar * br; end
endmodule

module dm_mul_dsp3 #(parameter int W = 18) (input logic clk, input logic signed [W-1:0] a, b, output logic signed [2*W-1:0] p);
    logic signed [W-1:0] ar, br; logic signed [2*W-1:0] mr;
    always_ff @(posedge clk) begin ar <= a; br <= b; mr <= ar * br; p <= mr; end
endmodule

module dm_bram #(parameter bit OREG = 0) (input logic clk, input logic we, input logic [9:0] wa, ra, input logic [15:0] wd,
                                          output logic [15:0] q);
    (* ram_style = "block" *) logic [15:0] mem [0:1023];
    logic [15:0] rd, rd2;
    always_ff @(posedge clk) begin
        if (we) mem[wa] <= wd;
        rd <= mem[ra];
        rd2 <= rd;
    end
    always_ff @(posedge clk) q <= OREG ? rd2 : rd;     // with OREG the second register goes into the RAM's output register
endmodule

module dm_calib (input logic clk, input logic [63:0] din, output logic [63:0] dout);
    // a shift register spreads din over a wide operand bus; dout is the registered XOR of every block's output
    logic [511:0] sh;
    always_ff @(posedge clk) sh <= {sh[447:0], din};
    logic [15:0] s16; logic [31:0] s32; logic [63:0] s64; logic lt; logic signed [8:0] c;
    logic [15:0] y16; logic signed [17:0] p9l, p9d; logic signed [35:0] p18l, p18d2, p18d3; logic [15:0] q0, q1;
    dm_add #(16) u_add16 (.clk, .a(sh[15:0]),  .b(sh[31:16]),  .s(s16));
    dm_add #(32) u_add32 (.clk, .a(sh[63:32]), .b(sh[95:64]),  .s(s32));
    dm_add #(64) u_add64 (.clk, .a(sh[159:96]), .b(sh[223:160]), .s(s64));
    dm_cmp #(32) u_cmp32 (.clk, .a(sh[255:224]), .b(sh[287:256]), .lt(lt));
    dm_tab u_tab (.clk, .k(sh[291:288]), .c(c));
    dm_mux16 u_mux16 (.clk, .d(sh[511:256]), .sel(sh[295:292]), .y(y16));
    dm_mul_lut #(9)  u_mul9_lut  (.clk, .a(sh[304:296]), .b(sh[313:305]), .p(p9l));
    dm_mul_lut #(18) u_mul18_lut (.clk, .a(sh[331:314]), .b(sh[349:332]), .p(p18l));
    dm_mul_dsp0 #(9) u_mul9_dsp0 (.clk, .a(sh[358:350]), .b(sh[367:359]), .p(p9d));
    dm_mul_dsp2 #(18) u_mul18_dsp2 (.clk, .a(sh[385:368]), .b(sh[403:386]), .p(p18d2));
    dm_mul_dsp3 #(18) u_mul18_dsp3 (.clk, .a(sh[421:404]), .b(sh[439:422]), .p(p18d3));
    dm_bram #(0) u_bram0 (.clk, .we(sh[440]), .wa(sh[450:441]), .ra(sh[460:451]), .wd(sh[476:461]), .q(q0));
    dm_bram #(1) u_bram1 (.clk, .we(sh[477]), .wa(sh[487:478]), .ra(sh[497:488]), .wd(sh[63:48]), .q(q1));
    always_ff @(posedge clk)
        dout <= s64 ^ {s32, s32} ^ {4{s16}} ^ {63'd0, lt} ^ {55'd0, c} ^ {4{y16}} ^ {46'd0, p9l} ^ {28'd0, p18l}
                ^ {46'd0, p9d} ^ {28'd0, p18d2} ^ {28'd0, p18d3} ^ {4{q0}} ^ {4{q1}};
endmodule
