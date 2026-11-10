// P9-2 reference: 1280x720@60 colour bars on the Nexys A7 VGA connector (CEA-861 timing, 74.25 MHz pixel clock, positive syncs). SIM = 1 swaps the MMCM for a wire.
// (Copy of the lab top labs/p9_video/vga_pattern_top_720p.sv; PIX_25_175 = 1 selects the 74.25 MHz MMCM settings.)
// Part 9 lab 1 (Nexys A7-100T, VGA): the test patterns of lesson 2 on a monitor, 640 x 480 at about 60 Hz.
//
// 100 MHz oscillator -> MMCME2_BASE -> pixel clock: 25.1748 MHz (VCO 900 MHz = 100 MHz x 9, CLKOUT0 divide 35.75; 6.9 ppm from 25.175) or, with
// PIX_25_175 = 0, exactly 25.000 MHz (VCO 600 MHz, divide 24). The timing generator and pattern generator are the course's reference solutions
// (solutions/p9l02_vtg, solutions/p9l02_tpg). SW[1:0] picks the pattern (bars, checkerboard, ramp, moving box); BTNC is a reset. Both cross into the pixel clock through two-flop synchronisers (07a1c).
// The pattern generator registers its colour, so hs and vs are delayed by one clock to stay aligned with it (lesson 2, section 5).
// SIM = 1 swaps the MMCM for a wire so the file also runs in Icarus (labs/p9_video/test_lab_vga.py).
module vga_bars_720p #(
    parameter bit SIM = 1'b0,
    parameter bit PIX_25_175 = 1'b1
) (
    input  logic        CLK100MHZ,
    input  logic        BTNC,
    input  logic [1:0]  SW,
    output logic        LED0,
    output logic [3:0]  VGA_R,
    output logic [3:0]  VGA_G,
    output logic [3:0]  VGA_B,
    output logic        VGA_HS,
    output logic        VGA_VS
);
    logic pix_clk, locked;
    assign LED0 = locked;                  // lit when the MMCM has locked
    generate
        if (SIM) begin : g_sim
            assign pix_clk = CLK100MHZ;
            assign locked  = 1'b1;
        end else begin : g_mmcm
            logic clkfb, clk0, clk0_b;
            MMCME2_BASE #(
                .CLKIN1_PERIOD(10.000),
                .DIVCLK_DIVIDE(PIX_25_175 ? 5 : 1),
                .CLKFBOUT_MULT_F(PIX_25_175 ? 37.125 : 6.000),
                .CLKOUT0_DIVIDE_F(PIX_25_175 ? 10.000 : 24.000)
            ) u_mmcm (
                .CLKIN1(CLK100MHZ), .CLKFBIN(clkfb), .CLKFBOUT(clkfb), .CLKOUT0(clk0), .LOCKED(locked), .PWRDWN(1'b0), .RST(1'b0),
                .CLKOUT0B(), .CLKOUT1(), .CLKOUT1B(), .CLKOUT2(), .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(), .CLKOUT4(), .CLKOUT5(), .CLKOUT6(), .CLKFBOUTB()
            );
            BUFG u_bufg (.I(clk0), .O(pix_clk));
        end
    endgenerate

    // BTNC and SW come from the 100 MHz oscillator's world (a button and slide switches), not from the pixel clock: each goes through a two-flop synchroniser
    // (ASYNC_REG keeps both flops together and tells Vivado's CDC check the crossing is handled)
    (* ASYNC_REG = "TRUE" *) logic [1:0] btn_sync = 2'b00;
    (* ASYNC_REG = "TRUE" *) logic [1:0] sw_sync0 = 2'b00, sw_sync1 = 2'b00;
    always_ff @(posedge pix_clk) begin
        btn_sync <= {btn_sync[0], ~BTNC};
        sw_sync0 <= SW;
        sw_sync1 <= sw_sync0;
    end

    // reset: held while the MMCM is unlocked or BTNC is pressed, released synchronously
    logic [2:0] rst_sr = '0;
    always_ff @(posedge pix_clk or negedge locked)
        if (!locked) rst_sr <= '0;
        else         rst_sr <= {rst_sr[1:0], btn_sync[1]};
    wire rst_n = rst_sr[2];

    logic hs, vs, de, sof, eol;
    logic [11:0] x, y;
    vtg #(.H_ACT(1280), .H_FP(110), .H_SYNC(40), .H_BP(220), .V_ACT(720), .V_FP(5), .V_SYNC(5), .V_BP(20), .HS_POL(1'b1), .VS_POL(1'b1)) u_vtg (
        .clk(pix_clk), .rst_n(rst_n), .hs(hs), .vs(vs), .de(de), .x(x), .y(y), .sof(sof), .eol(eol));

    logic [7:0] frame = '0;
    always_ff @(posedge pix_clk) if (sof) frame <= frame + 8'd1;

    // the timing generator shows h = 0, v = 0 (an active pixel) while it is held in reset, so de is gated with rst_n: no lit pixels during reset
    logic de_q;
    logic [3:0] r, g, b;
    tpg #(.W(1280), .H(720)) u_tpg (.clk(pix_clk), .de(de & rst_n), .x(x), .y(y), .sel(sw_sync1), .frame(frame), .de_q(de_q), .r(r), .g(g), .b(b));

    // tpg registers the colour (one clock), so hs and vs take one extra register too; then everything leaves the chip from one final register rank
    logic hs_d, vs_d;
    always_ff @(posedge pix_clk) begin
        hs_d <= hs;
        vs_d <= vs;
        VGA_R  <= r;
        VGA_G  <= g;
        VGA_B  <= b;
        VGA_HS <= hs_d;
        VGA_VS <= vs_d;
    end
endmodule
