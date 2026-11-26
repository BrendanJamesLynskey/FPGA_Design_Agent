// rp_freqcount: P1 frequency and period meter block (spec.yaml), a block inside the
// Red Pitaya shell. Single clock domain clk (shell ADC clock, 125 MHz). Synchronous
// reset: the shell's active-low rstn is inverted once here into the internal
// active-high rst. No asynchronous reset, no clock gating, no CDC.
//
// Timing follows model.py: a bus access driven in cycle t is answered in cycle t+1
// (sys_ack registered); the register read is combinational from the registers
// during the ack cycle (index registered as rsel_q). The ADC sample is registered
// (adc_q) and decided one cycle later.
module rp_freqcount #(
    /* verilator lint_off UNUSEDPARAM */
    parameter integer GATE_MIN_CYCLES   = 1000,
    parameter integer GATE_RESET_CYCLES = 125000000,
    parameter integer THR_HIGH_RESET    = 256,
    parameter integer THR_LOW_RESET     = -256,
    parameter integer SIGNED_WIDTH      = 14,
    parameter integer CNT_WIDTH         = 32
    /* verilator lint_on UNUSEDPARAM */
) (
    input  wire        clk,
    input  wire        rstn,
    /* verilator lint_off UNUSEDSIGNAL */
    input  wire [31:0] sys_addr,      // only bits 19:0 are used
    /* verilator lint_on UNUSEDSIGNAL */
    input  wire [31:0] sys_wdata,
    input  wire        sys_wen,
    input  wire        sys_ren,
    output wire [31:0] sys_rdata,
    output wire        sys_err,
    output wire        sys_ack,
    input  wire [13:0] adc_a,
    /* verilator lint_off UNUSEDSIGNAL */
    input  wire [13:0] adc_b,
    /* verilator lint_on UNUSEDSIGNAL */
    output wire [13:0] dac_a,
    output wire [13:0] dac_b
);

    // ------------------------------------------------------------------
    // constants
    // ------------------------------------------------------------------
    localparam [31:0] ID_VALUE  = 32'hFDA10101;
    localparam [31:0] GATE_MIN  = GATE_MIN_CYCLES;
    localparam [31:0] GATE_RST  = GATE_RESET_CYCLES;
    localparam [SIGNED_WIDTH-1:0] THR_HI_RST = THR_HIGH_RESET[SIGNED_WIDTH-1:0];
    localparam [SIGNED_WIDTH-1:0] THR_LO_RST = THR_LOW_RESET[SIGNED_WIDTH-1:0];

    // register index (decoded from sys_addr[19:0])
    localparam [3:0] R_ID       = 4'd0;
    localparam [3:0] R_SCRATCH  = 4'd1;
    localparam [3:0] R_CTRL     = 4'd2;
    localparam [3:0] R_GATE_LEN = 4'd3;
    localparam [3:0] R_THR_HIGH = 4'd4;
    localparam [3:0] R_THR_LOW  = 4'd5;
    localparam [3:0] R_STATUS   = 4'd6;
    localparam [3:0] R_EDGES    = 4'd7;
    localparam [3:0] R_GATE_ACT = 4'd8;
    localparam [3:0] R_SPAN     = 4'd9;
    localparam [3:0] R_MEAS     = 4'd10;
    localparam [3:0] R_NONE     = 4'd15;

    // one reset polarity inside: active high
    wire rst = ~rstn;

    // ------------------------------------------------------------------
    // state
    // ------------------------------------------------------------------
    reg  [31:0]             scratch_q;
    reg                     cont_q;
    reg  [31:0]             gate_len_q;
    reg  [SIGNED_WIDTH-1:0] thr_hi_q;
    reg  [SIGNED_WIDTH-1:0] thr_lo_q;
    reg                     busy_q;
    reg                     done_q;
    reg                     few_q;
    reg                     restart_q;   // a gate ended in the previous cycle
    reg                     armed_q;     // Schmitt state
    reg  [13:0]             adc_q;       // registered adc_a sample
    reg  [31:0]             gcnt_q;      // cycles run in the current gate
    reg  [31:0]             gate_n_q;    // GATE_LEN in force at START
    reg  [31:0]             run_q;       // edges counted in the current gate
    reg  [31:0]             first_q;     // gcnt stamp of first counted edge
    reg  [31:0]             last_q;      // gcnt stamp of last counted edge
    reg  [31:0]             edges_q;     // result: EDGES
    reg  [31:0]             gate_act_q;  // result: GATE_ACTUAL
    reg  [31:0]             span_q;      // result: SPAN
    reg  [31:0]             meas_done_q; // result: MEAS_DONE
    reg                     ack_q;
    reg                     err_q;
    reg  [3:0]              rsel_q;      // read index registered in the access cycle

    // ------------------------------------------------------------------
    // bus decode (access presented this cycle)
    // ------------------------------------------------------------------
    reg [3:0] sel;
    always @(*) begin
        case (sys_addr[19:0])
            20'h00000: sel = R_ID;
            20'h00004: sel = R_SCRATCH;
            20'h00008: sel = R_CTRL;
            20'h0000C: sel = R_GATE_LEN;
            20'h00010: sel = R_THR_HIGH;
            20'h00014: sel = R_THR_LOW;
            20'h00018: sel = R_STATUS;
            20'h0001C: sel = R_EDGES;
            20'h00020: sel = R_GATE_ACT;
            20'h00024: sel = R_SPAN;
            20'h00028: sel = R_MEAS;
            default:   sel = R_NONE;
        endcase
    end

    wire is_rw = (sel == R_SCRATCH) || (sel == R_CTRL) || (sel == R_GATE_LEN) ||
                 (sel == R_THR_HIGH) || (sel == R_THR_LOW);
    wire ctrl_wr    = sys_wen && (sel == R_CTRL);
    wire scratch_wr = sys_wen && (sel == R_SCRATCH);
    wire gl_wr      = sys_wen && (sel == R_GATE_LEN);
    wire thrh_wr    = sys_wen && (sel == R_THR_HIGH);
    wire thrl_wr    = sys_wen && (sel == R_THR_LOW);

    // START and CONT
    wire       cont_next = ctrl_wr ? sys_wdata[1] : cont_q;
    wire       start_req = ctrl_wr && sys_wdata[0] && !busy_q;
    wire       restart   = restart_q && cont_next && !busy_q;
    wire       start_go  = start_req || restart;

    // GATE_LEN: a write below GATE_MIN_CYCLES stores GATE_MIN_CYCLES
    wire [31:0] gl_clamped   = (sys_wdata < GATE_MIN) ? GATE_MIN : sys_wdata;
    wire [31:0] gate_len_nxt = gl_wr ? gl_clamped : gate_len_q;

    // ------------------------------------------------------------------
    // Schmitt edge decision on the registered sample
    // ------------------------------------------------------------------
    wire thr_bad  = ($signed(thr_hi_q) <= $signed(thr_lo_q));
    wire rising   = armed_q && !thr_bad && ($signed(adc_q) >= $signed(thr_hi_q));
    wire arm_now  = ($signed(adc_q) <= $signed(thr_lo_q));

    // ------------------------------------------------------------------
    // gate counting (only while busy_q)
    // ------------------------------------------------------------------
    wire [31:0] gcnt_inc   = gcnt_q + 32'd1;
    wire        gate_end   = busy_q && (gcnt_inc >= gate_n_q);
    wire        count_edge = busy_q && rising;
    wire [31:0] run_n      = (count_edge && (run_q != 32'hFFFFFFFF)) ? run_q + 32'd1 : run_q;
    wire [31:0] first_n    = (count_edge && (run_q == 32'd0)) ? gcnt_inc : first_q;
    wire [31:0] last_n     = count_edge ? gcnt_inc : last_q;
    wire [31:0] span_n     = (run_n >= 32'd2) ? (last_n - first_n) : 32'd0;

    // ------------------------------------------------------------------
    // read mux (combinational from the registers in the ack cycle)
    // ------------------------------------------------------------------
    wire [31:0] thr_hi_ext = {{(32-SIGNED_WIDTH){thr_hi_q[SIGNED_WIDTH-1]}}, thr_hi_q};
    wire [31:0] thr_lo_ext = {{(32-SIGNED_WIDTH){thr_lo_q[SIGNED_WIDTH-1]}}, thr_lo_q};
    wire [31:0] status_w   = {28'd0, thr_bad, few_q, done_q, busy_q};

    reg [31:0] rmux;
    always @(*) begin
        case (rsel_q)
            R_ID:       rmux = ID_VALUE;
            R_SCRATCH:  rmux = scratch_q;
            R_CTRL:     rmux = {30'd0, cont_q, 1'b0};
            R_GATE_LEN: rmux = gate_len_q;
            R_THR_HIGH: rmux = thr_hi_ext;
            R_THR_LOW:  rmux = thr_lo_ext;
            R_STATUS:   rmux = status_w;
            R_EDGES:    rmux = edges_q;
            R_GATE_ACT: rmux = gate_act_q;
            R_SPAN:     rmux = span_q;
            R_MEAS:     rmux = meas_done_q;
            default:    rmux = 32'd0;
        endcase
    end

    assign sys_rdata = rmux;
    assign sys_ack   = ack_q;
    assign sys_err   = err_q;
    assign dac_a     = 14'd0;
    assign dac_b     = 14'd0;

    // ------------------------------------------------------------------
    // registers
    // ------------------------------------------------------------------
    always @(posedge clk) begin
        if (rst) begin
            adc_q       <= 14'd0;
            ack_q       <= 1'b0;
            err_q       <= 1'b0;
            rsel_q      <= R_NONE;
            scratch_q   <= 32'd0;
            cont_q      <= 1'b0;
            gate_len_q  <= GATE_RST;
            thr_hi_q    <= THR_HI_RST;
            thr_lo_q    <= THR_LO_RST;
            busy_q      <= 1'b0;
            done_q      <= 1'b0;
            few_q       <= 1'b0;
            restart_q   <= 1'b0;
            armed_q     <= 1'b0;
            edges_q     <= 32'd0;
            gate_act_q  <= 32'd0;
            span_q      <= 32'd0;
            meas_done_q <= 32'd0;
        end else begin
            adc_q      <= adc_a;
            ack_q      <= sys_wen | sys_ren;
            err_q      <= sys_wen ? !is_rw : (sys_ren && (sel == R_NONE));
            rsel_q     <= sys_ren ? sel : R_NONE;

            // config registers
            if (scratch_wr) scratch_q <= sys_wdata;
            if (ctrl_wr)    cont_q    <= sys_wdata[1];
            gate_len_q <= gate_len_nxt;
            if (thrh_wr) thr_hi_q <= sys_wdata[SIGNED_WIDTH-1:0];
            if (thrl_wr) thr_lo_q <= sys_wdata[SIGNED_WIDTH-1:0];

            // Schmitt state: runs continuously, not reset at START or gate end
            if (rising)       armed_q <= 1'b0;
            else if (arm_now) armed_q <= 1'b1;

            // gate control and counting
            if (start_go) begin
                busy_q   <= 1'b1;
                done_q   <= 1'b0;
                gcnt_q   <= 32'd0;
                gate_n_q <= gate_len_nxt;
                run_q    <= 32'd0;
            end else if (busy_q) begin
                gcnt_q  <= gcnt_inc;
                run_q   <= run_n;
                first_q <= first_n;
                last_q  <= last_n;
                if (gate_end) begin
                    busy_q      <= 1'b0;
                    done_q      <= 1'b1;
                    few_q       <= (run_n < 32'd2);
                    edges_q     <= run_n;
                    gate_act_q  <= gate_n_q;
                    span_q      <= span_n;
                    meas_done_q <= meas_done_q + 32'd1;
                end
            end
            restart_q <= gate_end;
        end
    end

endmodule
