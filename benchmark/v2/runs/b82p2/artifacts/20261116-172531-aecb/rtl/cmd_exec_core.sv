// Command executor and register file behind the shell window.
module cmd_exec_core #(
    parameter logic [31:0] ID_VALUE     = 32'h55445031,
    parameter logic [31:0] PERIOD_RESET = 32'd100,
    parameter logic [15:0] PERIOD_MIN   = 16'd4
) (
    input  logic        clk,
    input  logic        rst,        // synchronous, active high
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    logic [7:0]  typ_q;
    logic [15:0] p0_q;
    logic [31:0] p1_q;
    logic [2:0]  code_q;
    logic [31:0] rdata_q;
    logic        tlm_q;
    logic [31:0] scratch0, scratch1, scratch2;
    logic [31:0] cmds_q, errs_q, period_q, uptime_q;

    logic [31:0] bank [8];
    assign bank[0] = ID_VALUE;
    assign bank[1] = scratch0;
    assign bank[2] = scratch1;
    assign bank[3] = scratch2;
    assign bank[4] = cmds_q;
    assign bank[5] = errs_q;
    assign bank[6] = period_q;
    assign bank[7] = uptime_q;

    logic go, tick_wr, ref_wr;
    assign go      = win_wr && (win_addr == 7'd3);
    assign tick_wr = win_wr && (win_addr == 7'd6);
    assign ref_wr  = win_wr && (win_addr == 7'd7);

    // command decode (combinational, applied at the clock edge of go)
    logic [2:0]  n_code;
    logic [31:0] n_data;
    logic        ok;
    logic        wr_scratch;
    logic        tlm_set, tlm_clr, period_set;
    logic [15:0] n_period;

    always_comb begin
        n_code     = 3'd0;
        n_data     = 32'd0;
        wr_scratch = 1'b0;
        tlm_set    = 1'b0;
        tlm_clr    = 1'b0;
        period_set = 1'b0;
        n_period   = (p0_q < PERIOD_MIN) ? PERIOD_MIN : p0_q;
        case (typ_q)
            8'd1: begin
                if (p0_q < 16'd8) n_data = bank[p0_q[2:0]];
                else n_code = 3'd3;
            end
            8'd2: begin
                if (p0_q >= 16'd8) n_code = 3'd3;
                else if (p0_q[2:0] == 3'd1 || p0_q[2:0] == 3'd2 || p0_q[2:0] == 3'd3) wr_scratch = 1'b1;
                else n_code = 3'd5;
            end
            8'd3: ;
            8'd4: begin
                tlm_set    = 1'b1;
                period_set = (p0_q != 16'd0);
            end
            8'd5: tlm_clr = 1'b1;
            default: n_code = 3'd1;
        endcase
        ok = (n_code == 3'd0);
    end

    // increments: at most one window write per cycle, so ERRS gets at most +1
    logic cmds_inc, errs_inc;
    assign cmds_inc = go && ok;
    assign errs_inc = (go && !ok) || ref_wr;

    always_ff @(posedge clk) begin
        if (rst) begin
            typ_q    <= 8'd0;
            p0_q     <= 16'd0;
            p1_q     <= 32'd0;
            code_q   <= 3'd0;
            rdata_q  <= 32'd0;
            tlm_q    <= 1'b0;
            scratch0 <= 32'd0;
            scratch1 <= 32'd0;
            scratch2 <= 32'd0;
            cmds_q   <= 32'd0;
            errs_q   <= 32'd0;
            period_q <= PERIOD_RESET;
            uptime_q <= 32'd0;
        end else begin
            if (win_wr) begin
                case (win_addr)
                    7'd0: typ_q <= win_wdata[7:0];
                    7'd1: p0_q  <= win_wdata[15:0];
                    7'd2: p1_q  <= win_wdata;
                    default: ;
                endcase
            end
            if (go) begin
                code_q  <= n_code;
                rdata_q <= n_data;
                if (wr_scratch) begin
                    case (p0_q[1:0])
                        2'd1: scratch0 <= p1_q;
                        2'd2: scratch1 <= p1_q;
                        default: scratch2 <= p1_q;
                    endcase
                end
                if (tlm_set) tlm_q <= 1'b1;
                if (tlm_clr) tlm_q <= 1'b0;
                if (period_set) period_q <= {16'd0, n_period};
            end
            if (cmds_inc) cmds_q <= cmds_q + 32'd1;
            if (errs_inc) errs_q <= errs_q + 32'd1;
            if (tick_wr)  uptime_q <= uptime_q + {24'd0, win_wdata[7:0]};
        end
    end

    // registered read port, due one cycle after win_rd
    always_ff @(posedge clk) begin
        if (rst) win_rdata <= 32'd0;
        else if (win_rd) begin
            if (win_addr[6:3] == 4'd2) win_rdata <= bank[win_addr[2:0]];
            else begin
                case (win_addr)
                    7'd0: win_rdata <= {24'd0, typ_q};
                    7'd1: win_rdata <= {16'd0, p0_q};
                    7'd2: win_rdata <= p1_q;
                    7'd4: win_rdata <= {29'd0, code_q};
                    7'd5: win_rdata <= rdata_q;
                    7'd8: win_rdata <= {31'd0, tlm_q};
                    default: win_rdata <= 32'd0;
                endcase
            end
        end
    end

    assign led = {cmds_q[7:0], errs_q[7:0]};
endmodule
