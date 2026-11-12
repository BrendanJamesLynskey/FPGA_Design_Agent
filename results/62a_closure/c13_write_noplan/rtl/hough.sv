module hough #(
    parameter int NT = 16,
    parameter int NR = 96,
    parameter int ROFF = 48
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        pt_valid,
    input  logic [7:0]  pt_x,
    input  logic [7:0]  pt_y,
    output logic        busy,
    input  logic        clear,
    input  logic [3:0]  rd_theta,
    input  logic [6:0]  rd_rho,
    output logic [15:0] rd_cnt
);

    logic [10:0] accum [0:NT*NR-1];

    logic [4:0] point_x;
    logic [4:0] point_y;
    logic [3:0] direction;

    logic signed [8:0] ct;
    logic signed [8:0] st;
    logic signed [15:0] x_term;
    logic signed [15:0] y_term;
    logic signed [15:0] projection_sum;
    logic signed [15:0] rho_rounded;
    integer signed bin_index;
    integer signed update_index;
    integer signed read_index;
    integer i;

    function automatic logic signed [8:0] coeff_ct(input logic [3:0] idx);
        begin
            case (idx)
                4'd0:  coeff_ct =  9'sd128;
                4'd1:  coeff_ct =  9'sd126;
                4'd2:  coeff_ct =  9'sd118;
                4'd3:  coeff_ct =  9'sd106;
                4'd4:  coeff_ct =   9'sd91;
                4'd5:  coeff_ct =   9'sd71;
                4'd6:  coeff_ct =   9'sd49;
                4'd7:  coeff_ct =   9'sd25;
                4'd8:  coeff_ct =    9'sd0;
                4'd9:  coeff_ct =  -9'sd25;
                4'd10: coeff_ct =  -9'sd49;
                4'd11: coeff_ct =  -9'sd71;
                4'd12: coeff_ct =  -9'sd91;
                4'd13: coeff_ct = -9'sd106;
                4'd14: coeff_ct = -9'sd118;
                4'd15: coeff_ct = -9'sd126;
                default: coeff_ct = 9'sd0;
            endcase
        end
    endfunction

    function automatic logic signed [8:0] coeff_st(input logic [3:0] idx);
        begin
            case (idx)
                4'd0:  coeff_st =   9'sd0;
                4'd1:  coeff_st =  9'sd25;
                4'd2:  coeff_st =  9'sd49;
                4'd3:  coeff_st =  9'sd71;
                4'd4:  coeff_st =  9'sd91;
                4'd5:  coeff_st = 9'sd106;
                4'd6:  coeff_st = 9'sd118;
                4'd7:  coeff_st = 9'sd126;
                4'd8:  coeff_st = 9'sd128;
                4'd9:  coeff_st = 9'sd126;
                4'd10: coeff_st = 9'sd118;
                4'd11: coeff_st = 9'sd106;
                4'd12: coeff_st =  9'sd91;
                4'd13: coeff_st =  9'sd71;
                4'd14: coeff_st =  9'sd49;
                4'd15: coeff_st =  9'sd25;
                default: coeff_st = 9'sd0;
            endcase
        end
    endfunction

    always_comb begin
        ct = coeff_ct(direction);
        st = coeff_st(direction);

        x_term = $signed({1'b0, point_x}) * ct;
        y_term = $signed({1'b0, point_y}) * st;
        projection_sum = x_term + y_term;
        rho_rounded = (projection_sum + 16'sd64) >>> 7;
        bin_index = $signed(rho_rounded) + ROFF;
        update_index = (direction * NR) + bin_index;

        read_index = (rd_theta * NR) + rd_rho;
        rd_cnt = 16'd0;
        if ((rd_rho < NR) && (read_index >= 0) &&
            (read_index < (NT * NR)))
            rd_cnt = {5'd0, accum[read_index]};
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            busy     <= 1'b0;
            point_x  <= 5'd0;
            point_y  <= 5'd0;
            direction <= 4'd0;
            for (i = 0; i < NT*NR; i = i + 1)
                accum[i] <= 11'd0;
        end else if (busy) begin
            if ((bin_index >= 0) && (bin_index < NR) &&
                (update_index >= 0) && (update_index < (NT * NR))) begin
                if (accum[update_index] != 11'h7ff)
                    accum[update_index] <= accum[update_index] + 11'd1;
            end

            if (direction == 4'd15) begin
                busy <= 1'b0;
            end else begin
                direction <= direction + 4'd1;
            end
        end else if (clear) begin
            for (i = 0; i < NT*NR; i = i + 1)
                accum[i] <= 11'd0;
        end else if (pt_valid) begin
            point_x  <= pt_x[4:0];
            point_y  <= pt_y[4:0];
            direction <= 4'd0;
            busy <= 1'b1;
        end
    end

endmodule
