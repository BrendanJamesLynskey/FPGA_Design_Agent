// fir_parallel: the fully parallel FIR core behind the lut_mult variant. Direct form: the last TAPS samples
// sit in a register delay line, every tap has its own multiplier, and a registered adder tree sums the products, so
// one sample is taken every clock. The multipliers are built from LUTs and carry chains (use_dsp "no"): the variant for
// a part, or a budget, with no DSP slices to spare. Coefficients sit in registers. (A transposed form would save the
// delay line but its adder chain holds partial sums made with the old coefficients for TAPS-1 samples after a
// coefficient load, which breaks the shared contract.)
// Pipeline: delay line, product registers, clog2(TAPS) adder levels; the last level is the output register. The whole
// pipeline stalls while a result waits for m_ready.
(* use_dsp = "no" *)
module fir_parallel #(
    parameter int TAPS   = 16,
    parameter int DATA_W = 16,
    parameter int COEF_W = 16,
    parameter int ACC_W  = DATA_W + COEF_W + $clog2(TAPS)
) (
    input  logic                     clk,
    input  logic                     rst,
    output logic                     busy,
    input  logic                     c_valid,
    output logic                     c_ready,
    input  logic signed [COEF_W-1:0] c_data,
    input  logic                     c_last,
    input  logic                     s_valid,
    output logic                     s_ready,
    input  logic signed [DATA_W-1:0] s_data,
    output logic                     m_valid,
    input  logic                     m_ready,
    output logic signed [ACC_W-1:0]  m_data
);
    localparam int KW = $clog2(TAPS + 1);
    localparam int LT = $clog2(TAPS);      // adder tree levels (TAPS >= 2, so at least one)
    logic signed [COEF_W-1:0] h [0:TAPS-1];
    logic signed [DATA_W-1:0] d [0:TAPS-1];
    logic                     va, en;
    logic [LT:0]              vt;          // vt[k]: level k of the tree holds a sample's values (level 0 = products)
    logic [KW-1:0]            ck;

    assign en      = !(m_valid && !m_ready);             // the pipeline moves unless a result is held
    assign c_ready = !busy && !va;                       // no sample waiting for its products
    assign s_ready = !busy && en && !c_valid;            // a coefficient beat goes first
    assign m_valid = vt[LT];

    function automatic int nodes(input int lev);
        int n = TAPS;
        for (int i = 0; i < lev; i++) n = (n + 1) / 2;
        return n;
    endfunction
    logic signed [ACC_W-1:0] tree [0:LT][0:TAPS-1];
    assign m_data = tree[LT][0];

    always_ff @(posedge clk) begin
        if (rst) begin
            busy <= 1'b1; va <= 1'b0; vt <= '0; ck <= '0;
            for (int k = 0; k < TAPS; k++) begin h[k] <= '0; d[k] <= '0; end
        end else begin
            busy <= 1'b0;
            if (c_valid && c_ready) begin
                h[ck] <= c_data;
                ck <= (c_last || ck == KW'(TAPS - 1)) ? '0 : ck + 1'b1;
            end
            if (en) begin
                va <= s_valid && s_ready;
                if (s_valid && s_ready) begin
                    d[0] <= s_data;
                    for (int k = 1; k < TAPS; k++) d[k] <= d[k-1];
                end
                vt <= {vt[LT-1:0], va};
            end
        end
    end
    // products: level 0 of the tree
    for (genvar k = 0; k < TAPS; k++) begin : g_mul
        always @(posedge clk) if (en && va) tree[0][k] <= d[k] * h[k];
    end
    for (genvar lv = 0; lv < LT; lv++) begin : g_lv
        localparam int NI = nodes(lv);
        localparam int NO = nodes(lv + 1);
        for (genvar i = 0; i < NO; i++) begin : g_n
            if (2 * i + 1 < NI) begin : g_add
                always @(posedge clk) if (en && vt[lv]) tree[lv+1][i] <= tree[lv][2*i] + tree[lv][2*i+1];
            end else begin : g_pass
                always @(posedge clk) if (en && vt[lv]) tree[lv+1][i] <= tree[lv][2*i];
            end
        end
    end
endmodule
