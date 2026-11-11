// axil_table_ctrl.sv: AXI4-Lite front end for the match-action tables (exact, LPM, ternary).
//
// Register map (32-bit, byte addresses):
//   0x00..0x3C  DATA[0..15]   write-only staging, 512 bits; DATA[0] is bits 31:0
//   0x40        CMD           write: [3:0] op, [31:16] addr; issues one command to the table
//   0x44        STATUS        read: [0] busy, [7:4] last status, [31:16] commands completed (wraps)
//   0x48        ID            read: 0x7AB1_0001
// The table core sees cmd_* (a valid/ready command) and answers on rsp_*; how it reads DATA is the core's (see each
// core's header). Lookups never wait for commands: the cores update their memories on a second port. A write to
// CMD while busy is accepted and ignored (STATUS[0] says when the previous command finished); software polls.
// One outstanding read and one outstanding write; responses OKAY; no write strobes (whole words only).

module axil_table_ctrl (
    input  logic         clk,
    input  logic         rst,
    // AXI4-Lite slave
    input  logic [6:0]   s_axil_awaddr,
    input  logic         s_axil_awvalid,
    output logic         s_axil_awready,
    input  logic [31:0]  s_axil_wdata,
    input  logic         s_axil_wvalid,
    output logic         s_axil_wready,
    output logic [1:0]   s_axil_bresp,
    output logic         s_axil_bvalid,
    input  logic         s_axil_bready,
    input  logic [6:0]   s_axil_araddr,
    input  logic         s_axil_arvalid,
    output logic         s_axil_arready,
    output logic [31:0]  s_axil_rdata,
    output logic [1:0]   s_axil_rresp,
    output logic         s_axil_rvalid,
    input  logic         s_axil_rready,
    // table command port
    output logic         cmd_valid,
    input  logic         cmd_ready,
    output logic [3:0]   cmd_op,
    output logic [15:0]  cmd_addr,
    output logic [511:0] cmd_data,
    input  logic         rsp_valid,
    input  logic [3:0]   rsp_status
);
    logic        busy;
    logic [3:0]  last_status;
    logic [15:0] ndone;
    logic        aw_held, w_held;
    logic [6:0]  aw_q;
    logic [31:0] w_q;

    assign s_axil_awready = !aw_held && !s_axil_bvalid;
    assign s_axil_wready  = !w_held && !s_axil_bvalid;
    assign s_axil_bresp   = 2'b00;
    assign s_axil_rresp   = 2'b00;
    assign s_axil_arready = !s_axil_rvalid;

    always_ff @(posedge clk) begin
        if (rst) begin
            aw_held <= 1'b0; w_held <= 1'b0; aw_q <= '0; w_q <= '0; s_axil_bvalid <= 1'b0;
            s_axil_rvalid <= 1'b0; s_axil_rdata <= '0; cmd_valid <= 1'b0; cmd_op <= '0; cmd_addr <= '0;
            cmd_data <= '0; busy <= 1'b0; last_status <= '0; ndone <= '0;
        end else begin
            if (s_axil_awvalid && s_axil_awready) begin aw_held <= 1'b1; aw_q <= s_axil_awaddr; end
            if (s_axil_wvalid && s_axil_wready)   begin w_held <= 1'b1;  w_q <= s_axil_wdata; end
            if (aw_held && w_held) begin
                aw_held <= 1'b0; w_held <= 1'b0; s_axil_bvalid <= 1'b1;
                if (aw_q[6] == 1'b0) cmd_data[32 * aw_q[5:2] +: 32] <= w_q;
                else if (aw_q[5:2] == 4'd0 && !busy) begin
                    cmd_valid <= 1'b1; cmd_op <= w_q[3:0]; cmd_addr <= w_q[31:16]; busy <= 1'b1;
                end
            end
            if (s_axil_bvalid && s_axil_bready) s_axil_bvalid <= 1'b0;
            if (cmd_valid && cmd_ready) cmd_valid <= 1'b0;
            if (rsp_valid) begin busy <= 1'b0; last_status <= rsp_status; ndone <= ndone + 16'd1; end
            if (s_axil_arvalid && s_axil_arready) begin
                s_axil_rvalid <= 1'b1;
                case (s_axil_araddr[6:2])
                    5'h11:   s_axil_rdata <= {ndone, 8'd0, last_status, 3'd0, busy};
                    5'h12:   s_axil_rdata <= 32'h7AB1_0001;
                    default: s_axil_rdata <= 32'd0;
                endcase
            end
            if (s_axil_rvalid && s_axil_rready) s_axil_rvalid <= 1'b0;
        end
    end
endmodule
