// P15-4 reference top: the PQ distance unit (pq_adc.sv) feeding the top-8 list (topk.sv) with the negated distance, so the smallest distance is the best score.
// Timing: pq_adc answers one clock after in_valid; topk inserts at the edge after that; done rises at that same edge for the last entry.
module pq_search (
    input  logic            clk,
    input  logic            rst_n,
    input  logic            t_we,
    input  logic [2:0]      t_m,
    input  logic [3:0]      t_k,
    input  logic [19:0]     t_data,
    input  logic            start,
    input  logic            in_valid,
    input  logic [31:0]     codes,
    input  logic            last,
    output logic            done,
    output logic [8*23-1:0] best_dist,
    output logic [8*16-1:0] best_idx,
    output logic [7:0]      best_valid
);
    logic        d_valid, last_q;
    logic [22:0] d;
    logic [15:0] cnt, idx_q;
    logic [8*24-1:0] top_score;
    pq_adc #(.M(8), .KB(4), .TW(20)) u_adc (.clk, .rst_n, .t_we, .t_m, .t_k, .t_data, .in_valid, .codes, .out_valid(d_valid), .distance(d));
    topk #(.K(8), .SW(24), .IW(16)) u_top (.clk, .rst_n, .clear(start), .in_valid(d_valid), .score(-$signed({1'b0, d})), .idx(idx_q), .top_score, .top_idx(best_idx), .top_valid(best_valid));
    always_ff @(posedge clk) begin
        if (!rst_n || start) begin
            cnt <= 16'd0;
            last_q <= 1'b0;
            done <= 1'b0;
        end else begin
            if (in_valid) cnt <= cnt + 16'd1;
            last_q <= in_valid && last;
            done <= last_q || done;
        end
        if (in_valid) idx_q <= cnt;
    end
    always_comb for (int i = 0; i < 8; i++) best_dist[i*23 +: 23] = -top_score[i*24 +: 23];
endmodule
