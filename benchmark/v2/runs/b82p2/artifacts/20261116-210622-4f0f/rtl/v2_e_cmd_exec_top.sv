// Board top: reset synchroniser, UART test shell, command executor and register bank.
module v2_e_cmd_exec_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0,
    parameter logic [31:0] ID_VALUE       = 32'h55445031,
    parameter logic [31:0] PERIOD_RESET   = 32'd100,
    parameter logic [15:0] PERIOD_MIN     = 16'd4
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
    logic [31:0] win_wdata;
    logic [31:0] win_rdata;

    v2_e_cmd_exec_rst_sync u_rst (.clk(CLK100MHZ), .resetn_async(CPU_RESETN), .rst(rst));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h43585231), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    // staged command
    logic [7:0]  typ;
    logic [15:0] p0;
    logic [31:0] p1;
    logic [2:0]  code;
    logic [31:0] rdata;
    logic        tlm;
    // register bank
    logic [31:0] scratch0, scratch1, scratch2, cmds, errs, period, uptime;

    wire go   = win_wr && (win_addr == 7'd3);
    wire tick = win_wr && (win_addr == 7'd6);
    wire refu = win_wr && (win_addr == 7'd7);

    // command decode (combinational on staged values)
    logic [2:0]  c_code;
    logic [31:0] c_rd;
    logic [31:0] bank_sel;
    always_comb begin
        case (p0[2:0])
            3'd0: bank_sel = ID_VALUE;
            3'd1: bank_sel = scratch0;
            3'd2: bank_sel = scratch1;
            3'd3: bank_sel = scratch2;
            3'd4: bank_sel = cmds;
            3'd5: bank_sel = errs;
            3'd6: bank_sel = period;
            default: bank_sel = uptime;
        endcase
        c_code = 3'd0;
        c_rd   = 32'd0;
        case (typ)
            8'd1: begin
                if (p0 >= 16'd8) c_code = 3'd3;
                else c_rd = bank_sel;
            end
            8'd2: begin
                if (p0 >= 16'd8) c_code = 3'd3;
                else if (p0 == 16'd0 || p0 >= 16'd4) c_code = 3'd5;
            end
            8'd3, 8'd4, 8'd5: ;
            default: c_code = 3'd1;
        endcase
    end

    wire cmd_ok  = go && (c_code == 3'd0);
    wire cmd_bad = go && (c_code != 3'd0);

    always_ff @(posedge CLK100MHZ) begin
        if (rst) begin
            typ      <= 8'd0;
            p0       <= 16'd0;
            p1       <= 32'd0;
            code     <= 3'd0;
            rdata    <= 32'd0;
            tlm      <= 1'b0;
            scratch0 <= 32'd0;
            scratch1 <= 32'd0;
            scratch2 <= 32'd0;
            cmds     <= 32'd0;
            errs     <= 32'd0;
            period   <= PERIOD_RESET;
            uptime   <= 32'd0;
        end else begin
            if (win_wr) begin
                case (win_addr)
                    7'd0: typ <= win_wdata[7:0];
                    7'd1: p0  <= win_wdata[15:0];
                    7'd2: p1  <= win_wdata;
                    default: ;
                endcase
            end
            if (go) begin
                code  <= c_code;
                rdata <= (typ == 8'd1 && c_code == 3'd0) ? c_rd : 32'd0;
                if (c_code == 3'd0) begin
                    if (typ == 8'd2) begin
                        case (p0[1:0])
                            2'd1: scratch0 <= p1;
                            2'd2: scratch1 <= p1;
                            default: scratch2 <= p1;
                        endcase
                    end
                    if (typ == 8'd4) begin
                        if (p0 != 16'd0) period <= {16'd0, (p0 < PERIOD_MIN) ? PERIOD_MIN : p0};
                        tlm <= 1'b1;
                    end
                    if (typ == 8'd5) tlm <= 1'b0;
                end
            end
            cmds   <= cmds + {31'd0, cmd_ok};
            errs   <= errs + {31'd0, cmd_bad} + {31'd0, refu};
            uptime <= uptime + (tick ? {24'd0, win_wdata[7:0]} : 32'd0);
        end
    end

    // window read mux, registered: data valid the cycle after win_rd
    logic [31:0] rd_mux;
    always_comb begin
        rd_mux = 32'd0;
        case (win_addr)
            7'h00: rd_mux = {24'd0, typ};
            7'h01: rd_mux = {16'd0, p0};
            7'h02: rd_mux = p1;
            7'h04: rd_mux = {29'd0, code};
            7'h05: rd_mux = rdata;
            7'h08: rd_mux = {31'd0, tlm};
            7'h10: rd_mux = ID_VALUE;
            7'h11: rd_mux = scratch0;
            7'h12: rd_mux = scratch1;
            7'h13: rd_mux = scratch2;
            7'h14: rd_mux = cmds;
            7'h15: rd_mux = errs;
            7'h16: rd_mux = period;
            7'h17: rd_mux = uptime;
            default: ;
        endcase
    end

    always_ff @(posedge CLK100MHZ) begin
        if (rst) win_rdata <= 32'd0;
        else if (win_rd) win_rdata <= rd_mux;
    end

    assign LED = {cmds[7:0], errs[7:0]};
endmodule
