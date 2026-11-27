// rp_bus_adapt: the adapter between the Red Pitaya shell's system bus and a user block (brief 243). tools/rp_shell.py puts one in front of every user block.
//
// Why it exists. The shell does not give a block a one-cycle request with an answer valid for one cycle. Between the PS and each slot sits the vendor's
// clock-crossing bridge (sys_bus_cdc). It
//   * holds wen or ren high from the first cycle of an access until the slot's ack has been seen, so a block with a one-cycle ack sees the request for two cycles;
//   * hands the slot's rdata to the PS side only after the ack has been carried back across the crossing, about three clocks after the block raised it,
//     reading sys_rdata combinationally at that moment.
// A block that follows the documented one-cycle convention (rp_user_block, and every block the agent wrote against shell.yaml) raises rdata for the ack cycle
// only and clears it the next cycle, so the PS read the cleared value: every read of such a slot returned 0 (build 170300fd, board visit 2026-11-27; the
// vendor's own slots hold rdata until the next access, so they were not affected). This adapter keeps the block's convention and gives the shell what it needs.
//
// Behaviour (stated, not left to chance):
//   * the block sees exactly ONE access per shell access: b_wen or b_ren is high for the first cycle the shell's wen or ren is seen, never again until the
//     shell's request has dropped and a new one arrives (a write is not repeated while the shell holds it);
//   * b_addr and b_wdata are the shell's, unchanged (the shell keeps them stable for the whole access);
//   * read and write in the same cycle: the write is passed and the read is dropped, as the blocks document;
//   * the block's rdata and err are captured in the cycle its ack is high and then HELD (s_rdata, s_err) until the next access is answered; s_ack goes high the
//     cycle after the block's ack and stays high until the shell drops its request;
//   * a block that has not acked TIMEOUT cycles after the access started is answered with s_ack, s_err high and s_rdata 0, so one silent block cannot hold
//     the shell's bus; a block ack that arrives after that is ignored. The documented block ack is the next cycle, so this never occurs for a conforming block;
//   * added latency: one cycle (the block's ack at cycle n, s_ack at n+1);
//   * reset: synchronous, active low; nothing is held after it.
module rp_bus_adapt #(
    parameter int TIMEOUT = 16
) (
    input  logic        clk,
    input  logic        rstn,
    // the shell side (the vendor's slot bus, after its clock-crossing bridge)
    input  logic [31:0] s_addr,
    input  logic [31:0] s_wdata,
    input  logic        s_wen,
    input  logic        s_ren,
    output logic [31:0] s_rdata,
    output logic        s_err,
    output logic        s_ack,
    // the block side (the one-cycle convention of rp_user_block)
    output logic [31:0] b_addr,
    output logic [31:0] b_wdata,
    output logic        b_wen,
    output logic        b_ren,
    input  logic [31:0] b_rdata,
    input  logic        b_err,
    input  logic        b_ack
);
    logic busy;                              // an access has been passed to the block and not yet released by the shell
    logic [$clog2(TIMEOUT+1)-1:0] wait_cnt;
    logic waiting;                           // passed to the block, its ack not yet seen
    wire  req = s_wen | s_ren;
    wire  take = req & ~busy;

    assign b_addr  = s_addr;
    assign b_wdata = s_wdata;
    assign b_wen   = take & s_wen;
    assign b_ren   = take & s_ren & ~s_wen;

    always_ff @(posedge clk) begin
        if (!rstn) begin
            busy     <= 1'b0;
            waiting  <= 1'b0;
            wait_cnt <= '0;
            s_ack    <= 1'b0;
            s_err    <= 1'b0;
            s_rdata  <= '0;
        end else begin
            if (take) begin
                busy     <= 1'b1;
                waiting  <= 1'b1;
                wait_cnt <= '0;
            end
            if (waiting && !take) begin
                wait_cnt <= wait_cnt + 1'b1;
                if (b_ack) begin
                    waiting <= 1'b0;
                    s_ack   <= 1'b1;
                    s_err   <= b_err;
                    s_rdata <= b_rdata;
                end else if (wait_cnt == TIMEOUT - 1) begin
                    waiting <= 1'b0;
                    s_ack   <= 1'b1;
                    s_err   <= 1'b1;
                    s_rdata <= '0;
                end
            end
            if (s_ack && !req) begin          // the shell has taken the answer and dropped its request
                s_ack <= 1'b0;
                busy  <= 1'b0;
            end
        end
    end
endmodule
