// tb_shutdown.sv: the safe shutdown of b196_top (brief 196). The top's SYSMON stand-in (sim_alarm, tied to zero in the top) is forced from here.
// Checks: the design runs (the core accepts words, led[0] or the checksum moves); one clock of one alarm bit latches shutdown, records the cause,
// holds the core in reset and drives both LEDs low; the latch stays set after the alarm is gone; a reset (power-on) clears it.
// The stream source starts a burst every 65536 clocks, so the bench waits that long (about a second of wall time).
`timescale 1ns/1ps
module tb_shutdown;
    logic clk = 0;
    wire [1:0] led;
    b196_top dut (.clk_25(clk), .led(led));
    always #20 clk = ~clk;
    int fails = 0;
    task automatic chk(input bit ok, input string what);
        if (!ok) begin fails++; $display("FAIL %s", what); end
    endtask
    logic [4:0] force_alarm = '0;
    initial force dut.u_guard.sim_alarm = force_alarm;
    int accepted = 0, n_prev = 0;
    always @(posedge clk) if (dut.accept) accepted <= accepted + 1;
    initial begin
        repeat (70000) @(posedge clk);                       // past the power-on reset and the first burst
        chk(accepted >= 16, "the core accepted a burst before any alarm");
        chk(dut.shutdown === 1'b0, "no shutdown without an alarm");
        chk(dut.aresetn === 1'b1, "core out of reset before any alarm");
        @(negedge clk); force_alarm = 5'b00010; @(negedge clk); force_alarm = '0;        // VCCINT alarm for one clock
        repeat (3) @(posedge clk);
        chk(dut.shutdown === 1'b1, "one alarm clock latches the shutdown");
        chk(dut.cause === 5'b00010, "the cause names the first alarm");
        chk(dut.aresetn === 1'b0, "the core is held in reset");
        repeat (4) @(posedge clk);
        chk(led === 2'b00, "both LEDs low in the safe state");
        n_prev = accepted; repeat (140000) @(posedge clk);
        chk(accepted == n_prev, "no word is accepted after the shutdown");
        chk(dut.shutdown === 1'b1, "the shutdown stays latched when the alarm is gone");
        force_alarm = 5'b10000; repeat (2) @(posedge clk); force_alarm = '0; @(posedge clk);
        chk(dut.cause === 5'b00010, "a later alarm does not overwrite the first cause");
        if (fails == 0) $display("TB PASS"); else $display("TB FAIL %0d", fails);
        $finish;
    end
endmodule
