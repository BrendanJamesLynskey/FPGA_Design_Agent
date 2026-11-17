// v2_e_udp_endpoint_top: UDP command and telemetry endpoint behind the test shell.
module v2_e_udp_endpoint_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000_000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0,
    parameter logic [31:0] ID_WORD        = 32'h55445031
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED
);
    logic rst;
    reset_sync u_rst (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    logic [6:0]  win_addr;
    logic        win_wr;
    /* verilator lint_off UNUSEDSIGNAL */
    logic        win_rd;
    logic [31:0] win_wdata;
    /* verilator lint_on UNUSEDSIGNAL */
    logic [31:0] win_rdata;

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(ID_WORD), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    // window decode
    logic [6:0] ridx, tidx;
    logic in_wr, tick_wr, take;
    assign in_wr   = win_wr && (win_addr == 7'd0);
    assign tick_wr = win_wr && (win_addr == 7'd1);
    assign take    = win_wr && (win_addr == 7'd8);

    always_ff @(posedge CLK100MHZ) begin
        if (rst) begin
            ridx <= 7'd0;
            tidx <= 7'd0;
        end else if (win_wr) begin
            if (win_addr == 7'd3) ridx <= win_wdata[6:0];
            if (win_addr == 7'd6) tidx <= win_wdata[6:0];
        end
    end

    logic [31:0] rword, tword, ticks;
    logic [4:0]  rlen, tlen;
    logic        busy, tel_on, tel_start, tel_stop;
    logic [15:0] cmds, refd, period, fseq, start_per;

    udp_engine #(.ID_WORD(ID_WORD)) u_eng (
        .clk(CLK100MHZ), .rst(rst), .in_wr(in_wr), .in_data(win_wdata[8:0]),
        .ridx(ridx), .rword(rword), .rlen(rlen), .busy(busy),
        .cmds(cmds), .refd(refd),
        .tel_on(tel_on), .tel_period(period), .tel_ticks(ticks), .tel_fcount(fseq),
        .tel_start(tel_start), .tel_start_per(start_per), .tel_stop(tel_stop));

    udp_tlm u_tlm (
        .clk(CLK100MHZ), .rst(rst),
        .tick_wr(tick_wr), .tick_n(win_wdata[7:0]),
        .start(tel_start), .start_per(start_per), .stop(tel_stop), .take(take),
        .cmds(cmds), .refd(refd), .tidx(tidx),
        .tel_on(tel_on), .period(period), .ticks(ticks), .fseq(fseq),
        .tlen(tlen), .tword(tword));

    always_ff @(posedge CLK100MHZ) begin
        if (rst) win_rdata <= 32'h0;
        else begin
            case (win_addr)
                7'd2:    win_rdata <= {27'h0, rlen};
                7'd3:    win_rdata <= {25'h0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= {27'h0, tlen};
                7'd6:    win_rdata <= {25'h0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'h0, busy, tel_on};
                default: win_rdata <= 32'h0;
            endcase
        end
    end

    assign LED = cmds;
endmodule
