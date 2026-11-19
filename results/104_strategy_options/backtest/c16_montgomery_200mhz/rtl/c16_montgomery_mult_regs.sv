// c16_montgomery_mult_regs.sv: the shell window of course task c16_montgomery_mult.
module c16_montgomery_mult_regs (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    logic [63:0] a_r, b_r, n_r, r_w;
    logic        st, busy, done, run, got, dn;
    logic [7:0]  clk_cnt, clocks;

    assign led = {14'd0, busy, dn};

    montgomery #(.W(64)) u_core (.clk(clk), .rst_n(!rst), .start(st), .a(a_r), .b(b_r), .n(n_r), .busy(busy), .done(done), .r(r_w));

    always_ff @(posedge clk) begin
        st <= 1'b0;
        if (win_wr) begin
            case (win_addr)
                7'd0: a_r[31:0]  <= win_wdata;
                7'd1: a_r[63:32] <= win_wdata;
                7'd2: b_r[31:0]  <= win_wdata;
                7'd3: b_r[63:32] <= win_wdata;
                7'd4: n_r[31:0]  <= win_wdata;
                7'd5: n_r[63:32] <= win_wdata;
                7'd6: begin st <= 1'b1; dn <= 1'b0; end
                default: ;
            endcase
        end
        if (st) begin run <= 1'b1; clk_cnt <= 8'd1; end
        else if (run) clk_cnt <= clk_cnt + 8'd1;
        if (done) begin dn <= 1'b1; run <= 1'b0; clocks <= clk_cnt; end
        win_rdata <= 32'd0;
        if (win_rd) begin
            case (win_addr)
                7'd0: win_rdata <= a_r[31:0];
                7'd1: win_rdata <= a_r[63:32];
                7'd2: win_rdata <= b_r[31:0];
                7'd3: win_rdata <= b_r[63:32];
                7'd4: win_rdata <= n_r[31:0];
                7'd5: win_rdata <= n_r[63:32];
                7'd7: win_rdata <= {30'd0, busy, dn};
                7'd8: win_rdata <= dn ? r_w[31:0] : 32'd0;
                7'd9: win_rdata <= dn ? r_w[63:32] : 32'd0;
                7'd10: win_rdata <= {24'd0, clocks};
                default: ;
            endcase
        end
        if (rst) begin
            a_r <= '0; b_r <= '0; n_r <= '0; st <= 1'b0; run <= 1'b0; dn <= 1'b0; clk_cnt <= '0; clocks <= '0; win_rdata <= 32'd0;
        end
    end
endmodule
