// Pacer core: registers behind the shell window, tick generator, period counter, pending frame, totals.
module v2_e_tlm_pacer_core #(
    parameter int PERIOD_MIN   = 4,
    parameter int PERIOD_RESET = 100
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic [15:0] frames_o
);
    localparam logic [15:0] PMIN = 16'(PERIOD_MIN);

    logic        enable, pending, take_q;
    logic [15:0] req, eff, cnt, frames, overruns;
    logic [7:0]  tick_left;

    logic wr_ctrl, wr_req, wr_tick, wr_take;
    assign wr_ctrl = win_wr && (win_addr == 7'd0);
    assign wr_req  = win_wr && (win_addr == 7'd1);
    assign wr_tick = win_wr && (win_addr == 7'd3);
    assign wr_take = win_wr && (win_addr == 7'd4);

    logic        tick;
    logic [15:0] req_eff, cnt_next;
    logic        due, pend_after_take;
    assign tick            = (tick_left != 8'd0);
    assign req_eff         = (req < PMIN) ? PMIN : req;
    assign cnt_next        = cnt + 16'd1;
    assign due             = enable && tick && (cnt_next >= eff);
    assign pend_after_take = pending && !take_q;

    always_ff @(posedge clk) begin
        if (rst) begin
            enable    <= 1'b0;
            req       <= 16'(PERIOD_RESET);
            eff       <= (16'(PERIOD_RESET) < PMIN) ? PMIN : 16'(PERIOD_RESET);
            pending   <= 1'b0;
            take_q    <= 1'b0;
            frames    <= 16'd0;
            overruns  <= 16'd0;
            cnt       <= 16'd0;
            tick_left <= 8'd0;
        end else begin
            take_q <= wr_take;

            if (wr_tick)      tick_left <= win_wdata[7:0];
            else if (tick)    tick_left <= tick_left - 8'd1;

            if (wr_req) req <= win_wdata[15:0];

            // default: apply the take first
            pending <= pend_after_take;

            if (enable && tick) begin
                if (due) begin
                    cnt <= 16'd0;
                    eff <= req_eff;
                    if (pend_after_take) overruns <= overruns + 16'd1;
                    else begin
                        pending <= 1'b1;
                        frames  <= frames + 16'd1;
                    end
                end else begin
                    cnt <= cnt_next;
                end
            end

            if (wr_ctrl) begin
                if (win_wdata[0] && !enable) begin
                    enable <= 1'b1;
                    cnt    <= 16'd0;
                    eff    <= req_eff;
                end else if (!win_wdata[0] && enable) begin
                    enable  <= 1'b0;
                    cnt     <= 16'd0;
                    pending <= 1'b0;
                end
            end
        end
    end

    always_ff @(posedge clk) begin
        if (win_rd) begin
            case (win_addr)
                7'd0:    win_rdata <= {31'd0, enable};
                7'd1:    win_rdata <= {16'd0, req};
                7'd2:    win_rdata <= {16'd0, eff};
                7'd5:    win_rdata <= {30'd0, enable, pending};
                7'd6:    win_rdata <= {16'd0, frames};
                7'd7:    win_rdata <= {16'd0, overruns};
                7'd8:    win_rdata <= {16'd0, cnt};
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    assign frames_o = frames;
endmodule
