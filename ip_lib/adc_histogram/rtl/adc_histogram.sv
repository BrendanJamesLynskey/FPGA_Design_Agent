// adc_histogram: code-density histogram for converter tests (brief 26's linearity measurements; brief 30). Counts
// samples by their top BIN_W bits; also min, max and the total. DNL and INL are computed on the host from the counts.
module adc_histogram #(
    parameter int SAMP_W = 12,
    parameter int BIN_W  = 8,            // 2**BIN_W bins
    parameter int CNT_W  = 20
) (
    input  logic              clk,
    input  logic              rst,
    input  logic              clear,       // one-clock pulse: zero the counts (takes 2**BIN_W clocks; samples are ignored meanwhile)
    input  logic              s_valid,
    input  logic [SAMP_W-1:0] s_data,      // offset-binary code
    input  logic [BIN_W-1:0]  rd_bin,
    output logic [CNT_W-1:0]  rd_count,    // count of rd_bin, one clock after rd_bin
    output logic [SAMP_W-1:0] min_code,
    output logic [SAMP_W-1:0] max_code,
    output logic [31:0]       total,
    output logic              busy,
    output logic              overflow     // a bin reached its maximum count and saturated
);
    initial begin
        if (SAMP_W < 4 || SAMP_W > 16) $error("adc_histogram: SAMP_W %0d outside 4..16", SAMP_W);
        if (BIN_W < 2 || BIN_W > SAMP_W || BIN_W > 12) $error("adc_histogram: BIN_W %0d outside 2..min(SAMP_W,12)", BIN_W);
        if (CNT_W < 8 || CNT_W > 32) $error("adc_histogram: CNT_W %0d outside 8..32", CNT_W);
    end
    localparam int N = 1 << BIN_W;
    logic [CNT_W-1:0] mem [0:N-1];
    logic [BIN_W:0] clr;
    // read-modify-write pipeline: stage 1 reads, stage 2 writes (a back-to-back hit on one bin is forwarded)
    logic              v1; logic [BIN_W-1:0] b1; logic [SAMP_W-1:0] d1;
    logic [CNT_W-1:0]  c1; logic [BIN_W-1:0] bw; logic [CNT_W-1:0] cw; logic vw;
    logic [CNT_W-1:0]  cur;
    always_comb begin
        cur = (vw && bw == b1) ? cw : c1;
    end
    assign busy = clr[BIN_W] == 1'b0;
    always_ff @(posedge clk) begin
        v1 <= 1'b0; vw <= 1'b0;
        rd_count <= mem[rd_bin];
        if (rst) begin
            clr <= '0; total <= '0; min_code <= '1; max_code <= '0; overflow <= 1'b0; v1 <= 1'b0; vw <= 1'b0;
        end else if (clear) begin
            clr <= '0; total <= '0; min_code <= '1; max_code <= '0; overflow <= 1'b0;
        end else if (!clr[BIN_W]) begin
            mem[clr[BIN_W-1:0]] <= '0; clr <= clr + 1'b1;
        end else begin
            if (s_valid) begin
                v1 <= 1'b1; b1 <= s_data[SAMP_W-1 -: BIN_W]; d1 <= s_data; c1 <= mem[s_data[SAMP_W-1 -: BIN_W]];
            end
            if (v1) begin
                bw <= b1; vw <= 1'b1;
                if (cur == {CNT_W{1'b1}}) begin cw <= cur; overflow <= 1'b1; end
                else cw <= cur + 1'b1;
                mem[b1] <= (cur == {CNT_W{1'b1}}) ? cur : cur + 1'b1;
                total <= total + 1'b1;
                if (d1 < min_code) min_code <= d1;
                if (d1 > max_code) max_code <= d1;
            end
        end
    end
endmodule
