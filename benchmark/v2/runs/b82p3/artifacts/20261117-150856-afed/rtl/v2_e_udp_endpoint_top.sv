// v2_e_udp_endpoint_top: UDP command and telemetry endpoint behind the test shell.
module v2_e_udp_endpoint_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100000,
    parameter int          DEFAULT_PERIOD = 100,
    parameter int          MIN_PERIOD     = 4,
    parameter logic [31:0] ID_WORD        = 32'h55445031,
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
    logic [31:0] win_wdata, win_rdata;

    rst_sync u_rst (.clk(CLK100MHZ), .arst_n(CPU_RESETN), .rst(rst));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h55455031), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    logic [6:0]  ridx, tidx;
    logic [7:0]  rlen, tlen;
    logic [31:0] rword, tword, ticks;
    logic        busy, tel_on, tel_start, tel_stop;
    logic [15:0] cmds, refused, tel_period, period, fcount;

    uep_rx #(.TIMEOUT_CYCLES(TIMEOUT_CYCLES), .ID_WORD(ID_WORD)) u_rx (
        .clk(CLK100MHZ), .rst(rst),
        .win_wr(win_wr), .win_addr(win_addr), .win_wdata(win_wdata),
        .ridx(ridx), .rlen(rlen), .rword(rword), .busy(busy),
        .cmds(cmds), .refused(refused),
        .tel_start(tel_start), .tel_stop(tel_stop), .tel_period(tel_period),
        .period(period), .ticks(ticks), .tel_on(tel_on), .fcount(fcount));

    uep_telemetry #(.DEFAULT_PERIOD(DEFAULT_PERIOD), .MIN_PERIOD(MIN_PERIOD)) u_tel (
        .clk(CLK100MHZ), .rst(rst),
        .tick_wr(win_wr && win_addr == 7'd1), .tick_n(win_wdata[7:0]),
        .start_p(tel_start), .start_period(tel_period), .stop_p(tel_stop),
        .take_p(win_wr && win_addr == 7'd8),
        .tidx_wr(win_wr && win_addr == 7'd6), .tidx_d(win_wdata[6:0]),
        .cmds(cmds), .refused(refused),
        .period(period), .ticks(ticks), .tel_on(tel_on), .fcount(fcount),
        .tidx(tidx), .tlen(tlen), .tword(tword));

    always_ff @(posedge CLK100MHZ) begin
        if (rst) win_rdata <= 32'd0;
        else if (win_rd) begin
            case (win_addr)
                7'd2:    win_rdata <= {24'd0, rlen};
                7'd3:    win_rdata <= {25'd0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= {24'd0, tlen};
                7'd6:    win_rdata <= {25'd0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'd0, busy, tel_on};
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    assign LED = cmds;

    /* verilator lint_off UNUSEDSIGNAL */
    wire unused_ok = &{1'b0, refused};
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
