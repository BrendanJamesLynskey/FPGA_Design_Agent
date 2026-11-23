// tb_fault.sv: seeded single-event-upset campaign on the development design (brief 194). RTL only: it needs the A194_FI hooks
// (compile with -DA194_FI). Every trial resets the design, runs one burst of L words (L = 8..24) with random input gaps and output
// back-pressure, and flips bits at one random clock inside the burst. The result is classified against the expected stream:
//   masked     output and checksum correct, no flag raised          (the fault did nothing, or was overwritten)
//   corrected  output and checksum correct, a flag raised            (a structure repaired it and said so)
//   detected   output or completion wrong, a flag raised             (the design knows it is wrong)
//   silent     done seen, output or checksum wrong, no flag          (silent data corruption)
//   hang       no done and no flag
// +target=state|ram|ram2|cnt|cnt2|bus   +trials=<n>   +seed=<n>   (target none = no injection: a sanity run, every trial must be masked)
//   state  one bit of the 3-bit state register          ram   one bit of the word stored by one write (ECC=2: INJECTSBITERR on that write)
//   ram2   two bits of that word (ECC=2: INJECTDBITERR)   cnt  one bit of the remaining counter (TMR: one copy of three)
//   cnt2   TMR only: the same bit in two copies (the limit of TMR)   bus  one bit of the output register or its parity bit
`timescale 1ns/1ps
`ifndef DUT_PARAMS
`define DUT_PARAMS
`endif
module tb_fault;
    logic        aclk = 0, aresetn = 0;
    logic        start = 0;
    logic [15:0] len = 0;
    logic [63:0] s_tdata = 0;
    logic        s_tvalid = 0, s_tready, m_tvalid, m_tready = 0;
    logic [63:0] m_tdata;
    logic        busy, done, err_corr, err_det, fsm_fault, wd_fault, tmr_fault;
    logic [63:0] checksum;
    logic        inj_s = 0, inj_d = 0;

    a194_core `DUT_PARAMS dut (.aclk(aclk), .aresetn(aresetn), .start(start), .len(len),
        .s_axis_tdata(s_tdata), .s_axis_tvalid(s_tvalid), .s_axis_tready(s_tready),
        .m_axis_tdata(m_tdata), .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready),
        .busy(busy), .done(done), .checksum(checksum), .err_corr(err_corr), .err_det(err_det),
        .fsm_fault(fsm_fault), .wd_fault(wd_fault), .tmr_fault(tmr_fault), .dbg_inj_s(inj_s), .dbg_inj_d(inj_d));
    always #5 aclk = ~aclk;

    int rs;
    function automatic int unsigned rnd(); return $random(rs); endfunction
    function automatic int rr(input int hi, input int lo); return lo + int'(rnd() % (hi - lo + 1)); endfunction

    string target;
    int    tcode;     // 0 none 1 state 2 ram 3 ram2 4 cnt 5 cnt2 6 bus
    int    trials, seed, ecc_prim;
    logic [63:0] exp_q [$];
    logic [63:0] expsum;
    int n_out, ndone, n_acc, wr_arm;
    bit bad_out;
    bit armed_d;

    // ECC = 2: the injection inputs act on the write of word wr_arm
    always_comb begin
        inj_s = 1'b0; inj_d = 1'b0;
        if (ecc_prim && s_tvalid && s_tready && n_acc == wr_arm) begin
            if (tcode == 2)  inj_s = 1'b1;
            if (tcode == 3) inj_d = 1'b1;
        end
    end
    always @(posedge aclk) begin
        if (s_tvalid && s_tready) n_acc <= n_acc + 1;
        if (m_tvalid && m_tready) begin
            if (n_out >= exp_q.size() || m_tdata !== exp_q[n_out]) bad_out <= 1;
            n_out <= n_out + 1;
        end
        if (done) ndone <= ndone + 1;
    end
    always @(negedge aclk) m_tready <= (rr(3, 0) != 0);

    // one clock of forced flips (released at the next negedge)
    task apply(input int t, input int L);
        int k, a, b, c;
        case (tcode)
            1: begin k = rr(2, 0); force dut.u_ctrl.fi_state = 3'(1 << k); end
            2: if (!ecc_prim) begin
                b = rr(`DATA_BITS - 1, 0);
                force dut.u_fifo.fi_wmask = 72'(1) << b;
            end
            3: if (!ecc_prim) begin
                b = rr(`DATA_BITS - 1, 0); c = (b + 1 + rr(`DATA_BITS - 2, 0)) % `DATA_BITS;
                force dut.u_fifo.fi_wmask = (72'(1) << b) | (72'(1) << c);
            end
            4: begin
                k = rr(15, 0);
                if (`TMR_ON) begin
                    case (rr(2, 0))
                        0: force dut.u_ctrl.fi_ra = 16'(1 << k);
                        1: force dut.u_ctrl.fi_rb = 16'(1 << k);
                        default: force dut.u_ctrl.fi_rc = 16'(1 << k);
                    endcase
                end else force dut.u_ctrl.fi_r = 16'(1 << k);
            end
            5: begin
                k = rr(15, 0);
                force dut.u_ctrl.fi_ra = 16'(1 << k); force dut.u_ctrl.fi_rb = 16'(1 << k);
            end
            6: begin k = rr(64, 0); force dut.fi_bus = 65'(1) << k; end
            default: ;
        endcase
    endtask
    task clear_forces();
        release dut.u_ctrl.fi_state; release dut.u_ctrl.fi_ra; release dut.u_ctrl.fi_rb; release dut.u_ctrl.fi_rc; release dut.u_ctrl.fi_r;
        release dut.u_fifo.fi_wmask; release dut.fi_bus;
    endtask

    int cnt_masked, cnt_corr, cnt_det, cnt_silent, cnt_hang;

    task automatic trial(input int L, input bit inject);
        int sent, t, t_inj, guard, limit;
        bit flag, completed, wrong;
        exp_q = {}; expsum = 0; n_out = 0; ndone = 0; n_acc = 0; bad_out = 0; sent = 0;
        wr_arm = rr(L - 1, 0);
        // reset
        @(negedge aclk); aresetn = 0; s_tvalid = 0; start = 0;
        repeat (3) @(negedge aclk);
        aresetn = 1;
        repeat (2) @(negedge aclk);
        n_out = 0; ndone = 0; n_acc = 0; bad_out = 0;
        t_inj = rr(2 * L + 4, 1);
        limit = 12 * L + 400;
        len = L[15:0]; start = 1;
        @(negedge aclk); start = 0;
        t = 0;
        while (t < limit && !(ndone > 0 && n_out >= L) && !(wd_fault)) begin
            @(negedge aclk);
            t++;
            clear_forces();
            if (inject && t == t_inj && (tcode < 2 || tcode > 3)) apply(t, L);
            if (s_tvalid && s_tready) sent++;       // sampled at negedge: valid/ready held since the posedge
            if (sent < L && (!s_tvalid || s_tready)) begin
                if (rr(3, 0) != 0) begin
                    s_tdata = {rnd(), rnd()}; s_tvalid = 1;
                    exp_q.push_back(s_tdata); expsum += s_tdata;
                end else s_tvalid = 0;
            end else if (sent >= L) s_tvalid = 0;
            if (inject && (tcode == 2 || tcode == 3) && s_tvalid && s_tready && sent == wr_arm) apply(t, L);   // at the write of word wr_arm
        end
        s_tvalid = 0;
        repeat (4) @(negedge aclk);
        clear_forces();
        flag = err_corr || err_det || fsm_fault || wd_fault || tmr_fault;
        completed = (ndone > 0);
        wrong = bad_out || (n_out != L) || (checksum !== expsum) || (ndone != 1);
        if (!completed) begin if (flag) cnt_det++; else cnt_hang++; end
        else if (!wrong) begin if (flag) cnt_corr++; else cnt_masked++; end
        else begin if (flag) cnt_det++; else cnt_silent++; end
    endtask

    initial begin
        if (!$value$plusargs("target=%s", target)) target = "none";
        if (!$value$plusargs("trials=%d", trials)) trials = 100;
        if (!$value$plusargs("seed=%d", seed)) seed = 1;
        ecc_prim = (`ECC_VAL == 2);
        tcode = (target == "state") ? 1 : (target == "ram") ? 2 : (target == "ram2") ? 3 : (target == "cnt") ? 4 : (target == "cnt2") ? 5 : (target == "bus") ? 6 : 0;
        rs = seed;
        repeat (4) @(negedge aclk);
        for (int i = 0; i < trials; i++) trial(rr(24, 8), target != "none");
        $display("RESULT target=%s ecc=%0d tmr=%0d trials=%0d seed=%0d masked=%0d corrected=%0d detected=%0d silent=%0d hang=%0d",
                 target, `ECC_VAL, `TMR_ON, trials, seed, cnt_masked, cnt_corr, cnt_det, cnt_silent, cnt_hang);
        $finish;
    end
endmodule
