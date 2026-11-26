// tb_mul_pipe (brief 185): random operands against dsp_mul_pipe; the latency must equal NA + NM + NP. (latency = register stages from the inputs to the output; the bench samples at the falling edge, so it adds 1 to the offset it finds)
module tb_mul_pipe;
    parameter int WA = 18, WB = 18, NA = 1, NM = 1, NP = 1, RSTP = 0, N = 1000;
    logic clk = 0, rst = 0;
    logic signed [WA-1:0] a;
    logic signed [WB-1:0] b;
    logic signed [WA+WB-1:0] p;
    dsp_mul_pipe #(.WA(WA), .WB(WB), .NA(NA), .NM(NM), .NP(NP), .RSTP(RSTP)) dut (.clk(clk), .rst(rst), .a(a), .b(b), .p(p));
    always #5 clk = ~clk;
    logic signed [WA+WB-1:0] exp_h [0:N+10], got_h [0:N+10];
    integer t, lat, bad [0:7], k;
    initial begin
        for (k = 0; k < 8; k++) bad[k] = 0;
        for (t = 0; t < N + 6; t++) begin
            if (t < N) begin a = $urandom; b = $urandom; exp_h[t] = a * b; end
            @(negedge clk);
            got_h[t] = p;
        end
        for (lat = 0; lat < 6; lat++) for (t = 10; t < N; t++) if (got_h[t + lat] !== exp_h[t]) bad[lat]++;
        for (lat = 0; lat < 6; lat++) if (bad[lat] == 0) $display("MATCH NA=%0d NM=%0d NP=%0d RSTP=%0d latency=%0d", NA, NM, NP, RSTP, lat + 1);
        $finish;
    end
endmodule
