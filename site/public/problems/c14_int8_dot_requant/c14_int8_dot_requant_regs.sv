// c14_int8_dot_requant_regs.sv: the shell window of course task c14_int8_dot_requant.
module c14_int8_dot_requant_regs (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    logic [63:0]        a_r, w_r;
    logic [31:0]        bias_r, acc;
    logic [15:0]        mult_r;
    logic [4:0]         shift_r;
    logic               relu_r, go, ov, vld;
    logic signed [7:0]  y;
    logic [31:0]        acc_s;

    assign led = {15'd0, vld};

    dot_requant #(.N(8)) u_core (.clk(clk), .rst_n(!rst), .in_valid(go), .a(a_r), .w(w_r), .bias(bias_r),
                                 .mult(mult_r), .shift(shift_r), .relu(relu_r), .out_valid(ov), .y(y), .acc(acc_s));

    always_ff @(posedge clk) begin
        go <= 1'b0;
        if (ov) vld <= 1'b1;
        if (win_wr) begin
            case (win_addr)
                7'd0: a_r[31:0]   <= win_wdata;
                7'd1: a_r[63:32]  <= win_wdata;
                7'd2: w_r[31:0]   <= win_wdata;
                7'd3: w_r[63:32]  <= win_wdata;
                7'd4: bias_r      <= win_wdata;
                7'd5: mult_r      <= win_wdata[15:0];
                7'd6: begin shift_r <= win_wdata[4:0]; relu_r <= win_wdata[8]; end
                7'd7: begin go <= 1'b1; vld <= 1'b0; end
                default: ;
            endcase
        end
        win_rdata <= 32'd0;
        if (win_rd) begin
            case (win_addr)
                7'd0:  win_rdata <= a_r[31:0];
                7'd1:  win_rdata <= a_r[63:32];
                7'd2:  win_rdata <= w_r[31:0];
                7'd3:  win_rdata <= w_r[63:32];
                7'd4:  win_rdata <= bias_r;
                7'd5:  win_rdata <= {16'd0, mult_r};
                7'd6:  win_rdata <= {23'd0, relu_r, 3'd0, shift_r};
                7'd8:  win_rdata <= vld ? {24'd0, y} : 32'd0;
                7'd9:  win_rdata <= vld ? acc_s : 32'd0;
                7'd10: win_rdata <= {31'd0, vld};
                default: ;
            endcase
        end
        if (rst) begin
            a_r <= '0; w_r <= '0; bias_r <= '0; mult_r <= '0; shift_r <= 5'd1; relu_r <= 1'b0;
            go <= 1'b0; vld <= 1'b0; win_rdata <= 32'd0;
        end
    end
endmodule
