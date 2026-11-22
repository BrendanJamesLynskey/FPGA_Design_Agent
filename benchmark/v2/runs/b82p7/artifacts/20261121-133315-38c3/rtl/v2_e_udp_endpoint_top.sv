// v2_e_udp_endpoint_top.sv: UDP-style command and telemetry endpoint on the Nexys A7-100T.
// The host reaches the window registers through the test shell (UART). Window offsets:
//   0 IN (WO)  1 TICK (WO)  2 RLEN (RO)  3 RIDX (RW)  4 RWORD (RO)
//   5 TLEN (RO) 6 TIDX (RW) 7 TWORD (RO) 8 TAKE (WO)  9 STAT (RO)
module v2_e_udp_endpoint_top #(
    parameter int          CLKS_PER_BIT           = 868,
    parameter int          TIMEOUT_CYCLES         = 100000,
    parameter logic [31:0] BUILD_STAMP            = 32'h0,
    parameter logic [31:0] ID_WORD                = 32'h55445031,
    parameter int          TELEMETRY_PERIOD_RESET = 100,
    parameter int          TELEMETRY_PERIOD_MIN   = 4
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED
);
    // Shell design ID: 'UEP1' (MSB first), distinct from the ID_WORD data constant.
    localparam logic [31:0] DESIGN_ID = 32'h55455031;

    logic        rst;
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] win_wdata;   // only bits 8:0 are used (IN byte and end flag; TICK 7:0; indexes 6:0)
    /* verilator lint_on UNUSEDSIGNAL */
    logic [31:0] win_rdata;

    reset_sync u_reset_sync (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT),
        .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(DESIGN_ID),
        .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst),
        .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata)
    );

    // ---- window write decode
    logic [6:0] ridx, tidx;
    wire in_wr   = win_wr && (win_addr == 7'd0);
    wire tick_wr = win_wr && (win_addr == 7'd1);
    wire take    = win_wr && (win_addr == 7'd8);

    always_ff @(posedge CLK100MHZ) begin
        if (rst) begin
            ridx <= 7'd0;
            tidx <= 7'd0;
        end else if (win_wr) begin
            if (win_addr == 7'd3) ridx <= win_wdata[6:0];
            if (win_addr == 7'd6) tidx <= win_wdata[6:0];
        end
    end

    // ---- blocks
    logic [31:0] rword, tword, uptime;
    logic [7:0]  rlen, tlen;
    logic        busy, tel_on, cmd_start, cmd_stop;
    logic [15:0] period, fcount, cmd_period, done_cnt, refused_cnt;

    udp_core #(.ID_WORD(ID_WORD)) u_core (
        .clk(CLK100MHZ), .rst(rst),
        .in_wr(in_wr), .in_data(win_wdata[8:0]),
        .ridx(ridx), .rword(rword), .rlen(rlen), .busy(busy),
        .tel_on(tel_on), .period(period), .uptime(uptime), .fcount(fcount),
        .cmd_start(cmd_start), .cmd_period(cmd_period), .cmd_stop(cmd_stop),
        .done_cnt(done_cnt), .refused_cnt(refused_cnt)
    );

    telemetry #(
        .PERIOD_RESET(TELEMETRY_PERIOD_RESET),
        .PERIOD_MIN(TELEMETRY_PERIOD_MIN)
    ) u_tel (
        .clk(CLK100MHZ), .rst(rst),
        .tick_wr(tick_wr), .tick_n(win_wdata[7:0]), .take(take),
        .cmd_start(cmd_start), .cmd_period(cmd_period), .cmd_stop(cmd_stop),
        .done_cnt(done_cnt), .refused_cnt(refused_cnt),
        .tidx(tidx), .tword(tword), .tlen(tlen),
        .tel_on(tel_on), .period(period), .uptime(uptime), .fcount(fcount)
    );

    // ---- window read (registered: valid one cycle after win_rd)
    always_ff @(posedge CLK100MHZ) begin
        if (win_rd) begin
            case (win_addr)
                7'd2:    win_rdata <= {24'h0, rlen};
                7'd3:    win_rdata <= {25'h0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= {24'h0, tlen};
                7'd6:    win_rdata <= {25'h0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'h0, busy, tel_on};
                default: win_rdata <= 32'h0;
            endcase
        end
    end

    assign LED = done_cnt;
endmodule
