// P15-4 reference RTL: a copy of solutions/p15l03_topk/topk.sv (course exercise p15l03_topk).
// Part 15 lesson 3 exercise: a streaming top-K list (K = 8 by default), one candidate per clock, a deterministic tie rule.
//
// Candidates arrive as (score, idx): score signed SW bits, idx IW bits (unique per stream). The list holds the K best seen so far, best first:
//   "a is better than b"  <=>  a.score > b.score,  or  a.score == b.score and a.idx < b.idx.        (so equal scores: the smaller index wins)
// clear = 1 (one clock) empties the list (it wins over in_valid in the same clock). With in_valid high the candidate is inserted at the next clock edge: it takes the first slot
// whose content it beats (an empty slot is beaten by anything), the slots below shift down by one and the old last slot falls off. rst_n (synchronous, active low) empties the list.
// Outputs (registers, valid the clock after the edge that inserted): slot 0 is the best; top_valid[i] says slot i holds a candidate; slot i's score is
// top_score[i*SW +: SW] and its index top_idx[i*IW +: IW]. Slots with top_valid = 0 are don't-care.
module topk #(
    parameter int K  = 8,
    parameter int SW = 24,
    parameter int IW = 16
) (
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  clear,
    input  logic                  in_valid,
    input  logic signed [SW-1:0]  score,
    input  logic [IW-1:0]         idx,
    output logic [K*SW-1:0]       top_score,
    output logic [K*IW-1:0]       top_idx,
    output logic [K-1:0]          top_valid
);
    logic [K-1:0] better;
    always_comb begin
        for (int i = 0; i < K; i++)
            better[i] = !top_valid[i] || (score > $signed(top_score[i*SW +: SW])) ||
                        (score == $signed(top_score[i*SW +: SW]) && idx < top_idx[i*IW +: IW]);
    end
    always_ff @(posedge clk) begin
        if (!rst_n || clear) top_valid <= '0;
        else if (in_valid) begin
            for (int i = 0; i < K; i++) begin
                if (better[i]) begin
                    if (i == 0 || !better[(i == 0) ? 0 : i - 1]) begin
                        top_valid[i] <= 1'b1;
                        top_score[i*SW +: SW] <= score;
                        top_idx[i*IW +: IW] <= idx;
                    end else begin
                        top_valid[i] <= top_valid[((i == 0) ? 0 : i - 1)];
                        top_score[i*SW +: SW] <= top_score[((i == 0) ? 0 : i - 1)*SW +: SW];
                        top_idx[i*IW +: IW] <= top_idx[((i == 0) ? 0 : i - 1)*IW +: IW];
                    end
                end
            end
        end
    end
endmodule
