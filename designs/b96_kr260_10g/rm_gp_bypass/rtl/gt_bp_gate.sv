// gt_bp_gate.sv (brief 96F1): lets one direction of the link run only when the GT Wizard's buffer-bypass controller has finished for the CURRENT reset sequence.
// Why a gate and not the controller's done output alone: the Wizard's controller (gtwiz_buffbypass_{tx,rx}) starts on the rising edge of its reset-done input, and clears
// its done and error outputs only when it starts, a few clocks later (gtwizard_ultrascale_v1_7_gtwiz_buffbypass_tx.v: start_int is registered, done_out <= 0 on the start).
// After a GT datapath reset the done output of the PREVIOUS sequence is therefore still high for those clocks; used directly it would release the PCS before the alignment ran.
// armed is set only after done has been seen LOW while the reset helper's done is high (the controller has restarted), and cleared whenever the helper's done drops.
// error from the controller (TXPHALIGNDONE / RXPHALIGNDONE not high at the end) keeps the direction in reset until the next GT reset: the fail-safe choice.
module gt_bp_gate (
    input  logic clk,        // the direction's user clock (TXUSRCLK2 or RXUSRCLK2): the clock the controller runs on
    input  logic rst_done,   // gtwiz_reset_{tx,rx}_done_out, used as the paths' reset today
    input  logic bp_done,    // gtwiz_buffbypass_{tx,rx}_done_out
    input  logic bp_err,     // gtwiz_buffbypass_{tx,rx}_error_out
    output logic run,        // 1 = this direction's PCS, MAC and paths may leave reset
    output logic armed = 1'b0 // 1 = the controller has restarted for the current reset sequence (brief 96F1b: gt_bp_ctl's alignment timer runs until armed AND done)
);
    always_ff @(posedge clk) begin
        if (!rst_done)    armed <= 1'b0;
        else if (!bp_done) armed <= 1'b1;
    end
    assign run = rst_done && armed && bp_done && !bp_err;
endmodule
