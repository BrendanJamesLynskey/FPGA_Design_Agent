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

    localparam integer DEPTH = NT * NR;

    function automatic logic signed [8:0] cos_coeff(input logic [3:0] k);
        case (k)
            4'd0:  cos_coeff =  9'sd128;
            4'd1:  cos_coeff =  9'sd126;
            4'd2:  cos_coeff =  9'sd118;
            4'd3:  cos_coeff =  9'sd106;
            4'd4:  cos_coeff =  9'sd91;
            4'd5:  cos_coeff =  9'sd71;
            4'd6:  cos_coeff =  9'sd49;
            4'd7:  cos_coeff =  9'sd25;
            4'd8:  cos_coeff =  9'sd0;
            4'd9:  cos_coeff = -9'sd25;
            4'd10: cos_coeff = -9'sd49;
            4'd11: cos_coeff = -9'sd71;
            4'd12: cos_coeff = -9'sd91;
            4'd13: cos_coeff = -9'sd106;
            4'd14: cos_coeff = -9'sd118;
            4'd15: cos_coeff = -9'sd126;
            default: cos_coeff = 9'sd0;
        endcase
    endfunction

    function automatic logic signed [8:0] sin_coeff(input logic [3:0] k);
        case (k)
            4'd0:  sin_coeff = 9'sd0;
            4'd1:  sin_coeff = 9'sd25;
            4'd2:  sin_coeff = 9'sd49;
            4'd3:  sin_coeff = 9'sd71;
            4'd4:  sin_coeff = 9'sd91;
            4'd5:  sin_coeff = 9'sd106;
            4'd6:  sin_coeff = 9'sd118;
            4'd7:  sin_coeff = 9'sd126;
            4'd8:  sin_coeff = 9'sd128;
            4'd9:  sin_coeff = 9'sd126;
            4'd10: sin_coeff = 9'sd118;
            4'd11: sin_coeff = 9'sd106;
            4'd12: sin_coeff = 9'sd91;
            4'd13: sin_coeff = 9'sd71;
            4'd14: sin_coeff = 9'sd49;
            4'd15: sin_coeff = 9'sd25;
            default: sin_coeff = 9'sd0;
        endcase
    endfunction

    (* ram_style = "block" *) logic [10:0] accumulator [0:DEPTH-1];
    integer init_i;

    initial begin
        for (init_i = 0; init_i < DEPTH; init_i = init_i + 1)
            accumulator[init_i] = 11'd0;
    end

    logic busy_reg;
    logic clear_active;
    logic [10:0] clear_index;

    logic feed_active;
    logic [4:0] x_hold;
    logic [4:0] y_hold;
    logic [3:0] dir_index;
    wire launch = feed_active;

    logic signed [8:0] x_operand;
    logic signed [8:0] cos_operand;
    logic signed [8:0] y_operand;
    logic signed [8:0] sin_operand;

    // DSP multiply and post-add pipeline registers; intentionally not reset.
    logic signed [17:0] cos_product;
    logic signed [17:0] sin_product;
    logic signed [17:0] cos_p;
    logic signed [17:0] sin_p;

    logic signed [18:0] projection_sum;
    logic signed [18:0] rho_value;
    logic signed [18:0] bin_value;
    logic [10:0] addr_calc;
    logic [10:0] addr5;
    logic [3:0] k1, k2, k3, k4;

    logic v1, v2, v3, v4, v5, v6;
    logic last1, last2, last3, last4, last5, last6;

    logic [10:0] mem_q;
    logic [10:0] rd_addr;

    assign busy = busy_reg;

    always_comb begin
        rho_value = projection_sum >>> 7;
        bin_value = rho_value + ROFF;
        addr_calc = (k4 * NR) + bin_value;

        if ((rd_rho < NR) && ((rd_theta * NR + rd_rho) < DEPTH))
            rd_addr = rd_theta * NR + rd_rho;
        else
            rd_addr = 11'd0;
    end

    // DSP48E1-friendly registered operands, multiply, and post-add stages.
    always_ff @(posedge clk) begin
        if (launch) begin
            x_operand   <= $signed({4'b0000, x_hold});
            cos_operand <= cos_coeff(dir_index);
            y_operand   <= $signed({4'b0000, y_hold});
            sin_operand <= sin_coeff(dir_index);
        end else begin
            x_operand   <= 9'sd0;
            cos_operand <= 9'sd0;
            y_operand   <= 9'sd0;
            sin_operand <= 9'sd0;
        end

        cos_product <= x_operand * cos_operand;
        sin_product <= y_operand * sin_operand;
        cos_p <= cos_product + 18'sd64;
        sin_p <= sin_product + 18'sd0;

        projection_sum <= {cos_p[17], cos_p} + {sin_p[17], sin_p};
        addr5 <= addr_calc;
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            busy_reg     <= 1'b0;
            clear_active <= 1'b0;
            clear_index  <= 11'd0;
            feed_active  <= 1'b0;
            x_hold       <= 5'd0;
            y_hold       <= 5'd0;
            dir_index    <= 4'd0;

            v1 <= 1'b0;
            v2 <= 1'b0;
            v3 <= 1'b0;
            v4 <= 1'b0;
            v5 <= 1'b0;
            v6 <= 1'b0;
            last1 <= 1'b0;
            last2 <= 1'b0;
            last3 <= 1'b0;
            last4 <= 1'b0;
            last5 <= 1'b0;
            last6 <= 1'b0;

            k1 <= 4'd0;
            k2 <= 4'd0;
            k3 <= 4'd0;
            k4 <= 4'd0;
            rd_cnt <= 16'd0;
        end else begin
            v1 <= launch;
            v2 <= v1;
            v3 <= v2;
            v4 <= v3;
            v5 <= v4;
            v6 <= v5;

            last1 <= launch && (dir_index == 4'd15);
            last2 <= last1;
            last3 <= last2;
            last4 <= last3;
            last5 <= last4;
            last6 <= last5;

            if (launch)
                k1 <= dir_index;
            k2 <= k1;
            k3 <= k2;
            k4 <= k3;

            if (clear_active) begin
                if (clear_index == DEPTH-1) begin
                    clear_active <= 1'b0;
                    busy_reg <= 1'b0;
                    clear_index <= 11'd0;
                end else begin
                    clear_index <= clear_index + 11'd1;
                end
            end else if (!busy_reg) begin
                if (clear) begin
                    clear_active <= 1'b1;
                    clear_index <= 11'd0;
                    busy_reg <= 1'b1;
                    feed_active <= 1'b0;
                end else if (pt_valid) begin
                    x_hold <= pt_x[4:0];
                    y_hold <= pt_y[4:0];
                    dir_index <= 4'd0;
                    feed_active <= 1'b1;
                    busy_reg <= 1'b1;
                end
            end

            if (feed_active) begin
                if (dir_index == 4'd15)
                    feed_active <= 1'b0;
                else
                    dir_index <= dir_index + 4'd1;
            end

            if (v6 && last6)
                busy_reg <= 1'b0;

            if (!busy_reg && !clear_active && !v5) begin
                if (rd_rho < NR)
                    rd_cnt <= {5'd0, mem_q};
                else
                    rd_cnt <= 16'd0;
            end
        end
    end

    // Synchronous BRAM read and single write port for clear/update operations.
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            mem_q <= 11'd0;
        end else if (clear_active) begin
            accumulator[clear_index] <= 11'd0;
            mem_q <= 11'd0;
        end else begin
            if (v6)
                accumulator[addr5] <=
                    (mem_q == 11'h7ff) ? mem_q : (mem_q + 11'd1);

            if (v5)
                mem_q <= accumulator[addr5];
            else if ((rd_rho < NR) && ((rd_theta * NR + rd_rho) < DEPTH))
                mem_q <= accumulator[rd_addr];
            else
                mem_q <= 11'd0;
        end
    end

endmodule
