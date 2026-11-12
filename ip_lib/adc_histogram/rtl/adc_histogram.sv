// adc_histogram: code-density histogram for converter tests (brief 26's linearity measurements; brief 30). Counts
// samples by their top BIN_W bits; also min, max and the total. DNL and INL are computed on the host from the counts.
// Implementation variants (brief 63A), same ports, function and latency, selected by IMPL:
//   "dist_ram"  one bin RAM in LUT RAM with two read ports (the sample path and the host readout)
//   "bram"      two block RAM copies written together, one per read port (a block RAM has one write port and one
//               read port in simple dual-port mode, so the third port costs a second copy)
module adc_histogram #(
    parameter     IMPL   = "dist_ram",   // a string: "dist_ram" or "bram"
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
        if (!(IMPL == "dist_ram" || IMPL == "bram")) $error("adc_histogram: IMPL %s is not dist_ram or bram", IMPL);
        if (SAMP_W < 4 || SAMP_W > 16) $error("adc_histogram: SAMP_W %0d outside 4..16", SAMP_W);
        if (BIN_W < 2 || BIN_W > SAMP_W || BIN_W > 12) $error("adc_histogram: BIN_W %0d outside 2..min(SAMP_W,12)", BIN_W);
        if (CNT_W < 8 || CNT_W > 32) $error("adc_histogram: CNT_W %0d outside 8..32", CNT_W);
    end
    localparam int N = 1 << BIN_W;
    logic [BIN_W:0] clr;
    // read-modify-write pipeline: stage 1 reads, stage 2 writes (a back-to-back hit on one bin is forwarded)
    logic              v1; logic [BIN_W-1:0] b1; logic [SAMP_W-1:0] d1;
    logic [CNT_W-1:0]  c1; logic [BIN_W-1:0] bw; logic [CNT_W-1:0] cw; logic vw;
    logic [CNT_W-1:0]  cur;
    always_comb begin
        cur = (vw && bw == b1) ? cw : c1;
    end
    assign busy = clr[BIN_W] == 1'b0;
    // the bin RAM's one write port: the clear sweep, else the incremented count of the bin in stage 2
    logic             we, s_rd;
    logic [BIN_W-1:0] wa;
    logic [CNT_W-1:0] wd;
    always_comb begin
        we   = !rst && !clear && (!clr[BIN_W] || v1);
        wa   = !clr[BIN_W] ? clr[BIN_W-1:0] : b1;
        wd   = !clr[BIN_W] ? '0 : (cur == {CNT_W{1'b1}}) ? cur : cur + 1'b1;     // a full bin saturates
        s_rd = !rst && !clear && clr[BIN_W] && s_valid;
    end
    logic [CNT_W-1:0] c1_q;                // stage-1 read of the sample's bin
    generate
        if (IMPL == "bram") begin : g_bram
            (* ram_style = "block" *) logic [CNT_W-1:0] mem_s [0:N-1];    // read by the sample path
            (* ram_style = "block" *) logic [CNT_W-1:0] mem_r [0:N-1];    // read by the host
            always_ff @(posedge clk) begin
                if (we) begin mem_s[wa] <= wd; mem_r[wa] <= wd; end
                if (s_rd) c1_q <= mem_s[s_data[SAMP_W-1 -: BIN_W]];
                rd_count <= mem_r[rd_bin];
            end
        end else begin : g_dist
            (* ram_style = "distributed" *) logic [CNT_W-1:0] mem [0:N-1];
            always_ff @(posedge clk) begin
                if (we) mem[wa] <= wd;
                if (s_rd) c1_q <= mem[s_data[SAMP_W-1 -: BIN_W]];
                rd_count <= mem[rd_bin];
            end
        end
    endgenerate
    assign c1 = c1_q;
    always_ff @(posedge clk) begin
        v1 <= 1'b0; vw <= 1'b0;
        if (rst) begin
            clr <= '0; total <= '0; min_code <= '1; max_code <= '0; overflow <= 1'b0; v1 <= 1'b0; vw <= 1'b0;
        end else if (clear) begin
            clr <= '0; total <= '0; min_code <= '1; max_code <= '0; overflow <= 1'b0;
        end else if (!clr[BIN_W]) begin
            clr <= clr + 1'b1;
        end else begin
            if (s_valid) begin
                v1 <= 1'b1; b1 <= s_data[SAMP_W-1 -: BIN_W]; d1 <= s_data;
            end
            if (v1) begin
                bw <= b1; vw <= 1'b1;
                if (cur == {CNT_W{1'b1}}) begin cw <= cur; overflow <= 1'b1; end
                else cw <= cur + 1'b1;
                total <= total + 1'b1;
                if (d1 < min_code) min_code <= d1;
                if (d1 > max_code) max_code <= d1;
            end
        end
    end
endmodule
