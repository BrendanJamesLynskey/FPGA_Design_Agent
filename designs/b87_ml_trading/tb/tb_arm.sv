// tb_arm.sv: streams every test-split feature vector through one arm and checks each class against the Python
// integer model; records the latency (in_v to out_v, in clocks) of every sample.
//   iverilog -g2012 -DARM=<module> -o sim tb_arm.sv <arm>.sv ; vvp sim +VEC=<vectors.hex> +N=<count> +OUT=<summary>
// <vectors.hex>: one line per sample, {2-bit expected class, 38-bit features} as 10 hex digits.
// The first half of the samples go in back to back (one a clock: initiation interval 1); the second half with
// pseudo-random gaps of 0 to 3 clocks, so a latency that depended on the input or on the spacing would show.
`timescale 1ns/1ps
module tb_arm;
    localparam int MAXN = 200000;
    logic clk = 0, rst = 1, in_v = 0, out_v;
    logic [37:0] in_f = '0;
    logic [1:0] out_cls;
    logic [39:0] vec [MAXN];
    int issue [MAXN];
    int n, ni = 0, no = 0, cyc = 0, bad = 0, lmin = 1 << 30, lmax = 0, fd, gap = 0;
    logic [15:0] lfsr = 16'hACE1;
    string vf, of;
    `ARM dut (.clk, .rst, .in_v, .in_f, .out_v, .out_cls);
    always #1 clk = ~clk;
    always @(posedge clk) cyc <= cyc + 1;
    initial begin
        if (!$value$plusargs("VEC=%s", vf)) $fatal(1, "no +VEC");
        if (!$value$plusargs("N=%d", n)) $fatal(1, "no +N");
        if (!$value$plusargs("OUT=%s", of)) of = "tb_arm_summary.txt";
        $readmemh(vf, vec, 0, n - 1);
        repeat (4) @(posedge clk);
        rst <= 0;
        @(posedge clk);
        while (ni < n) begin
            @(posedge clk);
            lfsr <= {lfsr[14:0], lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10]};
            if (gap > 0) begin
                in_v <= 0; gap <= gap - 1;
            end else begin
                in_v <= 1; in_f <= vec[ni][37:0]; issue[ni] = cyc + 1; ni = ni + 1;
                gap <= (ni > n / 2) ? int'(lfsr[1:0]) : 0;
            end
        end
        @(posedge clk) in_v <= 0;
        repeat (64) @(posedge clk);
        fd = $fopen(of, "w");
        $fwrite(fd, "n %0d out %0d mismatches %0d latency_min %0d latency_max %0d\n", n, no, bad, lmin, lmax);
        $fclose(fd);
        $display("tb_arm: n %0d out %0d mismatches %0d latency_min %0d latency_max %0d", n, no, bad, lmin, lmax);
        $finish;
    end
    always @(posedge clk) begin
        if (!rst && out_v) begin
            if (out_cls !== vec[no][39:38]) begin
                if (bad < 5) $display("mismatch at %0d: got %0d want %0d", no, out_cls, vec[no][39:38]);
                bad <= bad + 1;
            end
            if (cyc - issue[no] < lmin) lmin <= cyc - issue[no];
            if (cyc - issue[no] > lmax) lmax <= cyc - issue[no];
            no <= no + 1;
        end
    end
endmodule
