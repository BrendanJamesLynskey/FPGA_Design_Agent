// tlm_pacer_core: register window, tick burst generator, period counter, frame hold.
module tlm_pacer_core #(
    parameter int PERIOD_MIN   = 4,
    parameter int PERIOD_RESET = 100
) (
    input  logic        clk,
    input  logic        rst,        // synchronous, active high
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

    logic        en;
    logic [15:0] req, eff, cnt, frames, overruns;
    logic        waiting;
    logic [7:0]  rem;

    wire tick     = (rem != 8'd0);
    wire wr_ctrl  = win_wr && (win_addr == 7'd0);
    wire wr_req   = win_wr && (win_addr == 7'd1);
    wire wr_tick  = win_wr && (win_addr == 7'd3);
    wire wr_take  = win_wr && (win_addr == 7'd4);

    wire [15:0] req_eff = (req < PMIN) ? PMIN : req;
    wire        en_rise = wr_ctrl && win_wdata[0] && !en;
    wire        en_fall = wr_ctrl && !win_wdata[0] && en;

    wire        counting = tick && en && !wr_ctrl;
    wire        wrap     = counting && ((cnt + 16'd1) >= eff);

    always_ff @(posedge clk) begin
        if (rst) begin
            en       <= 1'b0;
            req      <= 16'(PERIOD_RESET);
            eff      <= 16'(PERIOD_RESET);
            cnt      <= 16'd0;
            waiting  <= 1'b0;
            frames   <= 16'd0;
            overruns <= 16'd0;
            rem      <= 8'd0;
        end else begin
            if (wr_tick)       rem <= win_wdata[7:0];
            else if (tick)     rem <= rem - 8'd1;

            if (wr_req) req <= win_wdata[15:0];

            if (wr_ctrl) en <= win_wdata[0];

            if (en_rise) begin
                cnt <= 16'd0;
                eff <= req_eff;
            end else if (en_fall) begin
                cnt     <= 16'd0;
                waiting <= 1'b0;
            end else begin
                if (counting) begin
                    if (wrap) begin
                        cnt <= 16'd0;
                        eff <= req_eff;
                    end else begin
                        cnt <= cnt + 16'd1;
                    end
                end
                if (wrap) begin
                    if (waiting && !wr_take) overruns <= overruns + 16'd1;
                    else begin
                        waiting <= 1'b1;
                        frames  <= frames + 16'd1;
                    end
                end else if (wr_take) begin
                    waiting <= 1'b0;
                end
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= 32'd0;
        else if (win_rd) begin
            case (win_addr)
                7'd0:    win_rdata <= {31'd0, en};
                7'd1:    win_rdata <= {16'd0, req};
                7'd2:    win_rdata <= {16'd0, eff};
                7'd5:    win_rdata <= {30'd0, en, waiting};
                7'd6:    win_rdata <= {16'd0, frames};
                7'd7:    win_rdata <= {16'd0, overruns};
                7'd8:    win_rdata <= {16'd0, cnt};
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    assign frames_o = frames;
endmodule
