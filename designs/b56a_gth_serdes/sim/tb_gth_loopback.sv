`timescale 1ns/1ps
// tb_gth_loopback.sv: xsim bench for gth_serdes_core with the real GT Wizard simulation model (UNISIM GTHE4 secureip), the
// transmitter looped to the receiver through the serial pins, driven through the host register bus (brief 56A).
// Prints "CHECK <name> PASS|FAIL <detail>" lines and "RESULT <key> <value>" lines; ends with "TB-DONE <fails>".
module tb_gth_loopback;
    logic clk = 0, refclk = 0, rst = 1;
    always #5.0 clk = ~clk;                       // 100 MHz free-running clock
`ifdef GT_STANDIN
    always #3.103 refclk = ~refclk;               // the stand-in uses the reference as both user clocks: 161.13 MHz (sim/gth_wiz_model.sv)
`else
    always #3.2 refclk = ~refclk;                 // 156.25 MHz reference
`endif
    logic        h_we = 0, h_re = 0;
    logic [11:0] h_addr = 0;
    logic [31:0] h_wdata = 0;
    wire  [31:0] h_rdata;
    wire         txp, txn, tx_dis, scl_low, sda_low, sm_en;
    wire  [7:0]  sm_addr;
    wire  [1:0]  led;
    logic [15:0] sm_do = 16'hABCD;
    logic        sm_rdy = 0;
    logic        sm_busy = 0;
    // SYSMON model: answers a read with 0xABCD three clocks later
    always_ff @(posedge clk) begin
        sm_rdy <= 1'b0;
        if (sm_en) sm_busy <= 1'b1;
        else if (sm_busy) begin sm_busy <= 1'b0; sm_rdy <= 1'b1; end
    end
    gth_serdes_core #(.BUILD_STAMP(32'h56A0_5EED)) dut (
        .clk, .rst, .h_we, .h_re, .h_addr, .h_wdata, .h_rdata,
        .refclk, .rx_p(txp), .rx_n(txn), .tx_p(txp), .tx_n(txn),
        .sfp_tx_disable(tx_dis), .sfp_mod_abs(1'b0), .sfp_rx_los(1'b0), .sfp_tx_fault(1'b0),
        .i2c_scl_low(scl_low), .i2c_sda_low(sda_low), .i2c_scl_i(~scl_low), .i2c_sda_i(~sda_low),
        .sm_en, .sm_addr, .sm_do, .sm_rdy, .led);

    int fails = 0;
    task automatic wr(input [11:0] a, input [31:0] d);
        @(posedge clk); h_addr <= a; h_wdata <= d; h_we <= 1'b1;
        @(posedge clk); h_we <= 1'b0;
    endtask
    task automatic rd(input [11:0] a, output [31:0] d);
        @(posedge clk); h_addr <= a; h_re <= 1'b1;
        @(posedge clk); h_re <= 1'b0;
        repeat (3) @(posedge clk);
        d = h_rdata;
    endtask
    task automatic check(input string name, input bit ok, input string detail);
        $display("CHECK %s %s %s", name, ok ? "PASS" : "FAIL", detail);
        if (!ok) fails++;
    endtask
    task automatic wait_status(input int bit_i, input int max_us, output bit ok);
        logic [31:0] s;
        ok = 0;
        for (int i = 0; i < max_us && !ok; i++) begin
            rd(12'h014, s);
            if (s[bit_i]) ok = 1; else #(1000.0);
        end
    endtask
    task automatic snap(output logic [63:0] words, output logic [63:0] errb, output logic [31:0] errw, output logic [15:0] loss,
                        output logic [63:0] hcyc, output logic [63:0] herr);
        logic [31:0] v, w;
        wr(12'h010, 32'h100);                                     // snapshot the (live) counters
        #(2000.0);
        wr(12'h010, 32'h100);                                     // the live copy is refreshed every few clocks: a second snapshot is current
        repeat (4) @(posedge clk);
        rd(12'h020, v); rd(12'h024, w); words = {w, v};
        rd(12'h028, v); rd(12'h02C, w); errb = {w, v};
        rd(12'h030, errw); rd(12'h034, v); loss = v[15:0];
        rd(12'h038, v); rd(12'h03C, w); hcyc = {w, v};
        rd(12'h040, v); rd(12'h044, w); herr = {w, v};
    endtask

    logic [31:0] r;
    logic [63:0] words, errb, hcyc, herr; logic [31:0] errw; logic [15:0] loss;
    bit ok;
    initial begin
        repeat (20) @(posedge clk);
        rst <= 1'b0;
        rd(12'h000, r); check("id", r == 32'h56A0_0001, $sformatf("%08h", r));
        rd(12'h004, r); check("build_stamp", r == 32'h56A0_5EED, $sformatf("%08h", r));
        rd(12'h00C, r); check("ctrl_reset_value", r == 32'h0005_3008, $sformatf("%08h", r));
        check("laser_disabled_at_reset", tx_dis === 1'b1, $sformatf("sfp_tx_disable=%b", tx_dis));
        rd(12'h1FC, r); check("unmapped_read_zero", r == 32'h0, $sformatf("%08h", r));
        // link bring-up: reset helper, QPLL lock, CDR lock
        wait_status(0, 2000, ok); check("tx_reset_done", ok, "STATUS[0]");
        wait_status(1, 2000, ok); check("rx_reset_done", ok, "STATUS[1]");
        rd(12'h014, r); $display("RESULT status_after_bringup %08h", r);
        // fabric PRBS-31 over the serial loop
        wait_status(9, 400, ok); check("fabric_prbs_locked", ok, "STATUS[9]");
        #(60000.0);
        snap(words, errb, errw, loss, hcyc, herr);
        $display("RESULT fab_words_60us %0d", words); $display("RESULT fab_errbits %0d", errb);
        check("fabric_words_counted", words > 5000, $sformatf("%0d words", words));
        check("fabric_no_errors", errb == 0 && errw == 0, $sformatf("errbits=%0d errwords=%0d", errb, errw));
        // injected error
        wr(12'h010, 32'h40); #(10000.0);
        snap(words, errb, errw, loss, hcyc, herr);
        check("fabric_injected_error_counted", errb == 1 && errw == 1, $sformatf("errbits=%0d errwords=%0d", errb, errw));
        // the polynomial change restarts and relocks
        rd(12'h00C, r); wr(12'h00C, (r & ~32'h3000) | (32'd2 << 12)); #(40000.0);
        rd(12'h014, r); check("fabric_relock_prbs23", r[9], $sformatf("STATUS=%08h", r));
        snap(words, errb, errw, loss, hcyc, herr);
        check("prbs23_no_errors", errb == 0, $sformatf("errbits=%0d words=%0d", errb, words));
        // GT's own PRBS-31 generator and checker
        wr(12'h00C, 32'h0005_3008 | (32'd5 << 4) | (32'd5 << 8)); #(40000.0);
        rd(12'h014, r); check("hard_prbs_locked", r[10], $sformatf("STATUS=%08h", r));
        wr(12'h010, 32'h20); #(30000.0);
        snap(words, errb, errw, loss, hcyc, herr);
        $display("RESULT hard_cycles %0d", hcyc); $display("RESULT hard_err %0d", herr);
        check("hard_cycles_counted", hcyc > 2000, $sformatf("%0d cycles", hcyc));
        check("hard_no_errors", herr == 0, $sformatf("%0d error cycles", herr));
        wr(12'h010, 32'h80); #(10000.0);
        snap(words, errb, errw, loss, hcyc, herr);
        check("hard_injected_error_counted", herr >= 1, $sformatf("%0d error cycles", herr));
        // sticky bit: the fabric checker lost lock when the GT took over the data
        rd(12'h018, r); check("sticky_fab_lock_lost", r[2], $sformatf("STICKY=%02h", r[5:0]));
        wr(12'h018, 32'h3F); rd(12'h018, r); check("sticky_w1c", r[5:0] == 0, $sformatf("STICKY=%02h", r[5:0]));
        // I2C bit-bang, SYSMON and DRP windows
        wr(12'h050, 32'h1); rd(12'h050, r); check("i2c_scl_low", r[0] && !r[8], $sformatf("%08h", r));
        wr(12'h050, 32'h0); rd(12'h050, r); check("i2c_released", !r[0] && r[8], $sformatf("%08h", r));
        wr(12'h060, 32'h00); repeat (8) @(posedge clk); rd(12'h064, r); check("sysmon_read", r == 32'h0001_ABCD, $sformatf("%08h", r));
        wr(12'h070, 32'h0); wr(12'h078, 32'h1); repeat (200) @(posedge clk); rd(12'h078, r);
        check("gt_drp_read_done", r[1] && !r[0], $sformatf("DRP_CTRL=%08h", r)); rd(12'h074, r); $display("RESULT drp_addr0_data %04h", r[15:0]);
        // loopback modes: near-end PMA loopback then back to normal needs a GTRXRESET: checked on hardware, not here
        $display("TB-DONE %0d", fails);
        $finish;
    end
endmodule
