// tb_func.sv: the functional bench of the development design (brief 194). Ports only, so the same file runs on the RTL, on a Vivado
// post-synthesis functional netlist (write_verilog -mode funcsim) and on a post-route timing netlist.
//   +seed=<n>   random seed (default 1)      +bursts=<n>  bursts per run (default 40)
// DUT parameters come from the macro DUT_PARAMS (for example -DDUT_PARAMS="#(.ECC(1),.PAR(1))"); empty for a netlist.
// Each burst: random length 0..40, random gaps on the input, random back-pressure on the output (about 3 clocks in 4 ready).
// Checks: the output words equal the input words in order, done pulses once, the checksum equals the sum, no error flag rises.
`timescale 1ns/1ps
`ifndef DUT_PARAMS
`define DUT_PARAMS
`endif
module tb_func;
    logic        aclk = 0, aresetn = 0;
    logic        start = 0;
    logic [15:0] len = 0;
    logic [63:0] s_tdata = 0;
    logic        s_tvalid = 0, s_tready, m_tvalid, m_tready = 0;
    logic [63:0] m_tdata;
    logic        busy, done, err_corr, err_det, fsm_fault, wd_fault, tmr_fault;
    logic [63:0] checksum;

    a194_core `DUT_PARAMS dut (.aclk(aclk), .aresetn(aresetn), .start(start), .len(len),
        .s_axis_tdata(s_tdata), .s_axis_tvalid(s_tvalid), .s_axis_tready(s_tready),
        .m_axis_tdata(m_tdata), .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready),
        .busy(busy), .done(done), .checksum(checksum), .err_corr(err_corr), .err_det(err_det),
        .fsm_fault(fsm_fault), .wd_fault(wd_fault), .tmr_fault(tmr_fault), .dbg_inj_s(1'b0), .dbg_inj_d(1'b0));

    always #5 aclk = ~aclk;

    int rs;
    function automatic int unsigned rnd();
        return $random(rs);            // $random(seed) is portable (xsim does not take $urandom(seed))
    endfunction
    function automatic int rr(input int hi, input int lo);   // uniform in lo..hi
        return lo + int'(rnd() % (hi - lo + 1));
    endfunction
    int seed, seed0, bursts, errors = 0, ndone;
    logic [63:0] exp_q [$];
    logic [63:0] expsum;
    int n_in, n_out;

    // output side: random back-pressure, compare against the expected queue
    always @(posedge aclk) begin
        if (m_tvalid && m_tready) begin
            if (exp_q.size() == 0) begin
                errors++; $display("TB FAIL: unexpected output word %h", m_tdata);
            end else begin
                if (m_tdata !== exp_q[0]) begin errors++; $display("TB FAIL: word %0d is %h, expected %h", n_out, m_tdata, exp_q[0]); end
                void'(exp_q.pop_front());
            end
            n_out++;
        end
        if (done) ndone++;
    end
    always @(negedge aclk) m_tready <= (rr(3, 0) != 0);

    // accepted-handshake monitor: values sampled before the edge's updates, so s_tready is the one the design saw
    logic acc_q = 0;
    int   n_acc;
    always @(posedge aclk) begin
        acc_q <= s_tvalid && s_tready;
        if (s_tvalid && s_tready) n_acc <= n_acc + 1;
    end

    task automatic burst(input int n);
        int pres, guard;
        expsum = 0; exp_q = {}; n_in = 0; n_out = 0; ndone = 0; n_acc = 0; pres = 0; guard = 0;
        @(negedge aclk); len = n[15:0]; start = 1;
        @(negedge aclk); start = 0;
        while (!(n_acc >= n && ndone > 0) && guard < 4000 + 40 * n) begin
            @(negedge aclk);
            guard++;
            if (!s_tvalid || acc_q) begin                       // the word on the bus was taken (or there is none): present the next
                if (pres < n && rr(3, 0) != 0) begin
                    s_tdata = {rnd(), rnd()};
                    s_tvalid = 1;
                    pres++;
                    exp_q.push_back(s_tdata); expsum += s_tdata;
                end else s_tvalid = 0;
            end
        end
        s_tvalid = 0;
        repeat (6) @(negedge aclk);
        if (guard >= 4000 + 40 * n) begin errors++; $display("TB FAIL: burst of %0d did not finish", n); end
        if (ndone != 1) begin errors++; $display("TB FAIL: done pulsed %0d times (burst of %0d)", ndone, n); end
        if (n_out != n) begin errors++; $display("TB FAIL: %0d words out, expected %0d", n_out, n); end
        if (checksum !== expsum) begin errors++; $display("TB FAIL: checksum %h expected %h", checksum, expsum); end
        if (err_corr || err_det || fsm_fault || wd_fault || tmr_fault) begin
            errors++; $display("TB FAIL: an error flag is set (corr %b det %b fsm %b wd %b tmr %b)", err_corr, err_det, fsm_fault, wd_fault, tmr_fault);
        end
    endtask

    initial begin
        if (!$value$plusargs("seed=%d", seed)) seed = 1;
        if (!$value$plusargs("bursts=%d", bursts)) bursts = 40;
        seed0 = seed; rs = seed;
        #200;                                  // a netlist simulation holds every register in its global set/reset for the first 100 ns (glbl)
        repeat (4) @(negedge aclk);
        aresetn = 1;
        repeat (3) @(negedge aclk);
        for (int b = 0; b < bursts; b++) begin
            // sizes: empty, 1, a few, and bursts longer than the FIFO depth is not reachable (512); keep the draw small and often large
            burst(b == 0 ? 0 : b == 1 ? 1 : (rr(4, 0) == 0 ? rr(600, 300) : rr(40, 2)));
        end
        if (errors == 0) $display("TB PASS: seed %0d, %0d bursts", seed0, bursts);
        else $display("TB FAILED: %0d errors, seed %0d", errors, seed0);
        $finish;
    end
    initial begin #50000000; $display("TB FAIL: timeout"); $finish; end
endmodule
