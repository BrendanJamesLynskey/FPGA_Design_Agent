// v2_e_udp_endpoint_top: UDP-style command and telemetry endpoint behind the test shell.
module v2_e_udp_endpoint_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100000000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED
);
    localparam logic [31:0] ID_WORD = 32'h55445031;

    logic rst;
    reset_sync u_rst (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    // ---------------------------------------------------------------- shell
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] win_wdata;   // only the low 9 bits carry packet or index data
    /* verilator lint_on UNUSEDSIGNAL */
    logic [31:0] win_rdata;

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(ID_WORD), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    // ---------------------------------------------------------------- window registers
    logic [6:0] ridx, tidx;
    logic [7:0] pend;
    wire        in_wr = win_wr && (win_addr == 7'd0);
    wire        take  = win_wr && (win_addr == 7'd8);
    wire        tick  = (pend != 8'd0);

    always_ff @(posedge CLK100MHZ) begin
        if (rst) begin
            ridx <= 7'd0;
            tidx <= 7'd0;
            pend <= 8'd0;
        end else begin
            if (tick) pend <= pend - 8'd1;
            if (win_wr) begin
                case (win_addr)
                    7'd1:    pend <= win_wdata[7:0];
                    7'd3:    ridx <= win_wdata[6:0];
                    7'd6:    tidx <= win_wdata[6:0];
                    default: ;
                endcase
            end
        end
    end

    // ---------------------------------------------------------------- blocks
    logic        pe_busy, tel_busy, tel_on, tstart, tstop;
    logic [5:0]  rlen, tlen;
    logic [31:0] rword, tword, uptime;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] cmds, refused;   // upper halves are read inside the blocks only
    /* verilator lint_on UNUSEDSIGNAL */
    logic [15:0] period, fcount, tstart_period;

    pkt_engine #(.ID_WORD(ID_WORD)) u_pkt (
        .clk(CLK100MHZ), .rst(rst), .in_wr(in_wr), .in_data(win_wdata[8:0]), .busy(pe_busy),
        .ridx(ridx), .rlen(rlen), .rword(rword),
        .uptime(uptime), .period(period), .tel_on(tel_on), .fcount(fcount),
        .tstart(tstart), .tstart_period(tstart_period), .tstop(tstop),
        .cmds(cmds), .refused(refused));

    telemetry u_tel (
        .clk(CLK100MHZ), .rst(rst), .tick(tick), .start(tstart), .start_period(tstart_period),
        .stop(tstop), .take(take), .cmds16(cmds[15:0]), .refused16(refused[15:0]),
        .tidx(tidx), .uptime(uptime), .period(period), .tel_on(tel_on), .fcount(fcount),
        .tlen(tlen), .tword(tword), .busy(tel_busy));

    // ---------------------------------------------------------------- read mux (registered)
    always_ff @(posedge CLK100MHZ) begin
        if (win_rd) begin
            case (win_addr)
                7'd2:    win_rdata <= {26'd0, rlen};
                7'd3:    win_rdata <= {25'd0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= {26'd0, tlen};
                7'd6:    win_rdata <= {25'd0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'd0, (pe_busy | tel_busy), tel_on};
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    always_ff @(posedge CLK100MHZ) begin
        if (rst) LED <= 16'd0;
        else     LED <= cmds[15:0];
    end
endmodule
