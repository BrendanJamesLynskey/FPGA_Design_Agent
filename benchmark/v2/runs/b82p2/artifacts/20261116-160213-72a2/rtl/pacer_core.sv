module pacer_core #(
    parameter int PERIOD_MIN   = 4,
    parameter int PERIOD_RESET = 100
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [15:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic [15:0] frames_o
);
    localparam logic [15:0] PMIN = 16'(PERIOD_MIN);

    logic        en, waiting;
    logic [15:0] req, eff, cnt, frames, overruns;
    logic [7:0]  burst;

    logic wr_ctrl, wr_req, wr_tick, wr_take;
    assign wr_ctrl = win_wr && (win_addr == 7'd0);
    assign wr_req  = win_wr && (win_addr == 7'd1);
    assign wr_tick = win_wr && (win_addr == 7'd3);
    assign wr_take = win_wr && (win_addr == 7'd4);

    logic [15:0] req_clamped;
    assign req_clamped = (req < PMIN) ? PMIN : req;

    logic tick, due;
    assign tick = (burst != 8'd0);
    assign due  = tick && en && ((cnt + 16'd1) == eff);

    assign frames_o = frames;

    always_ff @(posedge clk) begin
        if (rst) begin
            en       <= 1'b0;
            req      <= 16'(PERIOD_RESET);
            eff      <= 16'(PERIOD_RESET);
            waiting  <= 1'b0;
            frames   <= 16'd0;
            overruns <= 16'd0;
            cnt      <= 16'd0;
            burst    <= 8'd0;
        end else begin
            // tick generator: n ticks on the n clocks after the write
            if (wr_tick)    burst <= win_wdata[7:0];
            else if (tick)  burst <= burst - 8'd1;

            if (wr_req) req <= win_wdata;

            // counting
            if (tick && en) begin
                if (due) begin
                    cnt <= 16'd0;
                    eff <= req_clamped;
                end else begin
                    cnt <= cnt + 16'd1;
                end
            end

            // frame hold
            if (due) begin
                if (!waiting || wr_take) frames <= frames + 16'd1;
                else                     overruns <= overruns + 16'd1;
                waiting <= 1'b1;
            end else if (wr_take) begin
                waiting <= 1'b0;
            end

            // enable (last: overrides the above)
            if (wr_ctrl) begin
                en <= win_wdata[0];
                if (win_wdata[0] && !en) begin
                    cnt <= 16'd0;
                    eff <= req_clamped;
                end
                if (!win_wdata[0]) waiting <= 1'b0;
            end
        end
    end

    // read path, registered
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
endmodule
