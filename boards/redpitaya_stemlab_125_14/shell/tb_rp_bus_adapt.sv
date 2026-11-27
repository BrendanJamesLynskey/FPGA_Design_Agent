// Self-checking test bench of rp_bus_adapt with rp_user_block behind it (brief 243): iverilog -g2012 tb_rp_bus_adapt.sv rp_bus_adapt.sv rp_user_block.sv; vvp prints
// "BUS ADAPT PASS" and one "case ... PASS" line per case.
//
// The shell side is a behavioural model of what the vendor's clock-crossing bridge does, written from the measured behaviour (hdl sim of the pinned vendor
// files, hil/rp_bus_sim): the request is seen by the slot SIN clocks after the PS raises it, is HELD until the slot's ack has been seen (then dropped the
// next cycle), and the PS samples the slot's rdata combinationally SOUT clocks after the ack was raised. It is a model of the contract, not the vendor's
// text. Cases cover SIN 2 to 3, SOUT 2 to 5, and a block that never acks.
// What it would have caught: with the block wired straight to this model (no adapter, DIRECT=1) every read returns 0, as build 170300fd did on the board.
module bridge_case #(
    parameter int SIN = 2,
    parameter int SOUT = 3,
    parameter bit SILENT = 0,
    parameter bit DIRECT = 0,
    parameter string NAME = "case"
);
    logic clk = 0, rstn = 0;
    always #4 clk = ~clk;
    logic [31:0] addr = 0, wdata = 0;
    // shell side
    logic        s_wen = 0, s_ren = 0, s_err, s_ack;
    logic [31:0] s_rdata;
    // block side
    logic [31:0] b_addr, b_wdata, b_rdata;
    logic        b_wen, b_ren, b_err, b_ack;
    logic signed [13:0] a = -14'sd100, b = 14'sd77, da, db;

    generate
        if (DIRECT) begin : g_direct
            assign b_addr = addr; assign b_wdata = wdata; assign b_wen = s_wen; assign b_ren = s_ren;
            assign s_rdata = b_rdata; assign s_err = b_err; assign s_ack = b_ack;
        end else begin : g_adapt
            rp_bus_adapt dut_adapt (.clk(clk), .rstn(rstn), .s_addr(addr), .s_wdata(wdata), .s_wen(s_wen), .s_ren(s_ren), .s_rdata(s_rdata), .s_err(s_err), .s_ack(s_ack),
                                    .b_addr(b_addr), .b_wdata(b_wdata), .b_wen(b_wen), .b_ren(b_ren), .b_rdata(b_rdata), .b_err(b_err), .b_ack(b_ack));
        end
        if (SILENT) begin : g_silent
            assign b_rdata = 32'hDEAD_BEEF; assign b_err = 1'b0; assign b_ack = 1'b0;
        end else begin : g_blk
            rp_user_block blk (.clk(clk), .rstn(rstn), .sys_addr(b_addr), .sys_wdata(b_wdata), .sys_wen(b_wen), .sys_ren(b_ren), .sys_rdata(b_rdata), .sys_err(b_err), .sys_ack(b_ack),
                               .adc_a(a), .adc_b(b), .dac_a(da), .dac_b(db));
        end
    endgenerate

    // count the accesses the block is shown: one per shell access
    int n_wen = 0, n_ren = 0;
    always @(posedge clk) begin if (b_wen) n_wen++; if (b_ren) n_ren++; end

    int fails = 0;
    // one access through the bridge model. Returns what the PS sees: rdata and err sampled SOUT clocks after the slot's ack was first raised; timeout = no ack within 40 clocks.
    task automatic access(input bit w, input [31:0] ad, input [31:0] d, output [31:0] rd, output bit er, output bit timeout);
        int t;
        @(posedge clk); addr = ad; wdata = d;
        repeat (SIN) @(posedge clk);
        if (w) s_wen = 1; else s_ren = 1;                  // held from here until the ack has been seen
        t = 0; timeout = 0;
        @(posedge clk);
        while (!s_ack && t < 40) begin @(posedge clk); t++; end
        if (!s_ack) timeout = 1;
        s_wen = 0; s_ren = 0;
        repeat (SOUT) @(posedge clk);                       // the ack travels back; the PS then samples
        rd = s_rdata; er = s_err;
        repeat (6) @(posedge clk);
    endtask
    task automatic rdchk(input [31:0] ad, input [31:0] want, input bit want_err, input string what);
        logic [31:0] r; bit e, to;
        access(0, ad, 0, r, e, to);
        if (to || r !== want || e !== want_err) begin $display("  %s: read %h err %b timeout %b, want %h err %b", what, r, e, to, want, want_err); fails++; end
    endtask
    task automatic wrchk(input [31:0] ad, input [31:0] d, input bit want_err, input string what);
        logic [31:0] r; bit e, to;
        access(1, ad, d, r, e, to);
        if (to || e !== want_err) begin $display("  %s: write err %b timeout %b, want err %b", what, e, to, want_err); fails++; end
    endtask

    initial begin
        logic [31:0] r; bit e, to;
        repeat (3) @(posedge clk); rstn = 1; repeat (2) @(posedge clk);
        if (SILENT) begin
            access(0, 32'h0, 0, r, e, to);
            // the adapter answers a silent block with an error after TIMEOUT clocks, so the shell's bus is not held; without it (DIRECT) there is no answer at all
            if (DIRECT ? !to : (to || !e || r !== 0)) begin $display("  silent block: rdata %h err %b timeout %b", r, e, to); fails++; end
        end else begin
            rdchk(32'h0, 32'hFDA10001, 0, "ID");
            wrchk(32'h4, 32'hCAFEF00D, 0, "SCRATCH write");
            rdchk(32'h4, 32'hCAFEF00D, 0, "SCRATCH read");
            rdchk(32'h10, 32'd77, 0, "IN2");
            rdchk(32'h0, 32'hFDA10001, 0, "ID again (a read after a read of another register)");
            wrchk(32'h0, 32'h1, 1, "write to read-only ID is an error");
            rdchk(32'h1C, 32'h0, 1, "unmapped read is an error with rdata 0");
            rdchk(32'h4, 32'hCAFEF00D, 0, "SCRATCH unchanged");
            // the block is shown each access once, however long the shell holds the request
            if (!DIRECT && (n_wen !== 2 || n_ren !== 6)) begin $display("  block saw %0d writes and %0d reads, want 2 and 6", n_wen, n_ren); fails++; end
            // DAC register: a held write must not be repeated into a different value (write twice is harmless here, count shows once)
            wrchk(32'h14, 32'h3FFF, 0, "DAC1 write");
            if (da !== -14'sd1) begin $display("  DAC1 %0d", da); fails++; end
        end
        if (fails == 0) $display("%s PASS", NAME); else $display("%s FAIL %0d", NAME, fails);
    end
endmodule

module tb;
    // adapter: every crossing delay and the silent block
    bridge_case #(.SIN(2), .SOUT(2), .NAME("case sin2 sout2")) c1();
    bridge_case #(.SIN(2), .SOUT(3), .NAME("case sin2 sout3")) c2();
    bridge_case #(.SIN(3), .SOUT(4), .NAME("case sin3 sout4")) c3();
    bridge_case #(.SIN(2), .SOUT(5), .NAME("case sin2 sout5")) c4();
    bridge_case #(.SIN(2), .SOUT(3), .SILENT(1), .NAME("case silent block")) c5();
    // the same model with the block wired straight on: expected to FAIL (reads return 0), the proof the model has teeth
    bridge_case #(.SIN(2), .SOUT(3), .DIRECT(1), .NAME("case direct (expected FAIL)")) d1();
    bridge_case #(.SIN(2), .SOUT(3), .SILENT(1), .DIRECT(1), .NAME("case direct silent (expected PASS: no answer)")) d2();
    initial begin
        #200000;
        if (c1.fails + c2.fails + c3.fails + c4.fails + c5.fails == 0 && d1.fails != 0 && d2.fails == 0) $display("BUS ADAPT PASS");
        else $display("BUS ADAPT FAIL %0d %0d %0d %0d %0d direct %0d %0d", c1.fails, c2.fails, c3.fails, c4.fails, c5.fails, d1.fails, d2.fails);
        $finish;
    end
endmodule
