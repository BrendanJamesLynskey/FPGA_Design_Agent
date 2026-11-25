// a194_ctrl.sv: the burst sequencer (brief 194): a four-state FSM, the remaining-words counter, and an optional watchdog.
// No memory in this module, so the netlist of it is one that flow/eqy_gate.py can prove against this RTL.
//
//   IDLE --start--> RUN --(remaining = 0)--> DRAIN --(drained)--> DONE --> IDLE      (len = 0 goes straight to DONE)
// The state is 3 bits for four states, so four codes are unused: the default arc and fsm_safe_state matter.
//
// Parameters (each a reliability structure, brief 194):
//   SAFE = 1  (* fsm_safe_state = "auto_safe_state" *) on the state register (UG901, FSM_SAFE_STATE): the synthesis tool adds the
//             detection and recovery logic; the RTL is unchanged.
//   TMR  = 1  the remaining counter is three registers with a bitwise majority voter; the voted value is fed back to all three each clock,
//             so a flipped copy is repaired on the next clock. The copies carry DONT_TOUCH so synthesis does not merge them (UG901).
//   WD   = 1  watchdog: WD_LIMIT (256: set per design to the longest legitimate stall plus margin) clocks without progress while busy forces the FSM to IDLE and sets wd_fault (sticky).
// Behaviour a user could guess wrong: the voter and the state register are not protected by TMR; fsm_fault is set only where the RTL's own
// default arc is taken (the SAFE logic of the tool is not visible to it); a start while busy is ignored.
// Fault-injection hooks (simulation only): with A194_FI defined, fi_* are nets the testbench forces for one clock; each is XORed into the D
// input of a register, so the register captures a flipped bit, as a single-event upset would leave it. Without the define they are
// constant zero and fold away in elaboration (brief 194 compares netlists with and without them).
`ifdef A194_FI
`define A194_FIW(name, width) wire [width-1:0] name = '0;
`else
`define A194_FIW(name, width) localparam logic [width-1:0] name = '0;
`endif
module a194_ctrl #(
    parameter int SAFE     = 0,
    parameter int TMR      = 0,
    parameter int WD       = 0,
    parameter int WD_LIMIT = 256
) (
    input  logic        clk,
    input  logic        rst,          // synchronous, active high
    input  logic        start,
    input  logic [15:0] len,
    input  logic        progress,     // a word was accepted or handed out this clock
    input  logic        accept,       // a word was accepted this clock
    input  logic        drained,      // FIFO and output stage empty
    output logic        run,          // input side may accept words
    output logic        busy,
    output logic        done,         // one clock
    output logic        fsm_fault,    // sticky
    output logic        wd_fault,     // sticky
    output logic        tmr_fault,    // sticky: a copy disagreed with the vote
    output logic [2:0]  state_o       // the state register (the formal bench reads it; unconnected in the core)
);
    typedef enum logic [2:0] {IDLE = 3'd0, RUN = 3'd1, DRAIN = 3'd2, DONE = 3'd3} state_t;

    `A194_FIW(fi_state, 3)
    `A194_FIW(fi_ra, 16)
    `A194_FIW(fi_rb, 16)
    `A194_FIW(fi_rc, 16)
    `A194_FIW(fi_r, 16)
    state_t      state_q, state_d;
    logic [15:0] rem_v;                     // the remaining count in use (the vote when TMR = 1)
    logic [15:0] rem_d;
    logic        load_rem, dec_rem;
    logic        illegal;
    logic [15:0] wd_cnt;
    logic        wd_trip;

    // ---- next-state logic (shared by every variant) ----
    always_comb begin
        state_d  = state_q;
        load_rem = 1'b0;
        dec_rem  = 1'b0;
        illegal  = 1'b0;
        case (state_q)
            IDLE:  if (start) begin
                load_rem = 1'b1;
                if (len == 16'd0) state_d = DONE;
                else              state_d = RUN;
            end
            RUN:   begin
                dec_rem = accept;
                if (rem_v == 16'd0) state_d = DRAIN;
            end
            DRAIN: if (drained) state_d = DONE;
            DONE:  state_d = IDLE;
            default: begin
                state_d = IDLE;
                illegal = 1'b1;
            end
        endcase
        if (wd_trip) state_d = IDLE;
    end
    assign rem_d = load_rem ? len : dec_rem ? rem_v - 16'd1 : rem_v;

    // ---- state register: the variant differs only in the attribute ----
    if (SAFE != 0) begin : g_safe
        (* fsm_safe_state = "auto_safe_state" *) state_t sq;
        always_ff @(posedge clk) sq <= state_t'((rst ? IDLE : state_d) ^ fi_state);
        assign state_q = sq;
    end else begin : g_plain
        state_t sq;
        always_ff @(posedge clk) sq <= state_t'((rst ? IDLE : state_d) ^ fi_state);
        assign state_q = sq;
    end

    // ---- remaining counter: one register, or three with a voter ----
    if (TMR != 0) begin : g_tmr
        (* dont_touch = "true" *) logic [15:0] ra, rb, rc;
        assign rem_v = (ra & rb) | (ra & rc) | (rb & rc);
        always_ff @(posedge clk) begin
            if (rst) begin
                ra <= '0; rb <= '0; rc <= '0;
            end else begin
                ra <= rem_d ^ fi_ra; rb <= rem_d ^ fi_rb; rc <= rem_d ^ fi_rc;      // rem_d is built from the vote: a flipped copy is overwritten
            end
        end
        always_ff @(posedge clk) begin
            if (rst) tmr_fault <= 1'b0;
            else if (ra != rem_v || rb != rem_v || rc != rem_v) tmr_fault <= 1'b1;
        end
    end else begin : g_single
        logic [15:0] r;
        assign rem_v = r;
        always_ff @(posedge clk) r <= (rst ? 16'd0 : rem_d) ^ fi_r;
        assign tmr_fault = 1'b0;
    end

    // ---- watchdog ----
    if (WD != 0) begin : g_wd
        always_ff @(posedge clk) begin
            if (rst || !busy || progress) wd_cnt <= '0;
            else wd_cnt <= wd_cnt + 16'd1;
            if (rst) wd_fault <= 1'b0;
            else if (wd_trip) wd_fault <= 1'b1;
        end
        assign wd_trip = busy && (wd_cnt == 16'(WD_LIMIT - 1));
    end else begin : g_nowd
        assign wd_trip  = 1'b0;
        assign wd_cnt   = '0;
        assign wd_fault = 1'b0;
    end

    // ---- outputs ----
    assign state_o = state_q;
    assign busy = (state_q != IDLE);
    assign run  = (state_q == RUN) && (rem_v != 16'd0);
    assign done = (state_q == DONE);
    always_ff @(posedge clk) begin
        if (rst) fsm_fault <= 1'b0;
        else if (illegal) fsm_fault <= 1'b1;
    end
endmodule
