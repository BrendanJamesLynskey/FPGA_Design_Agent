// c15_pq_search_regs.sv: the shell window of course task c15_pq_search.
module c15_pq_search_regs (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    logic [6:0]   ta_r;
    logic [19:0]  td_r;
    logic [31:0]  cd [0:15];
    logic [4:0]   n_tot, tx_i;
    logic         txing, last_f, we, st, done, in_v, last_c;
    logic [2:0]   t_m;
    logic [3:0]   t_k;
    logic [8*23-1:0] best_dist;
    logic [8*16-1:0] best_idx;
    logic [7:0]   best_valid;

    assign t_m  = ta_r[6:4];
    assign t_k  = ta_r[3:0];
    assign in_v = txing;
    assign last_c = txing && last_f && (tx_i + 5'd1 == n_tot);
    assign led  = {14'd0, txing, done};

    pq_search u_core (.clk(clk), .rst_n(!rst), .t_we(we), .t_m(t_m), .t_k(t_k), .t_data(td_r), .start(st), .in_valid(in_v),
                      .codes(cd[tx_i[3:0]]), .last(last_c), .done(done), .best_dist(best_dist), .best_idx(best_idx),
                      .best_valid(best_valid));

    always_ff @(posedge clk) begin
        we <= 1'b0; st <= 1'b0;
        if (win_wr) begin
            case (win_addr)
                7'h00: ta_r <= win_wdata[6:0];
                7'h01: begin td_r <= win_wdata[19:0]; we <= 1'b1; end
                7'h02: st <= 1'b1;
                7'h18: begin
                    n_tot <= (win_wdata[4:0] == 5'd0) ? 5'd1 : (win_wdata[4:0] > 5'd16 ? 5'd16 : win_wdata[4:0]);
                    last_f <= win_wdata[8]; tx_i <= 5'd0; txing <= 1'b1;
                end
                default: if (win_addr >= 7'h08 && win_addr <= 7'h17) cd[4'(win_addr - 7'h08)] <= win_wdata;
            endcase
        end
        if (we) ta_r <= ta_r + 7'd1;
        if (txing) begin
            tx_i <= tx_i + 5'd1;
            if (tx_i + 5'd1 == n_tot) txing <= 1'b0;
        end
        win_rdata <= 32'd0;
        if (win_rd) begin
            if (win_addr == 7'h00) win_rdata <= {25'd0, ta_r};
            else if (win_addr >= 7'h08 && win_addr <= 7'h17) win_rdata <= cd[4'(win_addr - 7'h08)];
            else if (win_addr == 7'h19) win_rdata <= {30'd0, txing, done};
            else if (win_addr >= 7'h40 && win_addr <= 7'h47)
                win_rdata <= best_valid[win_addr[2:0]] ? {7'd0, 1'b1, 1'b0, best_dist[win_addr[2:0]*23 +: 23]} : 32'd0;
            else if (win_addr >= 7'h48 && win_addr <= 7'h4F)
                win_rdata <= best_valid[win_addr[2:0]] ? {16'd0, best_idx[win_addr[2:0]*16 +: 16]} : 32'd0;
        end
        if (rst) begin
            ta_r <= '0; td_r <= '0; n_tot <= '0; tx_i <= '0; txing <= 1'b0; last_f <= 1'b0; we <= 1'b0; st <= 1'b0; win_rdata <= 32'd0;
            for (int i = 0; i < 16; i++) cd[i] <= '0;
        end
    end
endmodule
