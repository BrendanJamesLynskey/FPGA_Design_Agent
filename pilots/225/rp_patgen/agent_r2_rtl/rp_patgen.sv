// rp_patgen: P2 programmable pulse and pattern generator for OUT1 (block inside the shell).
//
// Blocks (architecture.yaml): bus_regs (decode, write rules, read mux, ack/err),
// seq_gen (pulse and pattern sequencer on the START shadows), out_clamp (LIMIT clamp,
// CLAMPED, registered dac_a; dac_b tied to 0).
//
// One clock domain (clk). rstn is active low and synchronous; it is inverted once into
// rst (active high) and only control and configuration registers take it.
//
// Bus: one access per clk. An access presented in clk k is captured (pend_*) and applied
// at clk k+1; sys_ack is high after clk k+1 with sys_rdata or sys_err. A write takes
// effect at that same edge.
//
// Sequence: START with RUNNING 0 copies the sequence settings into the shadow registers
// (suffix _s); the sequencer runs only on the shadows. LIMIT is not latched: the clamp
// uses the live value on every clk.
//
// Timing: START applied at edge T+1 (RUNNING visible after T+1); the first sample is
// registered at edge T+2. STOP applied at edge T+1 makes dac_a 0 after T+1.

module rp_patgen #(
    parameter integer LIMIT_MAX_COUNTS    = 7372,
    parameter integer LIMIT_RESET_COUNTS  = 4096,
    parameter integer LEVEL_MAX_COUNTS    = 8191,
    parameter integer LEVEL_MIN_COUNTS    = -8192,
    parameter integer PERIOD_RESET_CYCLES = 1250,
    parameter integer WIDTH_RESET_CYCLES  = 625,
    parameter integer PAT_MAX_SAMPLES     = 16
) (
    input  logic        clk,
    input  logic        rstn,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] sys_addr,      // bits 31 to 20 unused: the shell decodes the slot
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic [31:0] sys_wdata,
    input  logic        sys_wen,
    input  logic        sys_ren,
    output logic [31:0] sys_rdata,
    output logic        sys_err,
    output logic        sys_ack,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [13:0] adc_a,         // IN1, unused by this block
    input  logic [13:0] adc_b,         // IN2, unused by this block
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [13:0] dac_a,         // OUT1 data
    output logic [13:0] dac_b          // OUT2 data, tied to 0
);

  localparam logic [31:0] ID_VALUE = 32'hFDA10201;
  localparam logic [31:0] LIM_MAX32 = 32'(LIMIT_MAX_COUNTS);
  localparam logic [13:0] LIM_MAX14 = 14'(LIMIT_MAX_COUNTS);
  localparam logic signed [31:0] LVL_MAX_S = 32'(LEVEL_MAX_COUNTS);
  localparam logic signed [31:0] LVL_MIN_S = 32'(LEVEL_MIN_COUNTS);
  localparam logic [13:0] LVL_MAX14 = 14'(LEVEL_MAX_COUNTS);
  localparam logic [13:0] LVL_MIN14 = 14'(LEVEL_MIN_COUNTS);
  localparam logic [31:0] PAT_MAX32 = 32'(PAT_MAX_SAMPLES);
  localparam logic [4:0]  PAT_MAX5  = 5'(PAT_MAX_SAMPLES);

  // ------------------------------------------------------------------ functions
  // level / sample write: signed 32-bit value saturated to the 14-bit signed range
  function automatic logic [13:0] sat_level(input logic [31:0] v);
    logic signed [31:0] s;
    s = v;
    if (s > LVL_MAX_S)      sat_level = LVL_MAX14;
    else if (s < LVL_MIN_S) sat_level = LVL_MIN14;
    else                    sat_level = s[13:0];
  endfunction

  // COUNT and SAMPLE_DIV write: 0 stores 1, above 65535 stores 65535
  function automatic logic [15:0] cnt16(input logic [31:0] v);
    if (v == 32'd0)          cnt16 = 16'd1;
    else if (v > 32'd65535)  cnt16 = 16'd65535;
    else                     cnt16 = v[15:0];
  endfunction

  // ------------------------------------------------------------------ rst
  wire rst = ~rstn;   // inverted once; active high inside the block

  // ------------------------------------------------------------------ declarations
  // bus stage 1 (captured request) and bus outputs
  logic        pend_wr, pend_rd;
  logic [19:0] pend_addr;
  logic [31:0] pend_data;
  logic        ack_r, err_r;
  logic [31:0] rdata_r;
  logic [31:0] rd_val;

  // configuration registers (live; readable)
  logic [31:0] scratch_r;
  logic        cont_r, mode_r;
  logic [31:0] period_r, width_r;
  logic [13:0] hi_r, lo_r;
  logic [15:0] count_r;
  logic [13:0] limit_r;
  logic [4:0]  plen_r;
  logic [15:0] sdiv_r;
  logic [13:0] pat_r [16];

  // shadow copies latched at START (sequence settings)
  logic        mode_s, cont_s;
  logic [31:0] period_s, width_s;
  logic [13:0] hi_s, lo_s;
  logic [15:0] count_s, sdiv_s;
  logic [4:0]  plen_s;
  logic [13:0] pat_s [16];

  // sequencer state and output
  logic        running, done, clamped;
  logic [31:0] pdone;
  logic [31:0] hcnt;
  logic [4:0]  sidx;
  logic [13:0] dac_r;

  // ------------------------------------------------------------------ bus_regs: decode
  wire        pend_in_win = (pend_addr[19:7] == 13'd0) && (pend_addr[1:0] == 2'b00);
  wire [4:0]  pend_idx    = pend_addr[6:2];
  wire        pend_valid  = pend_in_win && (pend_idx != 5'd14) && (pend_idx != 5'd15);
  wire        pend_ro     = (pend_idx == 5'd0) || (pend_idx == 5'd10) || (pend_idx == 5'd11);
  wire        wr_ok       = pend_wr && pend_valid && !pend_ro;
  wire        rd_ok       = pend_rd && pend_valid;
  wire        bus_err_n   = (pend_wr && !wr_ok) || (pend_rd && !pend_valid);

  // CTRL: STOP wins over START; START is ignored while RUNNING
  wire wr_ctrl    = wr_ok && (pend_idx == 5'd2);
  wire ctrl_stop  = wr_ctrl && pend_data[1];
  wire ctrl_start = wr_ctrl && pend_data[0] && !pend_data[1];
  wire start_go  = ctrl_start && !running;

  // WIDTH limited to 1 .. PERIOD minus 1 at START
  wire [31:0] per_m1    = period_r - 32'd1;
  wire [31:0] width_lim = (width_r == 32'd0) ? 32'd1 :
                          ((width_r > per_m1) ? per_m1 : width_r);

  // LIMIT write: saturates to LIMIT_MAX; applies on the clk it is written
  wire        wr_lim    = wr_ok && (pend_idx == 5'd9);
  wire [13:0] lim_new   = (pend_data > LIM_MAX32) ? LIM_MAX14 : pend_data[13:0];
  wire [13:0] limit_eff = wr_lim ? lim_new : limit_r;

  // PAT_LEN write: 0 stores 1, above PAT_MAX_SAMPLES stores PAT_MAX_SAMPLES
  wire [4:0]  plen_new  = (pend_data == 32'd0) ? 5'd1 :
                          ((pend_data > PAT_MAX32) ? PAT_MAX5 : pend_data[4:0]);

  // read mux (valid offsets only; sys_rdata is 0 when not a valid read)
  always_comb begin
    case (pend_idx)
      5'd0:    rd_val = ID_VALUE;
      5'd1:    rd_val = scratch_r;
      5'd2:    rd_val = {29'd0, cont_r, 2'd0};
      5'd3:    rd_val = {31'd0, mode_r};
      5'd4:    rd_val = period_r;
      5'd5:    rd_val = width_r;
      5'd6:    rd_val = {18'd0, hi_r};
      5'd7:    rd_val = {18'd0, lo_r};
      5'd8:    rd_val = {16'd0, count_r};
      5'd9:    rd_val = {18'd0, limit_r};
      5'd10:   rd_val = {29'd0, clamped, done, running};
      5'd11:   rd_val = pdone;
      5'd12:   rd_val = {27'd0, plen_r};
      5'd13:   rd_val = {16'd0, sdiv_r};
      default: rd_val = pend_idx[4] ? {18'd0, pat_r[pend_idx[3:0]]} : 32'd0;
    endcase
  end

  // ------------------------------------------------------------------ seq_gen
  wire [31:0] pulse_last = period_s - 32'd1;
  wire [31:0] pat_last   = {16'd0, sdiv_s} - 32'd1;
  wire        hold_end   = mode_s ? (hcnt == pat_last) : (hcnt == pulse_last);
  // all periods or passes done (CONT 0): the next clk ends the sequence
  wire        seq_done_now = !cont_s && (pdone == {16'd0, count_s}) &&
                             (hcnt == 32'd0) && (sidx == 5'd0);
  wire [13:0] sel_v = mode_s ? pat_s[sidx[3:0]] :
                      ((hcnt < width_s) ? hi_s : lo_s);

  // ------------------------------------------------------------------ out_clamp
  wire signed [14:0] sel_e = $signed({sel_v[13], sel_v});
  wire signed [14:0] lim_e = $signed({1'b0, limit_eff});
  wire               over_pos = (sel_e > lim_e);
  wire               over_neg = (sel_e < -lim_e);
  wire [13:0]        clamp_v  = over_pos ? limit_eff :
                                (over_neg ? (14'd0 - limit_eff) : sel_v);

  // ------------------------------------------------------------------ datapath (no reset)
  always_ff @(posedge clk) begin
    pend_addr <= sys_addr[19:0];
    pend_data <= sys_wdata;

    if (start_go) begin
      mode_s   <= mode_r;
      period_s <= period_r;
      width_s  <= width_lim;
      hi_s     <= hi_r;
      lo_s     <= lo_r;
      count_s  <= count_r;
      cont_s   <= pend_data[2];
      plen_s   <= plen_r;
      sdiv_s   <= sdiv_r;
      for (int i = 0; i < 16; i++) pat_s[i] <= pat_r[i];
      hcnt     <= 32'd0;
      sidx     <= 5'd0;
    end else if (running && !ctrl_stop) begin
      if (hold_end) begin
        hcnt <= 32'd0;
        if (mode_s) sidx <= (sidx == plen_s - 5'd1) ? 5'd0 : sidx + 5'd1;
      end else begin
        hcnt <= hcnt + 32'd1;
      end
    end
  end

  // ------------------------------------------------------------------ control (sync reset)
  always_ff @(posedge clk) begin
    if (rst) begin
      pend_wr  <= 1'b0;
      pend_rd  <= 1'b0;
      ack_r    <= 1'b0;
      err_r    <= 1'b0;
      rdata_r  <= 32'd0;
      scratch_r <= 32'd0;
      cont_r   <= 1'b0;
      mode_r   <= 1'b0;
      period_r <= 32'(PERIOD_RESET_CYCLES);
      width_r  <= 32'(WIDTH_RESET_CYCLES);
      hi_r     <= 14'h0800;
      lo_r     <= 14'd0;
      count_r  <= 16'd1;
      limit_r  <= 14'(LIMIT_RESET_COUNTS);
      plen_r   <= 5'd16;
      sdiv_r   <= 16'd1;
      for (int i = 0; i < 16; i++) pat_r[i] <= 14'd0;
      running  <= 1'b0;
      done     <= 1'b0;
      clamped  <= 1'b0;
      pdone    <= 32'd0;
      dac_r    <= 14'd0;
    end else begin
      // bus stage 2: ack, error and read data, one clk after the access
      pend_wr <= sys_wen;
      pend_rd <= sys_ren & ~sys_wen;
      ack_r   <= pend_wr | pend_rd;
      err_r   <= bus_err_n;
      rdata_r <= rd_ok ? rd_val : 32'd0;

      // register writes (applied at this edge)
      if (wr_ok) begin
        case (pend_idx)
          5'd1:    scratch_r <= pend_data;
          5'd2:    cont_r    <= pend_data[2];
          5'd3:    mode_r    <= (pend_data == 32'd1);
          5'd4:    period_r  <= (pend_data < 32'd2) ? 32'd2 : pend_data;
          5'd5:    width_r   <= pend_data;
          5'd6:    hi_r      <= sat_level(pend_data);
          5'd7:    lo_r      <= sat_level(pend_data);
          5'd8:    count_r   <= cnt16(pend_data);
          5'd9:    limit_r   <= lim_new;
          5'd12:   plen_r    <= plen_new;
          5'd13:   sdiv_r    <= cnt16(pend_data);
          default: if (pend_idx[4]) pat_r[pend_idx[3:0]] <= sat_level(pend_data);
        endcase
      end

      // sequence control and sequencer state (seq_gen)
      if (ctrl_stop) begin
        running <= 1'b0;
        done    <= 1'b1;
      end else if (start_go) begin
        running <= 1'b1;
        done    <= 1'b0;
        clamped <= 1'b0;
        pdone   <= 32'd0;
        width_r <= width_lim;
      end else if (running) begin
        if (seq_done_now) begin
          running <= 1'b0;
          done    <= 1'b1;
        end else begin
          if (over_pos || over_neg) clamped <= 1'b1;
          if (hold_end && (!mode_s || (sidx == plen_s - 5'd1)))
            pdone <= pdone + 32'd1;
        end
      end

      // output register: 0 unless a sample is produced this clk
      dac_r <= (running && !ctrl_stop && !seq_done_now) ? clamp_v : 14'd0;
    end
  end

  // ------------------------------------------------------------------ outputs
  assign sys_ack   = ack_r;
  assign sys_err   = err_r;
  assign sys_rdata = rdata_r;
  assign dac_a     = dac_r;
  assign dac_b     = 14'd0;

endmodule
