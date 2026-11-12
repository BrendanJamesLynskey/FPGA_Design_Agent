// jtag_bus.sv: the host's register bus over the board's JTAG cable (BSCANE2, USER4), with no processor and no IP.
//
// The host shifts a 64-bit data register (least significant bit first, host/jtag_regs.tcl):
//   [31:0] write data   [43:32] register address   [44] write   [45] read   [63:46] zero
// At Update-DR the command is latched in the TCK domain and a toggle tells the core clock domain, which runs it on
// the register bus (a read waits the bus's two clocks). At Capture-DR the shift register loads
//   [31:0] the last read's data   [39:32] a count of completed commands   [63:48] 0x58A0 (a marker)
// so a read is: the read scan, then two more scans (no command) to clock the TCK-side synchroniser, the last of which
// returns the data. Only quasi-static values cross: each side holds its value until the other has seen the toggle.

module jtag_bus (
    input  logic        clk,
    input  logic        rst,
    output logic        h_we,
    output logic        h_re,
    output logic [11:0] h_addr,
    output logic [31:0] h_wdata,
    input  logic [31:0] h_rdata
);
    logic tck, tdi, tdo, sel, shift, capture, update;
`ifdef SYNTHESIS
    BSCANE2 #(.JTAG_CHAIN(4)) u_bscan (.TCK(tck), .TDI(tdi), .TDO(tdo), .SEL(sel), .SHIFT(shift), .CAPTURE(capture),
        .UPDATE(update), .DRCK(), .RESET(), .RUNTEST(), .TMS());
`else
    assign {tck, tdi, sel, shift, capture, update} = '0;
`endif
    // ---- TCK domain ----
    logic [63:0] sr;
    logic [45:0] cmd;
    logic        req_t;
    logic [39:0] resp_t;                // {count, data} as seen in the TCK domain
    always_ff @(posedge tck) begin
        if (sel && capture)      sr <= {16'h58A0, 8'h00, resp_t};
        else if (sel && shift)   sr <= {tdi, sr[63:1]};
        if (sel && update && (sr[44] || sr[45])) begin cmd <= sr[45:0]; req_t <= ~req_t; end
    end
    assign tdo = sr[0];

    // ---- core clock domain ----
    logic        req_s, req_q;
    logic [45:0] cmd_s;
    logic [39:0] resp;
    logic [1:0]  wait_n;
    logic        rd_pend;
    xpm_cdc_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_req (
        .src_clk(tck), .src_in(req_t), .dest_clk(clk), .dest_out(req_s));
    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0), .WIDTH(46)) u_cmd (
        .src_clk(tck), .src_in(cmd), .dest_clk(clk), .dest_out(cmd_s));
    always_ff @(posedge clk) begin
        h_we <= 1'b0; h_re <= 1'b0;
        if (rst) begin req_q <= 1'b0; resp <= '0; rd_pend <= 1'b0; wait_n <= '0; h_addr <= '0; h_wdata <= '0; end
        else begin
            req_q <= req_s;
            if (req_s != req_q) begin
                h_addr <= cmd_s[43:32]; h_wdata <= cmd_s[31:0];
                if (cmd_s[44]) begin h_we <= 1'b1; resp[39:32] <= resp[39:32] + 8'd1; end
                else begin h_re <= 1'b1; rd_pend <= 1'b1; wait_n <= 2'd0; end
            end
            if (rd_pend) begin
                wait_n <= wait_n + 2'd1;
                if (wait_n == 2'd2) begin rd_pend <= 1'b0; resp <= {resp[39:32] + 8'd1, h_rdata}; end
            end
        end
    end
    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1), .WIDTH(40)) u_resp (
        .src_clk(clk), .src_in(resp), .dest_clk(tck), .dest_out(resp_t));
endmodule
