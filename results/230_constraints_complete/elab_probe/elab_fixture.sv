// Brief 230 probe fixture: clock sources of every kind in one top, so check_timing and report_clocks can be read on the elaborated
// design (synth_design -rtl) and on the synthesised one. Not a design: nothing here is meant to do anything useful.
module elab_fixture (
    input  logic clk_in,        // board clock: create_clock in elab_fixture.xdc
    input  logic din_ok,        // set_input_delay in the XDC
    input  logic din_missing,   // no constraint at all
    output logic dout_ok,       // set_output_delay in the XDC
    output logic dout_missing,  // no constraint at all
    output logic dout_fp        // set_false_path -to only (no delay)
);
    logic [31:0] usr;
    logic cfgclk, datavalid;
    USR_ACCESSE2 u_usr (.CFGCLK(cfgclk), .DATA(usr), .DATAVALID(datavalid));          // no XDC line: the case of the 224 p5 run

    logic tck, tdi, tdo, sel, shift, capture, update;
    BSCANE2 #(.JTAG_CHAIN(4)) u_bscan (.TCK(tck), .TDI(tdi), .TDO(tdo), .SEL(sel), .SHIFT(shift), .CAPTURE(capture),
        .UPDATE(update), .DRCK(), .RESET(), .RUNTEST(), .TMS());                       // no XDC line
    logic [7:0] sr_tck;
    always_ff @(posedge tck) sr_tck <= {sr_tck[6:0], tdi};
    assign tdo = sr_tck[7];

    logic clk_div;                                                                      // BUFGCE_DIV on the board clock
    BUFGCE_DIV #(.BUFGCE_DIVIDE(2)) u_div (.I(clk_in), .CE(1'b1), .CLR(1'b0), .O(clk_div));
    logic [7:0] cnt_div;
    always_ff @(posedge clk_div) cnt_div <= cnt_div + 8'd1;

    logic mm_fb, mm_o0, mm_lock;                                                        // MMCM on the board clock
    MMCME4_ADV #(.CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT_F(10.0), .CLKOUT0_DIVIDE_F(5.0), .DIVCLK_DIVIDE(1)) u_mmcm (
        .CLKIN1(clk_in), .CLKFBIN(mm_fb), .CLKFBOUT(mm_fb), .CLKOUT0(mm_o0), .LOCKED(mm_lock), .PWRDWN(1'b0), .RST(1'b0),
        .CLKIN2(1'b0), .CLKINSEL(1'b1), .DADDR(7'd0), .DCLK(1'b0), .DEN(1'b0), .DI(16'd0), .DWE(1'b0), .PSCLK(1'b0), .PSEN(1'b0), .PSINCDEC(1'b0), .CDDCREQ(1'b0));
    logic [7:0] cnt_mm;
    always_ff @(posedge mm_o0) cnt_mm <= cnt_mm + 8'd1;

    logic fab_div = 1'b0;                                                               // a fabric register used as a clock
    always_ff @(posedge clk_in) fab_div <= ~fab_div;
    logic [7:0] cnt_fab;
    always_ff @(posedge fab_div) cnt_fab <= cnt_fab + 8'd1;

    logic [7:0] cnt_usr;                                                                // registers clocked by the USR_ACCESSE2 clock
    always_ff @(posedge cfgclk) cnt_usr <= usr[7:0] ^ cnt_usr;

    logic r_in, r_in_missing;
    always_ff @(posedge clk_in) begin r_in <= din_ok; r_in_missing <= din_missing; end
    assign dout_ok      = r_in ^ cnt_div[7] ^ cnt_mm[7];
    assign dout_missing = r_in_missing ^ cnt_fab[7] ^ cnt_usr[7] ^ sr_tck[0] ^ mm_lock;
    assign dout_fp      = cnt_fab[0] ^ r_in;
endmodule
