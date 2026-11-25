// b196_top.sv: the demonstration design of brief 196 (production_secure) on the Kria KR260 (xck26-sfvc784-2LV-c).
// A 25 MHz clock drives a stream source, the brief-194 development core (fabric ECC, bus parity, safe-state FSM, watchdog) and two LEDs:
// led[0] toggles with the checksum of the words the core handed out, led[1] lights when any of the core's fault flags is set. On a SYSMON
// alarm the design latches `shutdown`, holds the core in reset and drives both LEDs low (the safe state: no activity, outputs inactive).
// Nothing here is a debug port: no ILA, no VIO, no JTAG-to-AXI, no BSCAN, no mark_debug. Not a held-out task; not run on a board.
// (dbg/rtl/b196_top.sv is this file plus one ILA: the debug build that the production_secure check must fail.)
module b196_top (
    input  logic       clk_25,
    output logic [1:0] led
);
    // power-on reset: 32 clocks from the configuration's initial register values, synchronous everywhere
    logic [5:0] por = '0;
    wire        por_done = por[5];
    always_ff @(posedge clk_25) if (!por_done) por <= por + 1'b1;

    logic       shutdown;
    logic [4:0] cause;
    b196_sysmon_guard u_guard (.clk(clk_25), .rst(!por_done), .sim_alarm(5'b0), .shutdown, .cause);

    wire aresetn = por_done && !shutdown;

    // stream source: every 65536 clocks one burst of 16 words from a 64-bit LFSR; valid does not wait for ready
    logic [15:0] tick = '0;
    logic [63:0] lfsr = 64'h1;
    logic        start, sending;
    logic [4:0]  sent;
    logic        s_tvalid, s_tready;
    logic [63:0] cs;
    logic        busy, done, e_corr, e_det, e_fsm, e_wd, e_tmr, m_tvalid;
    logic [63:0] m_tdata;
    wire         accept = s_tvalid && s_tready;

    always_ff @(posedge clk_25) begin
        if (!aresetn) begin
            tick <= '0; start <= 1'b0; sending <= 1'b0; sent <= '0;
        end else begin
            tick  <= tick + 1'b1;
            start <= (&tick) && !busy && !sending;
            if (start) begin sending <= 1'b1; sent <= '0; end
            if (accept) begin
                sent <= sent + 1'b1;
                lfsr <= {lfsr[62:0], lfsr[63] ^ lfsr[62] ^ lfsr[60] ^ lfsr[59]};
                if (sent == 5'd15) sending <= 1'b0;
            end
        end
    end
    assign s_tvalid = sending;

    a194_core #(.ECC(1), .PAR(1), .SAFE(1), .TMR(0), .WD(1)) u_core (
        .aclk(clk_25), .aresetn(aresetn), .start(start), .len(16'd16),
        .s_axis_tdata(lfsr), .s_axis_tvalid(s_tvalid), .s_axis_tready(s_tready),
        .m_axis_tdata(m_tdata), .m_axis_tvalid(m_tvalid), .m_axis_tready(1'b1),
        .busy(busy), .done(done), .checksum(cs),
        .err_corr(e_corr), .err_det(e_det), .fsm_fault(e_fsm), .wd_fault(e_wd), .tmr_fault(e_tmr),
        .dbg_inj_s(1'b0), .dbg_inj_d(1'b0));

    logic [1:0] led_q = '0;
    always_ff @(posedge clk_25) begin
        led_q[0] <= shutdown ? 1'b0 : ^cs;
        led_q[1] <= shutdown ? 1'b0 : (e_corr | e_det | e_fsm | e_wd | e_tmr);
    end
    assign led = led_q;
endmodule
