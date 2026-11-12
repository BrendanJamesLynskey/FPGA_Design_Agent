// fir_fold: the folded (time-shared MAC) FIR core behind the dsp_bram, dist_ram and serial variants (brief 63A).
//
// MACS = ceil(TAPS / FOLD) multiply-accumulate engines each take FOLD taps in turn, so one output costs FOLD MAC cycles.
// Engine e holds taps e*FOLD .. e*FOLD+FOLD-1. The delay line is one RAM of FOLD words, each word MACS samples wide
// (field e is engine e's segment), used as a circular buffer: a new sample is written into field 0 of slot p while the
// older fields shift up by one, so the sample leaving segment e enters segment e+1. The coefficients live in a second
// RAM of the same shape (field e, address j = tap e*FOLD + j); a coefficient beat is a read-modify-write of one field.
// Padding taps past TAPS keep coefficient zero.
//
// Per sample: accept (read slot p), wait, write slot p, then FOLD read cycles; each read pair feeds the engines through
// A/B, M and P registers (fir_mac: the DSP slice's own pipeline, use_dsp, KB inference template "multiply-accumulate
// with pipeline registers"); a registered adder tree sums the MACS partial sums. Initiation interval FOLD + 3 clocks.
// A small output queue lets the next samples start while earlier results wait for m_ready.
module fir_fold #(
    parameter int TAPS      = 16,
    parameter int DATA_W    = 16,
    parameter int COEF_W    = 16,
    parameter int FOLD      = 4,
    parameter int MEM_STYLE = 0,           // fir_ram STYLE: 0 synthesis decides, 1 block RAM, 2 LUT RAM
    parameter int ACC_W     = DATA_W + COEF_W + $clog2(TAPS)
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
    localparam int F  = FOLD;
    localparam int M  = (TAPS + F - 1) / F;
    localparam int AW = (F > 1) ? $clog2(F) : 1;
    localparam int EW = (M > 1) ? $clog2(M) : 1;
    localparam int L  = (M > 1) ? $clog2(M) : 0;
    localparam int KW = $clog2(TAPS + 1);

    // ---- memories ------------------------------------------------------------------------------------------------
    logic            d_we, c_we;
    logic [AW-1:0]   d_wa, d_ra, c_wa, c_ra;
    logic [M*DATA_W-1:0] d_wd, d_q;
    logic [M*COEF_W-1:0] c_wd, c_q;
    fir_ram #(.WIDTH(M*DATA_W), .DEPTH(F), .STYLE(MEM_STYLE)) u_dly (.clk, .we(d_we), .wa(d_wa), .wd(d_wd), .ra(d_ra), .q(d_q));
    fir_ram #(.WIDTH(M*COEF_W), .DEPTH(F), .STYLE(MEM_STYLE)) u_cof (.clk, .we(c_we), .wa(c_wa), .wd(c_wd), .ra(c_ra), .q(c_q));

    // ---- control -------------------------------------------------------------------------------------------------
    typedef enum logic [2:0] {S_INIT, S_IDLE, S_U1, S_U2, S_SWEEP, S_C1, S_C2} state_t;
    state_t st;
    logic [AW-1:0] p, rp, j, ia;           // write slot, sweep read slot, sweep count, init address
    logic [AW-1:0] cj;                     // coefficient load: address within an engine
    logic [EW-1:0] ce;                     //                   engine
    logic [KW-1:0] ck;                     //                   tap index
    logic signed [DATA_W-1:0] xin;
    logic signed [COEF_W-1:0] cin;
    logic          cin_last;
    localparam int LAT = F + 8 + L;          // the wrapper's LATENCY for this core
    localparam int OQ  = (LAT + F + 2) / (F + 3) + 1;
    localparam int NW  = $clog2(OQ + 1);
    logic [NW-1:0] cnt;                    // samples accepted and not yet taken from the output (at most OQ)
    logic [NW-1:0] qn;                     // results waiting behind the output register
    logic signed [ACC_W-1:0] q [0:OQ-1];
    logic          s_fire, c_fire, m_fire;

    assign busy    = (st == S_INIT);
    assign c_ready = (st == S_IDLE);
    assign s_ready = (st == S_IDLE) && !c_valid && (cnt < NW'(OQ));
    assign s_fire  = s_valid && s_ready;
    assign c_fire  = c_valid && c_ready;
    assign m_fire  = m_valid && m_ready;

    function automatic logic [AW-1:0] inc(input logic [AW-1:0] a);
        return (a == AW'(F - 1)) ? '0 : a + 1'b1;
    endfunction
    function automatic logic [AW-1:0] dec(input logic [AW-1:0] a);
        return (a == '0) ? AW'(F - 1) : a - 1'b1;
    endfunction

    always_comb begin
        d_we = 1'b0; d_wa = p;  d_wd = '0;
        c_we = 1'b0; c_wa = cj; c_wd = c_q;
        d_ra = (st == S_SWEEP) ? rp : p;
        c_ra = (st == S_SWEEP) ? j  : cj;
        case (st)
            S_INIT: begin
                d_we = 1'b1; d_wa = ia; c_we = 1'b1; c_wa = ia; c_wd = '0;
            end
            S_U2: begin
                d_we = 1'b1;
                if (M > 1) d_wd = {d_q[(M-1)*DATA_W-1:0], xin};
                else       d_wd = xin;
            end
            S_C2: begin
                c_we = 1'b1;
                c_wd[ce*COEF_W +: COEF_W] = cin;
            end
            default: ;
        endcase
    end

    logic issue, issue_first;              // a sweep read pair is issued this clock
    assign issue       = (st == S_SWEEP);
    assign issue_first = (st == S_SWEEP) && (j == '0);

    always_ff @(posedge clk) begin
        if (rst) begin
            st <= S_INIT; ia <= '0; p <= '0; rp <= '0; j <= '0; cj <= '0; ce <= '0; ck <= '0; cnt <= '0;
        end else begin
            cnt <= cnt + NW'(s_fire) - NW'(m_fire);
            case (st)
                S_INIT: begin
                    ia <= inc(ia);
                    if (ia == AW'(F - 1)) st <= S_IDLE;
                end
                S_IDLE: begin
                    if (c_fire) begin
                        cin <= c_data; cin_last <= c_last; st <= S_C1;
                    end else if (s_fire) begin
                        xin <= s_data; st <= S_U1;
                    end
                end
                S_U1: st <= S_U2;
                S_U2: begin
                    st <= S_SWEEP; rp <= p; j <= '0;
                end
                S_SWEEP: begin
                    rp <= dec(rp);
                    j  <= j + 1'b1;
                    if (j == AW'(F - 1)) begin
                        st <= S_IDLE; p <= inc(p);
                    end
                end
                S_C1: st <= S_C2;
                S_C2: begin
                    st <= S_IDLE;
                    if (cin_last || ck == KW'(TAPS - 1)) begin
                        cj <= '0; ce <= '0; ck <= '0;
                    end else begin
                        ck <= ck + 1'b1;
                        if (cj == AW'(F - 1)) begin cj <= '0; ce <= ce + 1'b1; end
                        else cj <= cj + 1'b1;
                    end
                end
                default: st <= S_INIT;
            endcase
        end
    end

    // ---- MAC engines: RAM read (2 clocks) -> A/B -> M -> P -----------------------------------------------------------
    // flags per stage, shifted every clock; bit k is high k+1 clocks after the issue clock: bit 1 = RAM data valid,
    // bit 2 = A/B valid, bit 3 = M valid
    logic [3:0] v, f, l;
    always_ff @(posedge clk) begin
        if (rst) begin
            v <= '0; f <= '0; l <= '0;
        end else begin
            v <= {v[2:0], issue};
            f <= {f[2:0], issue_first};
            l <= {l[2:0], issue && (j == AW'(F - 1))};
        end
    end
    // acc[e] is engine e's accumulator (P); tree[k] (k >= 1) is level k of a registered adder tree over the partial
    // sums. tv[k] is high in the clock level k holds a complete sample's values (tv[0]: the accumulators).
    function automatic int nodes(input int lev);
        int n = M;
        for (int i = 0; i < lev; i++) n = (n + 1) / 2;
        return n;
    endfunction
    wire  signed [ACC_W-1:0] acc [0:M-1];
    (* use_dsp = "no" *) logic signed [ACC_W-1:0] tree [0:L][0:M-1];   // fabric adders: without this, synthesis put
                                           // the tree into DSP slices at some widths (7 slices for 4 engines)
    logic [L:0] tv;
    always @(posedge clk) tv <= rst ? '0 : {tv, v[3] && l[3]};
    for (genvar e = 0; e < M; e++) begin : g_mac
        fir_mac #(.DATA_W(DATA_W), .COEF_W(COEF_W), .ACC_W(ACC_W)) u_mac (
            .clk, .ld_p(v[3]), .first(f[3]),
            .a_in(d_q[e*DATA_W +: DATA_W]), .b_in(c_q[e*COEF_W +: COEF_W]), .acc(acc[e]));
    end
    for (genvar lv = 0; lv < L; lv++) begin : g_lv
        localparam int NI = nodes(lv);
        localparam int NO = nodes(lv + 1);
        for (genvar i = 0; i < NO; i++) begin : g_n
            if (lv == 0 && 2 * i + 1 < NI) begin : g_add0
                always @(posedge clk) tree[1][i] <= acc[2*i] + acc[2*i+1];
            end else if (lv == 0) begin : g_pass0
                always @(posedge clk) tree[1][i] <= acc[2*i];
            end else if (2 * i + 1 < NI) begin : g_add
                always @(posedge clk) tree[lv+1][i] <= tree[lv][2*i] + tree[lv][2*i+1];
            end else begin : g_pass
                always @(posedge clk) tree[lv+1][i] <= tree[lv][2*i];
            end
        end
    end
    wire signed [ACC_W-1:0] root = (L == 0) ? acc[0] : tree[L][0];

    // ---- output queue ------------------------------------------------------------------------------------------------
    // Up to OQ samples are accepted and not yet taken (cnt): enough for back-to-back samples at the full rate when
    // m_ready is high, since a result takes LAT clocks and a sample is accepted every FOLD + 3. A result goes straight
    // into the output register when it is free, otherwise into a small shift queue behind it.
    always_ff @(posedge clk) begin
        if (rst) begin
            m_valid <= 1'b0; qn <= '0;
        end else if (m_fire || !m_valid) begin
            if (qn != 0) begin
                m_valid <= 1'b1; m_data <= q[0];
                for (int i = 0; i < OQ - 1; i++) q[i] <= q[i+1];
                if (tv[L]) q[qn-1] <= root;
                qn <= qn - (tv[L] ? 0 : 1);
            end else begin
                m_valid <= tv[L];
                if (tv[L]) m_data <= root;
            end
        end else if (tv[L]) begin
            q[qn] <= root; qn <= qn + 1'b1;
        end
    end
endmodule
