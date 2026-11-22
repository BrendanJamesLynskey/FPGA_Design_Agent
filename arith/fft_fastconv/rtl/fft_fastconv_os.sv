// fft_fastconv_os: FIR filtering of a complex stream by fast convolution, overlap-save, on the streaming FFT (arith brief 161, variant "os").
//
// What it does (arith/fft_fastconv/spec.md): the stream on s_axis (one complex sample per beat, W-bit parts) is filtered by a real FIR filter of L taps whose spectrum Hq (N = 2**LOGN complex words of WH bits,
// FH fractional bits) is loaded at run time over AXI4-Lite; the filtered stream, one output per input sample, leaves on m_axis (W-bit parts, saturated). Blocks: N input samples overlap by L - 1;
// B = N - L + 1 new samples make a block; the block goes through a forward FFT (arith/fft sdf, unscaled, natural order), a product with Hq (fft_cmul, exact, then a rounded shift of FH bits) and an inverse FFT
// (scaled by 1/N, so the result is the circular convolution); the first L - 1 outputs of the block are the wrap-around and are dropped, the other B are the filter output.
// Control: a ring of N input words (the last L - 1 samples stay in it from block to block), a four-state machine (clear, collect B samples, wait for output room, feed the ring to the forward FFT in N clocks),
// and an output FIFO of N words with a credit counter: a block starts only when the FIFO has room for its B results, so the FFT pipelines, which cannot be stalled, never lose a word; m_axis honours
// tready fully. s_axis_tready is high only while collecting (it is low during the clear after reset and while a block is fed to the FFT); the average rate is B samples per B + N clocks.
// Filter: the first N clocks after reset the ring and the filter memory are cleared (s_axis_tready low, STATUS.BUSY 1); until coefficients are loaded the filter is zero and the output is zero.
// Gain: the inverse FFT's input is WI = W + LOGN + GB bits wide; the filter's absolute gain (sum of |h|) must not exceed 2**GB or the transform overflows and wraps; outputs beyond W bits saturate (STATUS.SAT).
// Latency (last input beat of a block to the first output beat of that block, empty pipeline, sink ready, room available): 2 * (2 * N + LOGN + ((LOGN - 1) // 2) * LMUL) + MULSTAGES + L + 7, LMUL = TWSTAGES + MULSTAGES + 1.
//
// Intended primitive use (stated before any Vivado run; not yet measured): two sdf FFT pipelines (forward on W bit words growing to W + LOGN, inverse on W + LOGN + GB bit words, each with its natural-order
// reorder buffer of 2 x N words), one complex multiplier (3 or 4 DSP48E1 for the spectral product, WF x WH operands: with WH = 24 and WF = W + LOGN = 26 bits each real multiplier needs 2 x 2 DSP blocks, 16 in all),
// three RAMs of N words (the ring 2W bits, the filter memory 2 WH bits, the output FIFO 2W bits), and the AXI4-Lite register file (about 70 flip-flops).
module fft_fastconv_os #(
    parameter int LOGN      = 8,
    parameter int L         = 33,
    parameter int W         = 16,
    parameter int TW        = 18,
    parameter int WH        = 24,
    parameter int FH        = 14,
    parameter int GB        = 1,
    parameter int RND       = 1,
    parameter int CMUL      = 4,
    parameter int TWSTAGES  = 1,
    parameter int MULSTAGES = 2
) (
    input  logic                clk,
    input  logic                aresetn,
    input  logic                s_axis_tvalid,
    input  logic [2*W-1:0]      s_axis_tdata,
    output logic                s_axis_tready,
    input  logic                m_axis_tready,
    output logic                m_axis_tvalid,
    output logic [2*W-1:0]      m_axis_tdata,
    input  logic                s_axil_awvalid,
    output logic                s_axil_awready,
    input  logic [5:0]          s_axil_awaddr,
    input  logic                s_axil_wvalid,
    output logic                s_axil_wready,
    input  logic [31:0]         s_axil_wdata,
    input  logic [3:0]          s_axil_wstrb,
    output logic                s_axil_bvalid,
    input  logic                s_axil_bready,
    output logic [1:0]          s_axil_bresp,
    input  logic                s_axil_arvalid,
    output logic                s_axil_arready,
    input  logic [5:0]          s_axil_araddr,
    output logic                s_axil_rvalid,
    input  logic                s_axil_rready,
    output logic [31:0]         s_axil_rdata,
    output logic [1:0]          s_axil_rresp
);
    localparam int N    = 1 << LOGN;
    localparam int B    = N - L + 1;
    localparam int WF   = W + LOGN;                 // forward FFT output word
    localparam int WI   = WF + GB;                  // inverse FFT word
    localparam int WP   = WF + WH + 1;              // exact complex product

`ifndef SYNTHESIS
    initial begin
        if (L < 1 || B < N / 4) $error("fft_fastconv_os: L = %0d taps with N = %0d leaves B = %0d new samples per block; B must be at least N/4 (the streaming FFT's frame-gap rule) and L at least 1", L, N, B);
    end
`endif

    logic rst;
    assign rst = ~aresetn;

    // ---- state ---------------------------------------------------------------------------------------------------------------------------
    typedef enum logic [1:0] {S_INIT, S_COLLECT, S_WAIT, S_FEED} state_t;
    state_t          state;
    logic [LOGN:0]   icnt;                          // clear counter 0 .. N-1
    logic [LOGN-1:0] wr_ptr;                        // ring write pointer; at the end of a collect it is the start of the next block
    logic [LOGN:0]   ccnt;                          // samples collected in this block
    logic [LOGN:0]   fcnt;                          // words fed to the forward FFT
    logic [LOGN:0]   credit;                        // free output slots not yet reserved
    logic [31:0]     blocks;
    logic [3:0]      pending;                       // blocks fed whose spectral product has not finished reading the filter memory
    logic            feed_start, mul_done, pop;

    // ---- ring --------------------------------------------------------------------------------------------------------------------------------
    logic [2*W-1:0]  ring [N];
    logic [2*W-1:0]  rd;
    logic [LOGN-1:0] ra;
    logic            in_xfer, v_r, sof_r;
    always_comb begin
        s_axis_tready = (state == S_COLLECT);
        in_xfer       = s_axis_tvalid && s_axis_tready;
        ra            = wr_ptr + fcnt[LOGN-1:0];
        feed_start    = (state == S_WAIT) && (credit >= (LOGN + 1)'(B));
    end
    always_ff @(posedge clk) begin
        if (state == S_INIT) ring[icnt[LOGN-1:0]] <= '0;
        else if (in_xfer) ring[wr_ptr] <= s_axis_tdata;
        rd <= ring[ra];
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            state  <= S_INIT;
            icnt   <= '0;
            wr_ptr <= '0;
            ccnt   <= '0;
            fcnt   <= '0;
            v_r    <= 1'b0;
            sof_r  <= 1'b0;
            blocks <= '0;
        end else begin
            v_r   <= 1'b0;
            sof_r <= 1'b0;
            case (state)
                S_INIT: begin
                    icnt <= icnt + 1'b1;
                    if (icnt == (LOGN + 1)'(N - 1)) begin
                        state  <= S_COLLECT;
                        wr_ptr <= LOGN'(L - 1);
                    end
                end
                S_COLLECT: if (in_xfer) begin
                    wr_ptr <= wr_ptr + 1'b1;
                    ccnt   <= ccnt + 1'b1;
                    if (ccnt == (LOGN + 1)'(B - 1)) begin
                        ccnt  <= '0;
                        state <= S_WAIT;
                    end
                end
                S_WAIT: if (feed_start) begin
                    state  <= S_FEED;
                    fcnt   <= '0;
                    blocks <= blocks + 1'b1;
                end
                default: begin                                          // S_FEED: one ring read per clock, N of them
                    v_r   <= 1'b1;
                    sof_r <= (fcnt == '0);
                    fcnt  <= fcnt + 1'b1;
                    if (fcnt == (LOGN + 1)'(N - 1)) state <= S_COLLECT;
                end
            endcase
        end
    end

    // ---- forward FFT, natural order, unscaled ---------------------------------------------------------------------------------------------------
    logic          fv, fs;
    logic [WF-1:0] fre, fim;
    // verilator lint_off UNUSEDSIGNAL
    logic          fready, iready;
    // verilator lint_on UNUSEDSIGNAL
    fft_sdf_r22 #(.LOGN(LOGN), .W(W), .TW(TW), .SCALE(0), .RND(RND), .ORDER(0), .CMUL(CMUL), .TWSTAGES(TWSTAGES), .MULSTAGES(MULSTAGES)) u_fwd (
        .clk(clk), .rst(rst), .in_valid(v_r), .in_sof(sof_r), .in_inverse(1'b0), .in_re(rd[W-1:0]), .in_im(rd[2*W-1:W]), .out_ready(1'b1),
        .in_ready(fready), .out_valid(fv), .out_sof(fs), .out_re(fre), .out_im(fim));

    // ---- filter memory and AXI4-Lite ---------------------------------------------------------------------------------------------------------------
    logic [2*WH-1:0] hmem [N];
    logic [2*WH-1:0] hrd;
    logic [LOGN-1:0] qcnt, qpos;
    logic            coef_we, sat_pulse, busy;
    logic [LOGN-1:0] coef_addr;
    logic [WH-1:0]   coef_re, coef_im;
    always_comb begin
        qpos = fs ? '0 : qcnt;
        busy = (state == S_INIT) || (pending != 4'd0);
    end
    always_ff @(posedge clk) begin
        if (state == S_INIT) hmem[icnt[LOGN-1:0]] <= '0;
        else if (coef_we) hmem[coef_addr] <= {coef_im, coef_re};
        hrd <= hmem[qpos];
    end
    always_ff @(posedge clk) begin
        if (rst) qcnt <= '0;
        else if (fv) qcnt <= qpos + 1'b1;
    end
    fft_fastconv_axil #(.LOGN(LOGN), .L(L), .W(W), .WH(WH), .FH(FH), .GB(GB)) u_axil (
        .clk(clk), .aresetn(aresetn),
        .s_axil_awvalid(s_axil_awvalid), .s_axil_awready(s_axil_awready), .s_axil_awaddr(s_axil_awaddr), .s_axil_wvalid(s_axil_wvalid), .s_axil_wready(s_axil_wready),
        .s_axil_wdata(s_axil_wdata), .s_axil_wstrb(s_axil_wstrb), .s_axil_bvalid(s_axil_bvalid), .s_axil_bready(s_axil_bready), .s_axil_bresp(s_axil_bresp),
        .s_axil_arvalid(s_axil_arvalid), .s_axil_arready(s_axil_arready), .s_axil_araddr(s_axil_araddr), .s_axil_rvalid(s_axil_rvalid), .s_axil_rready(s_axil_rready),
        .s_axil_rdata(s_axil_rdata), .s_axil_rresp(s_axil_rresp),
        .busy(busy), .sat_pulse(sat_pulse), .blocks(blocks), .coef_we(coef_we), .coef_addr(coef_addr), .coef_re(coef_re), .coef_im(coef_im));
    always_comb mul_done = fv && (qpos == LOGN'(N - 1));                  // the last filter word is read in this clock
    always_ff @(posedge clk) begin
        if (rst) pending <= 4'd0;
        else pending <= pending + 4'(feed_start) - 4'(mul_done);
    end

    // ---- spectral product: filter word aligned with the FFT word, exact complex product, rounded shift of FH, register ---------------------------------------------
    logic signed [WF-1:0] dr, di;
    logic                 dv, ds;
    logic [WH-1:0]        hre, him;
    always_ff @(posedge clk) begin
        dr <= fre;
        di <= fim;
        dv <= fv;
        ds <= fs && fv;
    end
    always_comb begin
        hre = hrd[WH-1:0];
        him = hrd[2*WH-1:WH];
    end
    logic [WP-1:0] pr, pi;
    generate
        if (CMUL == 3) begin : g_m3
            fft_cmul_m3 #(.WA(WF), .WB(WH), .STAGES(MULSTAGES)) u_m (.clk(clk), .ar(dr), .ai(di), .br(hre), .bi(him), .pr(pr), .pi(pi));
        end else begin : g_m4
            fft_cmul_m4 #(.WA(WF), .WB(WH), .STAGES(MULSTAGES)) u_m (.clk(clk), .ar(dr), .ai(di), .br(hre), .bi(him), .pr(pr), .pi(pi));
        end
    endgenerate
    // the valid and start flags follow the data through the multiplier ranks: MULSTAGES clocks, then the register below
    logic xv_in, xs_in;
    generate
        if (MULSTAGES == 0) begin : g_c0
            assign xv_in = dv;
            assign xs_in = dv && ds;
        end else begin : g_cn
            logic [MULSTAGES-1:0] cv, cs;
            always_ff @(posedge clk) begin
                if (rst) begin
                    cv <= '0;
                    cs <= '0;
                end else begin
                    cv[0] <= dv;
                    cs[0] <= dv && ds;
                    for (int k = 1; k < MULSTAGES; k++) begin
                        cv[k] <= cv[k-1];
                        cs[k] <= cs[k-1];
                    end
                end
            end
            assign xv_in = cv[MULSTAGES-1];
            assign xs_in = cs[MULSTAGES-1];
        end
    endgenerate
    // verilator lint_off UNUSEDSIGNAL
    logic signed [WP-1:0] sr, si, rr, ri;      // the shifted product is narrower than the exact one: only the low WI bits are kept
    // verilator lint_on UNUSEDSIGNAL
    logic [WI-1:0] xr, xi;
    always_comb begin
        sr = pr;
        si = pi;
        if (FH == 0) begin
            rr = sr;
            ri = si;
        end else begin
            rr = (RND != 0) ? (sr + (WP)'(1 << (FH - 1))) >>> FH : sr >>> FH;
            ri = (RND != 0) ? (si + (WP)'(1 << (FH - 1))) >>> FH : si >>> FH;
        end
    end
    logic xv, xs;
    always_ff @(posedge clk) begin
        xr <= WI'(rr);
        xi <= WI'(ri);
        xv <= xv_in;
        xs <= xs_in;
    end

    // ---- inverse FFT, natural order, scaled by 1/N -------------------------------------------------------------------------------------------------------
    logic          iv, is_;
    logic [WI-1:0] ire, iim;
    fft_sdf_r22 #(.LOGN(LOGN), .W(WI), .TW(TW), .SCALE(1), .RND(RND), .ORDER(0), .CMUL(CMUL), .TWSTAGES(TWSTAGES), .MULSTAGES(MULSTAGES)) u_inv (
        .clk(clk), .rst(rst), .in_valid(xv), .in_sof(xs), .in_inverse(1'b1), .in_re(xr), .in_im(xi), .out_ready(1'b1),
        .in_ready(iready), .out_valid(iv), .out_sof(is_), .out_re(ire), .out_im(iim));

    // ---- output: drop the first L - 1 words of the block, saturate to W bits, store ---------------------------------------------------------------------
    logic [LOGN-1:0] ocnt, opos;
    logic            keep, wen, sat_r, sat_i;
    logic [W-1:0]    cr, ci;
    function automatic logic [W-1:0] clampw(input logic signed [WI-1:0] v);
        if (v > WI'((1 <<< (W - 1)) - 1)) return W'((1 <<< (W - 1)) - 1);
        if (v < -WI'(1 <<< (W - 1))) return W'(1 <<< (W - 1));
        return v[W-1:0];
    endfunction
    always_comb begin
        opos      = is_ ? '0 : ocnt;
        keep      = iv && (opos >= LOGN'(L - 1));
        wen       = keep;
        cr        = clampw(ire);
        ci        = clampw(iim);
        sat_r     = ($signed(ire) > $signed(WI'((1 <<< (W - 1)) - 1))) || ($signed(ire) < -$signed(WI'(1 <<< (W - 1))));
        sat_i     = ($signed(iim) > $signed(WI'((1 <<< (W - 1)) - 1))) || ($signed(iim) < -$signed(WI'(1 <<< (W - 1))));
        sat_pulse = keep && (sat_r || sat_i);
    end
    always_ff @(posedge clk) begin
        if (rst) ocnt <= '0;
        else if (iv) ocnt <= opos + 1'b1;
    end

    // ---- output FIFO: N words in a RAM with a registered read, a prefetch register and an output register; credit counter reserves room per block ----------------------
    logic [2*W-1:0]  fmem [N];
    logic [LOGN-1:0] wp, rp;
    logic [LOGN:0]   cnt_ram;
    logic [2*W-1:0]  rdq, od;
    logic            have, ov, adv2, can_load, load;
    always_comb begin
        adv2          = !ov || m_axis_tready;
        can_load      = !have || adv2;
        load          = can_load && (cnt_ram != '0);
        m_axis_tvalid = ov;
        m_axis_tdata  = od;
        pop           = ov && m_axis_tready;
    end
    always_ff @(posedge clk) begin
        if (wen) fmem[wp] <= {ci, cr};
        if (can_load && load) rdq <= fmem[rp];
        if (adv2) od <= rdq;
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            wp      <= '0;
            rp      <= '0;
            cnt_ram <= '0;
            have    <= 1'b0;
            ov      <= 1'b0;
            credit  <= (LOGN + 1)'(N);
        end else begin
            if (wen) wp <= wp + 1'b1;
            if (load) rp <= rp + 1'b1;
            cnt_ram <= cnt_ram + (LOGN + 1)'(wen) - (LOGN + 1)'(load);
            if (can_load) have <= load;
            if (adv2) ov <= have;
            credit <= credit - ((feed_start) ? (LOGN + 1)'(B) : '0) + (LOGN + 1)'(pop);
        end
    end

`ifndef SYNTHESIS
    // protocol checkers for simulation: the AXI4-Stream rules on both streams (tdata and tvalid held while stalled, no unknowns after reset) and the AXI4-Lite rules on the register interface
    // verilator lint_off UNUSEDSIGNAL
    int chk_s_errs, chk_m_errs, chk_l_errs;
    // verilator lint_on UNUSEDSIGNAL
    axis_checker #(.DW(2 * W), .NBEAT(0), .NO_STALL(0), .CONTIG(0), .NAME("fft_fastconv_os s_axis")) u_chk_s (.clk(clk), .aresetn(aresetn), .tvalid(s_axis_tvalid), .tready(s_axis_tready), .tdata(s_axis_tdata), .tlast(1'b0), .errs(chk_s_errs));
    axis_checker #(.DW(2 * W), .NBEAT(0), .NO_STALL(0), .CONTIG(0), .NAME("fft_fastconv_os m_axis")) u_chk_m (.clk(clk), .aresetn(aresetn), .tvalid(m_axis_tvalid), .tready(m_axis_tready), .tdata(m_axis_tdata), .tlast(1'b0), .errs(chk_m_errs));
    axil_checker #(.NAME("fft_fastconv_os s_axil")) u_chk_l (.clk(clk), .aresetn(aresetn),
        .awvalid(s_axil_awvalid), .awready(s_axil_awready), .awaddr(s_axil_awaddr), .wvalid(s_axil_wvalid), .wready(s_axil_wready), .wdata(s_axil_wdata), .wstrb(s_axil_wstrb),
        .bvalid(s_axil_bvalid), .bready(s_axil_bready), .bresp(s_axil_bresp), .arvalid(s_axil_arvalid), .arready(s_axil_arready), .araddr(s_axil_araddr),
        .rvalid(s_axil_rvalid), .rready(s_axil_rready), .rdata(s_axil_rdata), .rresp(s_axil_rresp), .errs(chk_l_errs));
`endif
endmodule
