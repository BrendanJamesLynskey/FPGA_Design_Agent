// Command executor and register file behind the shell window.
module v2_e_cmd_exec #(
    parameter logic [31:0] ID_VALUE     = 32'h55445031,
    parameter logic [31:0] PERIOD_RESET = 32'd100,
    parameter logic [15:0] PERIOD_MIN   = 16'd4
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    logic [7:0]  typ;
    logic [15:0] p0;
    logic [31:0] p1;
    logic [2:0]  code;
    logic [31:0] rdata;
    logic        tlm;
    logic [31:0] scratch0, scratch1, scratch2;
    logic [31:0] cmds, errs, period, uptime;

    wire wr_typ  = win_wr && (win_addr == 7'h00);
    wire wr_p0   = win_wr && (win_addr == 7'h01);
    wire wr_p1   = win_wr && (win_addr == 7'h02);
    wire go      = win_wr && (win_addr == 7'h03);
    wire wr_tick = win_wr && (win_addr == 7'h06);
    wire wr_ref  = win_wr && (win_addr == 7'h07);

    // command decode (combinational on staged registers)
    logic        reg_bad, ro_reg, ok;
    logic [2:0]  res;
    logic [31:0] rsel;
    always_comb begin
        reg_bad = (p0 >= 16'd8);
        ro_reg  = (p0 == 16'd0) || (p0 >= 16'd4 && p0 <= 16'd7);
        case (p0[2:0])
            3'd0:    rsel = ID_VALUE;
            3'd1:    rsel = scratch0;
            3'd2:    rsel = scratch1;
            3'd3:    rsel = scratch2;
            3'd4:    rsel = cmds;
            3'd5:    rsel = errs;
            3'd6:    rsel = period;
            default: rsel = uptime;
        endcase
        res = 3'd0;
        case (typ)
            8'd1:    if (reg_bad) res = 3'd3;
            8'd2:    if (reg_bad) res = 3'd3; else if (ro_reg) res = 3'd5;
            8'd3, 8'd4, 8'd5: res = 3'd0;
            default: res = 3'd1;
        endcase
        ok = (res == 3'd0);
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            typ <= 8'd0;  p0 <= 16'd0;  p1 <= 32'd0;
            code <= 3'd0; rdata <= 32'd0; tlm <= 1'b0;
            scratch0 <= 32'd0; scratch1 <= 32'd0; scratch2 <= 32'd0;
            cmds <= 32'd0; errs <= 32'd0; period <= PERIOD_RESET; uptime <= 32'd0;
        end else begin
            if (wr_typ) typ <= win_wdata[7:0];
            if (wr_p0)  p0  <= win_wdata[15:0];
            if (wr_p1)  p1  <= win_wdata;
            if (wr_tick) uptime <= uptime + {24'd0, win_wdata[7:0]};
            if (wr_ref)  errs <= errs + 32'd1;
            if (go) begin
                code  <= res;
                rdata <= (ok && typ == 8'd1) ? rsel : 32'd0;
                if (ok) cmds <= cmds + 32'd1; else errs <= errs + 32'd1;
                if (ok && typ == 8'd2) begin
                    case (p0[1:0])
                        2'd1: scratch0 <= p1;
                        2'd2: scratch1 <= p1;
                        default: scratch2 <= p1;
                    endcase
                end
                if (ok && typ == 8'd4) begin
                    tlm <= 1'b1;
                    if (p0 != 16'd0) period <= {16'd0, (p0 < PERIOD_MIN) ? PERIOD_MIN : p0};
                end
                if (ok && typ == 8'd5) tlm <= 1'b0;
            end
        end
    end

    // registered read mux, valid the cycle after win_rd
    always_ff @(posedge clk) begin
        if (rst) win_rdata <= 32'd0;
        else if (win_rd) begin
            case (win_addr)
                7'h00: win_rdata <= {24'd0, typ};
                7'h01: win_rdata <= {16'd0, p0};
                7'h02: win_rdata <= p1;
                7'h04: win_rdata <= {29'd0, code};
                7'h05: win_rdata <= rdata;
                7'h08: win_rdata <= {31'd0, tlm};
                7'h10: win_rdata <= ID_VALUE;
                7'h11: win_rdata <= scratch0;
                7'h12: win_rdata <= scratch1;
                7'h13: win_rdata <= scratch2;
                7'h14: win_rdata <= cmds;
                7'h15: win_rdata <= errs;
                7'h16: win_rdata <= period;
                7'h17: win_rdata <= uptime;
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    always_ff @(posedge clk) begin
        if (rst) led <= 16'd0;
        else led <= {cmds[7:0], errs[7:0]};
    end
endmodule
