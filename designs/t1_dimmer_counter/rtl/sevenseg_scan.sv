// sevenseg_scan.sv: drive the Nexys A7's eight common-anode digits, one at a
// time, 0 (rightmost) to 7, each for 2^REFRESH_BITS clocks. A digit whose
// blank bit is set stays dark. Anodes and segments are active low and
// registered together, so they always change on the same clock.

module sevenseg_scan #(
    parameter int REFRESH_BITS = 17           // 2^17 clocks = 1.31 ms a digit at 100 MHz
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        enable,               // 0: every digit dark
    input  logic [31:0] digits,               // digit k = digits[4k+3:4k]
    input  logic [7:0]  blank,                // 1: digit k stays dark
    output logic [7:0]  an,                   // active low
    output logic [6:0]  seg                   // active low, seg[0] = a ... seg[6] = g
);
    logic [REFRESH_BITS+2:0] scan;
    wire  [2:0] k   = scan[REFRESH_BITS+2:REFRESH_BITS];
    wire  [3:0] nib = digits[{k, 2'b00} +: 4];

    function automatic logic [6:0] glyph(input logic [3:0] n);   // segments lit, bit 0 = a
        case (n)
            4'h0: glyph = 7'b0111111;
            4'h1: glyph = 7'b0000110;
            4'h2: glyph = 7'b1011011;
            4'h3: glyph = 7'b1001111;
            4'h4: glyph = 7'b1100110;
            4'h5: glyph = 7'b1101101;
            4'h6: glyph = 7'b1111101;
            4'h7: glyph = 7'b0000111;
            4'h8: glyph = 7'b1111111;
            4'h9: glyph = 7'b1101111;
            4'hA: glyph = 7'b1110111;
            4'hB: glyph = 7'b1111100;
            4'hC: glyph = 7'b0111001;
            4'hD: glyph = 7'b1011110;
            4'hE: glyph = 7'b1111001;
            default: glyph = 7'b1110001;   // F
        endcase
    endfunction

    always_ff @(posedge clk) begin
        if (rst) begin
            scan <= '0;
            an   <= '1;
            seg  <= '1;
        end else begin
            scan <= scan + 1'b1;
            an   <= (enable && !blank[k]) ? ~(8'b1 << k) : 8'hFF;
            seg  <= ~glyph(nib);
        end
    end
endmodule
