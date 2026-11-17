// UDP command and telemetry endpoint: board top.
module v2_e_udp_endpoint_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED
);
    logic        rst;
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] win_wdata;
    /* verilator lint_on UNUSEDSIGNAL */
    logic [31:0] win_rdata;

    v2_e_udp_endpoint_rst_sync u_rst (.clk(CLK100MHZ), .arst_n(CPU_RESETN), .rst(rst));

    fpga_shell #(
        .CLKS_PER_BIT  (CLKS_PER_BIT),
        .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID     (32'h55455031),
        .BUILD_STAMP   (BUILD_STAMP)
    ) u_shell (
        .clk      (CLK100MHZ),
        .rst      (rst),
        .uart_rx  (UART_TXD_IN),
        .uart_tx  (UART_RXD_OUT),
        .win_addr (win_addr),
        .win_wr   (win_wr),
        .win_rd   (win_rd),
        .win_wdata(win_wdata),
        .win_rdata(win_rdata)
    );

    // window registers
    logic [6:0] ridx, tidx;
    logic [5:0] rlen, tlen;
    logic [31:0] rword, tword;
    logic busy, tel_on;

    wire in_wr   = win_wr && (win_addr == 7'd0);
    wire tick_wr = win_wr && (win_addr == 7'd1);
    wire take    = win_wr && (win_addr == 7'd8);

    logic        start_en, stop_en;
    logic [15:0] start_period, tel_period, tel_fcount, cmds, refused;
    logic [31:0] tel_ticks;

    v2_e_udp_endpoint_cmd u_cmd (
        .clk(CLK100MHZ), .rst(rst),
        .in_wr(in_wr), .in_byte(win_wdata[7:0]), .in_end(win_wdata[8]),
        .ridx(ridx), .rlen(rlen), .rword(rword), .busy(busy),
        .tel_on(tel_on), .tel_period(tel_period), .tel_ticks(tel_ticks), .tel_fcount(tel_fcount),
        .start_en(start_en), .start_period(start_period), .stop_en(stop_en),
        .cmds(cmds), .refused(refused)
    );

    v2_e_udp_endpoint_tel u_tel (
        .clk(CLK100MHZ), .rst(rst),
        .tick_wr(tick_wr), .tick_n(win_wdata[7:0]), .take(take),
        .start_en(start_en), .start_period(start_period), .stop_en(stop_en),
        .cmds(cmds), .refused(refused), .tidx(tidx),
        .tel_on(tel_on), .period(tel_period), .ticks(tel_ticks), .fcount(tel_fcount),
        .tlen(tlen), .tword(tword)
    );

    always_ff @(posedge CLK100MHZ) begin
        if (rst) begin
            ridx      <= 7'd0;
            tidx      <= 7'd0;
            win_rdata <= 32'd0;
        end else begin
            if (win_wr && win_addr == 7'd3) ridx <= win_wdata[6:0];
            if (win_wr && win_addr == 7'd6) tidx <= win_wdata[6:0];
            if (win_rd) begin
                case (win_addr)
                    7'd2:    win_rdata <= {26'd0, rlen};
                    7'd3:    win_rdata <= {25'd0, ridx};
                    7'd4:    win_rdata <= rword;
                    7'd5:    win_rdata <= {26'd0, tlen};
                    7'd6:    win_rdata <= {25'd0, tidx};
                    7'd7:    win_rdata <= tword;
                    7'd9:    win_rdata <= {30'd0, busy, tel_on};
                    default: win_rdata <= 32'd0;
                endcase
            end
        end
    end

    assign LED = cmds;
endmodule
