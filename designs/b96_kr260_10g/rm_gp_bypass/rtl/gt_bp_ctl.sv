// gt_bp_ctl.sv (brief 96F1b): the reset drive, the alignment timeout with retry, and the run gate of ONE direction's GT Wizard buffer-bypass controller (gtwiz_buffbypass_{tx,rx}, auto mode, one lane).
// It follows the Wizard's generated example design (the reading is in the 96F2 note: results/b96f2 on branch b96f2-sources; PG182):
//  - reset: the controller's reset input is the INVERSE of the user-clock helper's active level, passed through a reset synchroniser in the controller's own clock domain (asynchronous assert,
//    synchronous release: xpm_cdc_async_rst, the one place the house rules allow an asynchronous reset). AMD's TX controller is reset exactly so. AMD's RX controller is also held in reset while the TX
//    controller is not done; AMD's own comment calls that term specific to its loopback example, and RX alignment (RXDLYSRESET, RXSYNCDONE, RXPHALIGNDONE) uses no TX signal, so this module has no such input.
//  - timeout and retry: AMD's init state machine gives TX 30 ms and RX 130 ms, then resets and retries. Here the timer runs while the controller is out of reset, the reset helper is done (so the controller
//    has been told to start) and the alignment of THIS sequence has not finished; at TIMEOUT_CLKS the controller is reset for RST_CLKS clocks and restarts by itself (it starts on the first clock after its
//    reset is released while the reset helper's done is high). After MAX_RETRIES retries the next timeout sets gave_up, which stays until the next GT reset sequence (rst_done low) or a clock-inactive reset.
//    The timer does NOT run while the reset helper itself is still working: a slow GT reset (for example a late receive CDR) is not an alignment failure and has its own status bits.
//  - the controller is also held in reset while the reset helper's done is low (a GT reset sequence is running). Found in simulation: the controller starts only from its idle state, so one that hung waiting for
//    SYNCDONE ignores the next reset-done edge and stays hung; AMD's example avoids this only because its whole init state machine resets the lot. A side effect: the controller's done and error are cleared at
//    the start of every sequence, so the previous sequence's done is no longer visible after the reset-done edge (gt_bp_gate stays as the safeguard).
//  - an error from the controller (PHALIGNDONE not high when the alignment ends) is NOT retried: the gate keeps the direction in reset until the next GT reset, as in 96F1 (stricter than AMD's example, which
//    only shows it on a VIO), and the status registers record it.
// run = rst_done AND armed AND bp_done AND no error (gt_bp_gate, 96F1: the controller's done from the previous sequence stays high for 6 to 12 clocks after the reset-done edge and must not release the paths).
module gt_bp_ctl #(
    parameter int TIMEOUT_CLKS = 4_833_984,   // 30 ms at 161.1328125 MHz (TX); use 20_947_266 for the 130 ms RX value
    parameter int MAX_RETRIES  = 3,           // 1 to 15: retries after a timeout before giving up (attempts = MAX_RETRIES + 1)
    parameter int RST_CLKS     = 8            // clocks the controller is held in reset for a retry (at least 2)
) (
    input  logic       clk,         // the direction's user clock (TXUSRCLK2 or RXUSRCLK2): the clock the controller runs on
    input  logic       clk_active,  // gtwiz_userclk_{tx,rx}_active_out (1 = the user clock is running)
    input  logic       rst_done,    // gtwiz_reset_{tx,rx}_done_out
    input  logic       bp_done,     // gtwiz_buffbypass_{tx,rx}_done_out
    input  logic       bp_err,      // gtwiz_buffbypass_{tx,rx}_error_out
    output logic       bp_reset,    // to gtwiz_buffbypass_{tx,rx}_reset_in (active high)
    output logic       run,         // 1 = this direction's PCS, MAC and paths may leave reset
    output logic [3:0] retries,     // timeout retries in this reset sequence (clears when rst_done drops)
    output logic       gave_up      // 1 = every attempt timed out (sticky until the next reset sequence)
);
    localparam int TW = $clog2(TIMEOUT_CLKS + 1);
    // reset synchroniser: src_arst is the ACTIVE level (RST_ACTIVE_HIGH = 0: low = reset), so no logic sits in front of it; act_s is low while the clock is inactive, then rises synchronously
    logic act_s;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(0)) u_rs (.src_arst(clk_active), .dest_clk(clk), .dest_arst(act_s));

    logic armed, retry_rst = 1'b0;
    logic [TW-1:0] tmr = '0;
    logic [3:0] rcnt = '0;
    logic [3:0] rty = '0;
    logic gu = 1'b0;
    gt_bp_gate u_gate (.clk(clk), .rst_done(rst_done), .bp_done(bp_done), .bp_err(bp_err), .run(run), .armed(armed));
    wire aligned = armed && bp_done;                               // the controller has finished (with or without an error) for this sequence
    always_ff @(posedge clk) begin
        if (!act_s || !rst_done) begin                             // clock not active, or no reset sequence finished: a new sequence starts afresh
            tmr <= '0; rcnt <= '0; rty <= '0; gu <= 1'b0; retry_rst <= 1'b0;
        end else if (retry_rst) begin                              // holding the controller in reset for a retry
            tmr <= '0;
            if (rcnt == 4'(RST_CLKS - 1)) begin retry_rst <= 1'b0; rcnt <= '0; end else rcnt <= rcnt + 4'd1;
        end else if (aligned || gu) begin
            tmr <= '0;
        end else if (tmr == TW'(TIMEOUT_CLKS - 1)) begin           // this attempt timed out
            tmr <= '0;
            if (rty == 4'(MAX_RETRIES)) gu <= 1'b1;
            else begin rty <= rty + 4'd1; retry_rst <= 1'b1; end
        end else tmr <= tmr + 1'b1;
    end
    assign bp_reset = !act_s || !rst_done || retry_rst;
    assign retries  = rty;
    assign gave_up  = gu;
endmodule
