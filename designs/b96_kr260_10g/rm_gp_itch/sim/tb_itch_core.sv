`timescale 1ns/1fs
// tb_itch_core.sv (brief 127): the WHOLE core of build rm_gp_itch (b96_core: PCS, rate matcher, MACs, ITCH path, transmit multiplexer, host registers) in xsim with AMD's real XPM macros
// and the behavioural GT stand-in (sim/gth_wiz_model96e.sv; the real GT model is refused by the free simulator), at a chosen phase between the receive and transmit user clocks
// (compile with -d RXPH=<ns>). The testbench is a HOST: it reads a script of register operations (`+script=<file>`, one per line) and executes them on the register bus exactly as the
// board's driver would, so the same script, made by host/itch_host.py, runs here and on the board:
//   W <addr hex> <data hex>   register write          R <addr hex>   read, printed as  RD <addr> <data>
//   D <ns>                    wait                     L              wait for the link (GT_STAT TX_DONE, RX_DONE, PCS block lock)
//   P <text>                  print a marker line      E              end
// Monitors (printed, one line each; times are the absolute ns of the clock edge that LOADS the signal): XW <n> <idx> <t> the receiver's PCS output words of frame n (idx 0 is the
// start word, idx 1 the first data word); MW <idx> <t> the MAC receiver's output words (idx 0 is the destination MAC word); GO <t> the risk logic's start of an order; OSOP <t> the
// start strobe of an order frame in the transmit MAC (the clock its preamble word is in the MAC's output register); TXW <d> <c> every non-idle word the transmit MAC hands to the PCS.
module tb_itch_core #(
    parameter bit RM_OWN = 1'b1
);
    localparam real TREF = 6.2058;
    logic clk = 1'b0, refclk = 1'b0, rst = 1'b1;
    logic h_we = 1'b0, h_re = 1'b0;
    logic [11:0] h_addr = '0;
    logic [31:0] h_wdata = '0, h_rdata;
    logic sfp_tx_disable, tx_p, tx_n, scl_low, sda_low, sm_en;
    logic [1:0] led;
    logic [7:0] sm_addr;
    always #5.0 clk = ~clk;
    always #(TREF / 2.0) refclk = ~refclk;
    b96_core #(.BUILD_STAMP(32'h127), .NEAR_END(1'b1), .TRADE(1'b0), .RATE_MATCH(1'b1), .RM_OWN(RM_OWN)) u (.clk, .rst, .h_we, .h_re, .h_addr, .h_wdata, .h_rdata, .refclk,
        .rx_p(1'b0), .rx_n(1'b1), .tx_p, .tx_n, .sfp_tx_disable, .sfp_mod_abs(1'b0), .sfp_rx_los(1'b0), .sfp_tx_fault(1'b0),
        .i2c_scl_low(scl_low), .i2c_sda_low(sda_low), .i2c_scl_i(1'b1), .i2c_sda_i(1'b1), .sm_en, .sm_addr, .sm_do(16'h0), .sm_rdy(sm_en), .led);

    // register bus operations are driven on the falling edge of clk, so no clock edge races them
    task automatic hw(input [11:0] a, input [31:0] d);
        @(negedge clk); h_addr = a; h_wdata = d; h_we = 1'b1; @(negedge clk); h_we = 1'b0; @(negedge clk);
    endtask
    task automatic hr(input [11:0] a, output [31:0] d);
        @(negedge clk); h_addr = a; h_re = 1'b1; @(negedge clk); h_re = 1'b0; @(negedge clk); @(negedge clk); d = h_rdata;
    endtask

    // ---------------------------------------------------------------- monitors
    logic        txclk, rxclk;
    assign txclk = u.txusr2; assign rxclk = u.rxusr2;
    logic        x_v, y_v;
    logic [63:0] x_d, y_d;
    logic [7:0]  x_c, y_c;
    assign x_v = u.g_rm.u_rx.x_v; assign x_d = u.g_rm.u_rx.x_d; assign x_c = u.g_rm.u_rx.x_c;
    int          nx, nf;
    realtime     quiet;
    initial begin nx = -1; nf = 0; end
    always @(posedge rxclk) begin
        realtime t;
        t = $realtime;
        #0.05;
        if (x_v) begin
            if ((x_c == 8'h01 && x_d[7:0] == 8'hFB) || (x_c == 8'h1F && x_d[39:32] == 8'hFB)) begin nx = 0; nf = nf + 1; $display("XW %0d 0 %0.3f", nf, t); end
            else if (nx >= 0) begin
                nx = nx + 1;
                if (nx <= 20) $display("XW %0d %0d %0.3f", nf, nx, t);
                if (x_c != 8'h00 && x_c != 8'h01) nx = -1;
            end
        end
    end
    int nm;
    initial nm = 0;
    always @(posedge txclk) begin
        realtime t;
        t = $realtime;
        #0.05;
        if (u.g_rm.u_rx.m_v) begin
            if (u.g_rm.u_rx.m_sof) nm = 0; else nm = nm + 1;
            if (nm <= 20) $display("MW %0d %0.3f", nm, t);
        end
        if (u.g_rm.u_ip.u_it.go) $display("GO %0.3f", t);
        if (u.g_rm.u_tx.ord_sop) $display("OSOP %0.3f", t);
        if (u.g_rm.u_tx.adv && !(u.g_rm.u_tx.x_d == 64'h0707070707070707 && u.g_rm.u_tx.x_c == 8'hFF)) $display("TXW %h %h", u.g_rm.u_tx.x_d, u.g_rm.u_tx.x_c);
    end

    // ---------------------------------------------------------------- the host script
    integer fd, rc;
    string  cmd, text, fname;
    logic [31:0] va, vd, st;
    longint dly;
    initial begin
        if (!$value$plusargs("script=%s", fname)) begin $display("NO SCRIPT"); $finish; end
        repeat (6) @(posedge clk);
        rst = 1'b0;
        fd = $fopen(fname, "r");
        if (fd == 0) begin $display("CANNOT OPEN %s", fname); $finish; end
        while (!$feof(fd)) begin
            rc = $fscanf(fd, "%s", cmd);
            if (rc != 1) break;
            case (cmd)
                "W": begin rc = $fscanf(fd, "%h %h", va, vd); hw(va[11:0], vd); end
                "R": begin rc = $fscanf(fd, "%h", va); hr(va[11:0], vd); $display("RD %03h %08h", va[11:0], vd); end
                "D": begin rc = $fscanf(fd, "%d", dly); #(dly * 1.0); end
                "L": begin
                    st = 0;
                    for (int i = 0; i < 400 && !((st & 1) && (st & 2) && (st & 32'h200)); i++) begin #200; hr(12'h014, st); end
                    if (!((st & 1) && (st & 2) && (st & 32'h200))) begin $display("LINK DID NOT COME UP: GTSTAT %h", st); $finish; end
                    $display("LINK UP at %0t", $time);
                end
                "P": begin rc = $fgets(text, fd); $display("MARK %s", text); end
                "E": begin $display("DONE"); $finish; end
                default: begin $display("BAD COMMAND %s", cmd); $finish; end
            endcase
        end
        $display("DONE");
        $finish;
    end
endmodule
