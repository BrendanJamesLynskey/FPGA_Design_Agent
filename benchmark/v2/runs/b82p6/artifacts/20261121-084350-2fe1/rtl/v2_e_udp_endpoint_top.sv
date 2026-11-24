// v2_e_udp_endpoint_top: UDP command and telemetry endpoint behind the test shell register window.
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
    logic [31:0] win_wdata;  // only the low 9 bits are used by this design
    /* verilator lint_on UNUSEDSIGNAL */
    logic [31:0] win_rdata;

    reset_sync u_rst (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h55455031), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    // window decode
    wire wr_in   = win_wr && (win_addr == 7'd0);
    wire wr_tick = win_wr && (win_addr == 7'd1);
    wire wr_ridx = win_wr && (win_addr == 7'd3);
    wire wr_tidx = win_wr && (win_addr == 7'd6);
    wire wr_take = win_wr && (win_addr == 7'd8);

    logic [6:0] ridx, tidx;
    logic [7:0] tick_pend;
    wire        tick = (tick_pend != 8'd0);

    always_ff @(posedge CLK100MHZ) begin
        if (rst) begin
            ridx      <= 7'd0;
            tidx      <= 7'd0;
            tick_pend <= 8'd0;
        end else begin
            if (wr_ridx) ridx <= win_wdata[6:0];
            if (wr_tidx) tidx <= win_wdata[6:0];
            if (wr_tick)      tick_pend <= win_wdata[7:0];
            else if (tick)    tick_pend <= tick_pend - 8'd1;
        end
    end

    logic        tlm_start, tlm_set, tlm_stop, tlm_on, busy;
    logic [15:0] tlm_period, period, fseq, cmds, refused;
    logic [31:0] uptime, rword, tword;
    logic [7:0]  rlen, tlen;

    pkt_core #(.ID_WORD(32'h55445031)) u_pkt (
        .clk(CLK100MHZ), .rst(rst),
        .in_wr(wr_in), .in_data(win_wdata[8:0]),
        .tlm_on_i(tlm_on), .period_i(period), .uptime_i(uptime), .tcount_i(fseq),
        .tlm_start(tlm_start), .tlm_set(tlm_set), .tlm_period(tlm_period), .tlm_stop(tlm_stop),
        .cmds_o(cmds), .refused_o(refused),
        .ridx(ridx), .rword(rword), .rlen(rlen), .busy(busy));

    telemetry u_tlm (
        .clk(CLK100MHZ), .rst(rst),
        .tick(tick), .start(tlm_start), .set_period(tlm_set), .period_val(tlm_period),
        .stop(tlm_stop), .take(wr_take),
        .cmds(cmds), .refused(refused), .tidx(tidx),
        .on(tlm_on), .period(period), .uptime(uptime), .fseq(fseq),
        .tword(tword), .tlen(tlen));

    // readback: value due the cycle after win_rd
    always_ff @(posedge CLK100MHZ) begin
        if (rst) begin
            win_rdata <= 32'd0;
        end else if (win_rd) begin
            case (win_addr)
                7'd2:    win_rdata <= {24'd0, rlen};
                7'd3:    win_rdata <= {25'd0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= {24'd0, tlen};
                7'd6:    win_rdata <= {25'd0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'd0, busy, tlm_on};
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    assign LED = cmds;
endmodule
