// tb_dot (brief 185): random operands against dsp_dot; prints the latency at which y matches. (latency = register stages from the inputs to the output; the bench samples at the falling edge, so it adds 1 to the offset it finds)
module tb_dot;
    parameter int W = 16, K = 8, STYLE = 0, TR = 1, N = 2000;
    localparam int OW = 2*W + $clog2(K);
    logic clk = 0;
    logic signed [K*W-1:0] a, b;
    logic signed [OW-1:0] y;
    dsp_dot #(.W(W), .K(K), .STYLE(STYLE), .TR(TR)) dut (.clk(clk), .a(a), .b(b), .y(y));
    always #5 clk = ~clk;
    logic signed [OW-1:0] exp_h [0:N+30], got_h [0:N+30];
    integer t, lat, k, bad [0:31];
    logic signed [OW-1:0] s;
    initial begin
        for (k = 0; k < 32; k++) bad[k] = 0;
        for (t = 0; t < N + 24; t++) begin
            if (t < N) begin
                for (k = 0; k < K*W; k += 32) begin a[k +: 32] = $urandom; b[k +: 32] = $urandom; end
                s = 0;
                for (k = 0; k < K; k++) s = s + $signed(a[k*W +: W]) * $signed(b[k*W +: W]);
                exp_h[t] = s;
            end
            @(negedge clk);
            got_h[t] = y;
        end
        for (lat = 0; lat < 24; lat++)
            for (t = 40; t < N; t++) if (got_h[t + lat] !== exp_h[t]) bad[lat]++;
        for (lat = 0; lat < 24; lat++) if (bad[lat] == 0) $display("MATCH W=%0d K=%0d STYLE=%0d TR=%0d latency=%0d", W, K, STYLE, TR, lat + 1);
        $finish;
    end
endmodule
