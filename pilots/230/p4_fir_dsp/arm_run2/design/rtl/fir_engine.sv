// Datapath run control in clk_dp: reads the input FIFO, feeds fir_filter, writes the output FIFO.
module fir_engine (
    input  logic        clk,
    input  logic        rst,          // active high, synchronous to clk
    input  logic        clr_p,        // CLEAR pulse
    input  logic        run_p,        // RUN pulse
    input  logic        in_empty,
    input  logic [15:0] in_dout,
    output logic        in_rd_en,
    input  logic [11:0] out_wr_cnt,
    output logic        out_wr_en,
    output logic [15:0] out_din,
    output logic        out_rst,      // reset for the output FIFO (stretched CLEAR or rst)
    output logic        busy,         // run in progress plus a short tail so the counters have settled in clk25
    output logic [31:0] sat_cnt,
    output logic [31:0] done_cnt
);
    logic [5:0] clr_cnt = 6'd0;
    logic       clr_act;
    assign clr_act = (clr_cnt != 6'd0);
    assign out_rst = clr_act | rst;

    always_ff @(posedge clk) begin
        if (rst)          clr_cnt <= 6'd0;
        else if (clr_p)   clr_cnt <= 6'd63;
        else if (clr_act) clr_cnt <= clr_cnt - 6'd1;
    end

    logic        run_i = 1'b0;
    logic [8:0]  tail = 9'd0;
    logic [5:0]  infl = 6'd0;
    logic [7:0]  ov_d = 8'd0;
    logic [3:0]  hold = 4'd0;
    logic        room, issue;
    logic        f_valid, f_sat;
    logic [15:0] f_y;

    assign busy = run_i | (tail != 9'd0);
    assign room  = ({1'b0, out_wr_cnt} + {6'd0, infl}) < 13'd1024;
    assign issue = run_i && !in_empty && room && !clr_act && (hold == 4'd0);
    assign in_rd_en = issue;

    always_ff @(posedge clk) begin
        if (rst || clr_act) begin
            run_i <= 1'b0; infl <= 6'd0; ov_d <= 8'd0; hold <= 4'd0; tail <= 9'd0;
        end else begin
            ov_d <= {ov_d[6:0], f_valid};
            infl <= infl + {5'd0, issue} - {5'd0, ov_d[7]};
            if (tail != 9'd0) tail <= tail - 9'd1;
            if (!busy) begin
                if (run_p) begin run_i <= 1'b1; hold <= 4'd15; end
            end else if (run_i) begin
                // hold lets the input FIFO empty flag settle before the run is judged
                if (hold != 4'd0) hold <= hold - 4'd1;
                else if ((in_empty || !room) && infl == 6'd0 && !issue) begin
                    run_i <= 1'b0; tail <= 9'd300;
                end
            end
        end
    end

    fir_filter u_filter (
        .clk(clk), .clr(clr_act | rst), .in_valid(issue), .in_x(in_dout),
        .out_valid(f_valid), .out_y(f_y), .out_sat(f_sat));

    assign out_wr_en = f_valid;
    assign out_din   = f_y;

    always_ff @(posedge clk) begin
        if (rst || clr_act) begin sat_cnt <= 32'd0; done_cnt <= 32'd0; end
        else if (f_valid) begin
            done_cnt <= done_cnt + 32'd1;
            sat_cnt  <= sat_cnt + {31'd0, f_sat};
        end
    end
endmodule
