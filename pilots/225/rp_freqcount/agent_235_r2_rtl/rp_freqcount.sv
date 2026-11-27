// rp_freqcount: P1 frequency and period meter block (inside the STEMlab shell).
// One clock domain (clk, 125 MHz). Synchronous active-low rstn, inverted once to rst.
// Bus: registered acknowledge one clk after each sys_wen / sys_ren, read data
// registered from the pre-edge register state. Register map per spec.yaml.
// Writes take effect at the clk edge after the access: every sample, gate end and
// gate start in the access clk sees the register values from before that edge.
// dac_a and dac_b are tied to 0. adc_b is not used.
module rp_freqcount #(
    parameter logic [31:0] GATE_LEN_RESET_CYCLES = 32'd125000000,
    parameter logic [31:0] GATE_LEN_MIN_CYCLES   = 32'd1000,
    parameter integer      THR_HIGH_RESET        = 256,
    parameter integer      THR_LOW_RESET         = -256,
    parameter logic [31:0] ID_VALUE              = 32'hFDA10101
) (
    input  logic        clk,
    input  logic        rstn,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] sys_addr,
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic [31:0] sys_wdata,
    input  logic        sys_wen,
    input  logic        sys_ren,
    output logic [31:0] sys_rdata,
    output logic        sys_err,
    output logic        sys_ack,
    input  logic [13:0] adc_a,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [13:0] adc_b,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [13:0] dac_a,
    output logic [13:0] dac_b
);
    localparam logic [19:0] A_ID          = 20'h00000;
    localparam logic [19:0] A_SCRATCH     = 20'h00004;
    localparam logic [19:0] A_CTRL        = 20'h00008;
    localparam logic [19:0] A_GATE_LEN    = 20'h0000C;
    localparam logic [19:0] A_THR_HIGH    = 20'h00010;
    localparam logic [19:0] A_THR_LOW     = 20'h00014;
    localparam logic [19:0] A_STATUS      = 20'h00018;
    localparam logic [19:0] A_EDGES       = 20'h0001C;
    localparam logic [19:0] A_GATE_ACTUAL = 20'h00020;
    localparam logic [19:0] A_SPAN        = 20'h00024;
    localparam logic [19:0] A_MEAS_DONE   = 20'h00028;
    localparam logic [31:0] M32           = 32'hFFFFFFFF;

    assign dac_a = 14'd0;
    assign dac_b = 14'd0;

    logic rst;
    assign rst = ~rstn;

    // ---------------------------------------------------------------- state
    logic [31:0]        scratch;
    logic               cont;
    logic [31:0]        gate_len;
    logic signed [13:0] thr_hi;
    logic signed [13:0] thr_lo;
    logic               busy;
    logic               done;
    logic               fewedges;
    logic [31:0]        edges;
    logic [31:0]        gate_actual;
    logic [31:0]        span;
    logic [31:0]        meas_done;
    // gate datapath (no reset: loaded at START)
    logic [31:0]        cur_n;
    logic [31:0]        idx;
    logic [31:0]        cur_edges;
    logic [31:0]        first;
    logic [31:0]        last;

    // ------------------------------------------------------- bus decode
    logic [19:0] a;
    logic        aligned;
    assign a       = sys_addr[19:0];
    assign aligned = (sys_addr[1:0] == 2'b00);

    logic wr_sel, wr_scr, wr_ctrl, wr_gl, wr_thi, wr_tlo, wr_ok, wr_err;
    assign wr_sel  = sys_wen & aligned;
    assign wr_scr  = wr_sel & (a == A_SCRATCH);
    assign wr_ctrl = wr_sel & (a == A_CTRL);
    assign wr_gl   = wr_sel & (a == A_GATE_LEN);
    assign wr_thi  = wr_sel & (a == A_THR_HIGH);
    assign wr_tlo  = wr_sel & (a == A_THR_LOW);
    assign wr_ok   = wr_scr | wr_ctrl | wr_gl | wr_thi | wr_tlo;
    assign wr_err  = sys_wen & ~wr_ok;

    logic bad_thr;
    assign bad_thr = (thr_hi <= thr_lo);

    logic        rd_ok;
    logic [31:0] rd_val;
    always_comb begin
        rd_ok  = 1'b1;
        rd_val = 32'd0;
        case (a)
            A_ID:          rd_val = ID_VALUE;
            A_SCRATCH:     rd_val = scratch;
            A_CTRL:        rd_val = {30'd0, cont, 1'b0};
            A_GATE_LEN:    rd_val = gate_len;
            A_THR_HIGH:    rd_val = {{18{thr_hi[13]}}, thr_hi};
            A_THR_LOW:     rd_val = {{18{thr_lo[13]}}, thr_lo};
            A_STATUS:      rd_val = {28'd0, bad_thr, fewedges, done, busy};
            A_EDGES:       rd_val = edges;
            A_GATE_ACTUAL: rd_val = gate_actual;
            A_SPAN:        rd_val = span;
            A_MEAS_DONE:   rd_val = meas_done;
            default:       rd_ok  = 1'b0;
        endcase
    end

    // write values: a write in this clk takes effect at the next clk, so the
    // sampling, gate start and gate end in this clk use the registers as they are
    logic [31:0]        gl_new;
    logic signed [13:0] wd14;
    logic               start_req, start_acc, cont_n;
    assign gl_new    = (sys_wdata < GATE_LEN_MIN_CYCLES) ? GATE_LEN_MIN_CYCLES : sys_wdata;
    assign wd14      = sys_wdata[13:0];
    assign start_req = wr_ctrl & sys_wdata[0];
    assign start_acc = start_req & ~busy;
    // START while BUSY changes nothing; otherwise CONT takes bit 1 of the write
    assign cont_n    = (wr_ctrl & ~(sys_wdata[0] & busy)) ? sys_wdata[1] : cont;

    // ----------------------------------------------------- edge detector
    logic edge_o;
    schmitt_edge u_edge (
        .clk    (clk),
        .rst    (rst),
        .s      (adc_a),
        .thr_hi (thr_hi),
        .thr_lo (thr_lo),
        .edge_o (edge_o)
    );

    // ------------------------------------------------------ gate sequencer
    logic        edge_c, end_now;
    logic [31:0] idx_n, cur_edges_n, first_n, last_n, span_n;
    assign edge_c      = edge_o & busy;
    assign idx_n       = idx + 32'd1;
    assign end_now     = busy & (idx_n == cur_n);
    assign cur_edges_n = (edge_c & (cur_edges != M32)) ? (cur_edges + 32'd1) : cur_edges;
    assign first_n     = (edge_c & (cur_edges == 32'd0)) ? idx_n : first;
    assign last_n      = edge_c ? idx_n : last;
    assign span_n      = (cur_edges_n >= 32'd2) ? (last_n - first_n) : 32'd0;

    always_ff @(posedge clk) begin
        if (start_acc) begin
            cur_n     <= gate_len;
            idx       <= 32'd0;
            cur_edges <= 32'd0;
        end else if (busy) begin
            idx       <= end_now ? 32'd0 : idx_n;
            cur_edges <= end_now ? 32'd0 : cur_edges_n;
            first     <= first_n;
            last      <= last_n;
            if (end_now) cur_n <= gate_len;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            busy        <= 1'b0;
            done        <= 1'b0;
            fewedges    <= 1'b0;
            edges       <= 32'd0;
            gate_actual <= 32'd0;
            span        <= 32'd0;
            meas_done   <= 32'd0;
        end else if (start_acc) begin
            busy <= 1'b1;
            done <= 1'b0;
        end else if (end_now) begin
            // CONT as it was before this clk: clearing CONT lets this gate finish
            busy        <= cont;
            done        <= 1'b1;
            edges       <= cur_edges_n;
            gate_actual <= cur_n;
            span        <= span_n;
            fewedges    <= (cur_edges_n < 32'd2);
            meas_done   <= meas_done + 32'd1;
        end
    end

    // -------------------------------------------------- configuration regs
    always_ff @(posedge clk) begin
        if (rst) begin
            scratch  <= 32'd0;
            cont     <= 1'b0;
            gate_len <= GATE_LEN_RESET_CYCLES;
            thr_hi   <= 14'(THR_HIGH_RESET);
            thr_lo   <= 14'(THR_LOW_RESET);
        end else begin
            cont <= cont_n;
            if (wr_scr) scratch  <= sys_wdata;
            if (wr_gl)  gate_len <= gl_new;
            if (wr_thi) thr_hi   <= wd14;
            if (wr_tlo) thr_lo   <= wd14;
        end
    end

    // ---------------------------------------------------------- bus response
    logic err_n;
    assign err_n = wr_err | (sys_ren & (sys_wen | ~rd_ok));

    always_ff @(posedge clk) begin
        if (rst) begin
            sys_ack <= 1'b0;
            sys_err <= 1'b0;
        end else begin
            sys_ack <= sys_wen | sys_ren;
            sys_err <= err_n;
        end
    end

    always_ff @(posedge clk) begin
        sys_rdata <= (sys_ren & ~sys_wen & rd_ok) ? rd_val : 32'd0;
    end
endmodule
