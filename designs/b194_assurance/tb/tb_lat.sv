// tb_lat.sv: latency of the development design, in clocks, from the clock edge that accepts the first word on the slave stream to the first clock
// edge at which m_axis_tvalid is high (output always ready, one burst of one word). Prints "LAT <n>". Ports only.
`timescale 1ns/1ps
`ifndef DUT_PARAMS
`define DUT_PARAMS
`endif
module tb_lat;
    logic aclk = 0, aresetn = 0, start = 0, s_tvalid = 0, s_tready, m_tvalid;
    logic [15:0] len = 0;
    logic [63:0] m_tdata, checksum;
    logic busy, done, err_corr, err_det, fsm_fault, wd_fault, tmr_fault;
    a194_core `DUT_PARAMS dut (.aclk(aclk), .aresetn(aresetn), .start(start), .len(len), .s_axis_tdata(64'h1234), .s_axis_tvalid(s_tvalid), .s_axis_tready(s_tready),
        .m_axis_tdata(m_tdata), .m_axis_tvalid(m_tvalid), .m_axis_tready(1'b1), .busy(busy), .done(done), .checksum(checksum), .err_corr(err_corr),
        .err_det(err_det), .fsm_fault(fsm_fault), .wd_fault(wd_fault), .tmr_fault(tmr_fault), .dbg_inj_s(1'b0), .dbg_inj_d(1'b0));
    always #5 aclk = ~aclk;
    int n = 0, acc_at = -1, out_at = -1, cyc = 0;
    always @(posedge aclk) begin
        cyc <= cyc + 1;
        if (s_tvalid && s_tready && acc_at < 0) acc_at <= cyc;
        if (m_tvalid && out_at < 0) out_at <= cyc;
    end
    initial begin
        repeat (4) @(negedge aclk); aresetn = 1; repeat (2) @(negedge aclk);
        len = 1; start = 1; @(negedge aclk); start = 0;
        s_tvalid = 1;
        repeat (40) @(negedge aclk);
        $display("LAT %0d", out_at - acc_at);
        $finish;
    end
endmodule
