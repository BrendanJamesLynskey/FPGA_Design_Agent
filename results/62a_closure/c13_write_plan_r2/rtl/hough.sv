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

    localparam int DEPTH  = NT * NR;
    localparam int ADDR_W = $clog2(DEPTH);

    (* ram_style = "block" *) logic [10:0] mem [0:DEPTH-1];

    logic [4:0] point_x, point_y;
    logic [4:0] issue_index;
    logic [ADDR_W-1:0] clear_index;
    logic clear_active, clear_command;

    logic signed [7:0] x_operand, y_operand;
    logic signed [7:0] ct_operand, st_operand;
    logic signed [15:0] x_product_m, y_product_m;
    logic signed [15:0] x_product_p, y_product_p;

    logic signed [16:0] projection_sum;
    logic signed [16:0] rounded_sum;
    logic signed [10:0] rho_calc;
    logic signed [10:0] bin_calc;
    logic [ADDR_W-1:0] address_calc;
    logic [ADDR_W-1:0] addr5, addr6;

    logic [3:0] dir1, dir2, dir3, dir4;
    logic last1, last2, last3, last4, last5, last6;
    logic v1, v2, v3, v4, v5, v6;

    logic [10:0] mem_read_q;
    logic readback_sel_d;
    logic [10:0] rd_count_q;

    logic mem_we;
    logic [ADDR_W-1:0] mem_waddr;
    logic [10:0] mem_wdata;
    logic [ADDR_W-1:0] rd_addr_calc;

    integer init_i;

    function automatic logic signed [7:0] cos_coeff(input logic [3:0] k);
        case (k)
            4'd0:  cos_coeff =  8'sd128;
            4'd1:  cos_coeff =  8'sd126;
            4'd2:  cos_coeff =  8'sd118;
            4'd3:  cos_coeff =  8'sd106;
            4'd4:  cos_coeff =  8'sd91;
            4'd5:  cos_coeff =  8'sd71;
            4'd6:  cos_coeff =  8'sd49;
            4'd7:  cos_coeff =  8'sd25;
            4'd8:  cos_coeff =  8'sd0;
            4'd9:  cos_coeff = -8'sd25;
            4'd10: cos_coeff = -8'sd49;
            4'd11: cos_coeff = -8'sd71;
            4'd12: cos_coeff = -8'sd91;
            4'd13: cos_coeff = -8'sd106;
            4'd14: cos_coeff = -8'sd118;
            default: cos_coeff = -8'sd126;
        endcase
    endfunction

    function automatic logic signed [7:0] sin_coeff(input logic [3:0] k);
        case (k)
            4'd0:  sin_coeff =  8'sd0;
            4'd1:  sin_coeff =  8'sd25;
            4'd2:  sin_coeff =  8'sd49;
            4'd3:  sin_coeff =  8'sd71;
            4'd4:  sin_coeff =  8'sd91;
            4'd5:  sin_coeff =  8'sd106;
            4'd6:  sin_coeff =  8'sd118;
            4'd7:  sin_coeff =  8'sd126;
            4'd8:  sin_coeff =  8'sd128;
            4'd9:  sin_coeff =  8'sd126;
            4'd10: sin_coeff =  8'sd118;
            4'd11: sin_coeff =  8'sd106;
            4'd12: sin_coeff =  8'sd91;
            4'd13: sin_coeff =  8'sd71;
            4'd14: sin_coeff =  8'sd49;
            default: sin_coeff =  8'sd25;
        endcase
    endfunction

    initial begin
        for (init_i = 0; init_i < DEPTH; init_i = init_i + 1)
            mem[init_i] = 11'd0;
    end

    wire issue_valid = busy && !clear_active && (issue_index < 5'd16);
    wire signed [7:0] issue_ct = cos_coeff(issue_index[3:0]);
    wire signed [7:0] issue_st = sin_coeff(issue_index[3:0]);

    // Operand, multiplier, and DSP output registers are deliberately unreset
    // so Vivado can map the two pipelined multiplies into DSP48E1 slices.
    always_ff @(posedge clk) begin
        x_operand <= $signed({3'b000, point_x});
        y_operand <= $signed({3'b000, point_y});
        ct_operand <= issue_ct;
        st_operand <= issue_st;

        x_product_m <= x_operand * ct_operand;
        y_product_m <= y_operand * st_operand;

        x_product_p <= x_product_m;
        y_product_p <= y_product_m;

        projection_sum <=
            $signed({x_product_p[15], x_product_p}) +
            $signed({y_product_p[15], y_product_p});
    end

    always_comb begin
        rounded_sum = projection_sum + 17'sd64;
        rho_calc = rounded_sum >>> 7;
        bin_calc = rho_calc + $signed(ROFF);
        address_calc = (dir4 * NR) + bin_calc;
    end

    always_comb begin
        rd_addr_calc = (rd_theta * NR) + rd_rho;

        mem_we = 1'b0;
        mem_waddr = '0;
        mem_wdata = '0;

        if (clear_active) begin
            mem_we = 1'b1;
            mem_waddr = clear_index;
            mem_wdata = 11'd0;
        end else if (v6) begin
            mem_we = 1'b1;
            mem_waddr = addr6;
            mem_wdata = (mem_read_q == 11'h7ff)
                      ? 11'h7ff : (mem_read_q + 11'd1);
        end
    end

    // One synchronous read port is shared between accumulator updates and
    // register readback; the independent write port supports one update/cycle.
    always_ff @(posedge clk) begin
        if (v5)
            mem_read_q <= mem[addr5];
        else if (rd_rho < NR)
            mem_read_q <= mem[rd_addr_calc];
        else
            mem_read_q <= 11'd0;
    end

    always_ff @(posedge clk) begin
        if (mem_we)
            mem[mem_waddr] <= mem_wdata;
    end

    assign rd_cnt = {5'b0, rd_count_q};

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_count_q <= 11'd0;
            readback_sel_d <= 1'b0;
        end else begin
            readback_sel_d <= !v5 && (rd_rho < NR);
            if (readback_sel_d)
                rd_count_q <= mem_read_q;
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            busy          <= 1'b0;
            point_x       <= 5'd0;
            point_y       <= 5'd0;
            issue_index   <= 5'd0;
            clear_index   <= '0;
            clear_active  <= 1'b1;
            clear_command <= 1'b0;

            v1 <= 1'b0;
            v2 <= 1'b0;
            v3 <= 1'b0;
            v4 <= 1'b0;
            v5 <= 1'b0;
            v6 <= 1'b0;
            dir1 <= '0;
            dir2 <= '0;
            dir3 <= '0;
            dir4 <= '0;
            last1 <= 1'b0;
            last2 <= 1'b0;
            last3 <= 1'b0;
            last4 <= 1'b0;
            last5 <= 1'b0;
            last6 <= 1'b0;
            addr5 <= '0;
            addr6 <= '0;
        end else begin
            v1 <= issue_valid;
            v2 <= v1;
            v3 <= v2;
            v4 <= v3;
            v5 <= v4;
            v6 <= v5;

            if (issue_valid) begin
                dir1 <= issue_index[3:0];
                last1 <= (issue_index == 5'd15);
            end
            dir2 <= dir1;
            dir3 <= dir2;
            dir4 <= dir3;

            last2 <= last1;
            last3 <= last2;
            last4 <= last3;
            last5 <= last4;
            last6 <= last5;

            if (v4)
                addr5 <= address_calc;
            if (v5)
                addr6 <= addr5;

            if (clear_active) begin
                if (clear_index == DEPTH-1) begin
                    clear_active <= 1'b0;
                    clear_index <= '0;
                    if (clear_command) begin
                        clear_command <= 1'b0;
                        busy <= 1'b0;
                    end
                end else begin
                    clear_index <= clear_index + 1'b1;
                end
            end else if (busy) begin
                if (issue_valid) begin
                    if (issue_index == 5'd15)
                        issue_index <= 5'd16;
                    else
                        issue_index <= issue_index + 1'b1;
                end

                if (v6 && last6)
                    busy <= 1'b0;
            end else if (clear) begin
                clear_active <= 1'b1;
                clear_command <= 1'b1;
                clear_index <= '0;
                busy <= 1'b1;
            end else if (pt_valid) begin
                point_x <= pt_x[4:0];
                point_y <= pt_y[4:0];
                issue_index <= 5'd0;
                busy <= 1'b1;
            end
        end
    end

endmodule
