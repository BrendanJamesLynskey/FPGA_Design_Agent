// tb_pe.sv: streams feature vectors through a partial-evaluation block (rtl/gen/*_pe*.sv) with the early features
// first and the late feature FILL clocks or more afterwards, and checks every class against the Python integer model.
//   iverilog -g2012 -DDUT=<module> -o sim tb_pe.sv <block>.sv ; vvp sim +VEC=<hex> +N=<count> +OUT=<summary>
// <hex>: one line per sample, {2-bit expected class, 38-bit features} as 10 hex digits (the late bits sit in the packed
// features; the bench sends them on l_x and zeroes them in e_f, so a block that read them early would fail).
// Schedule (te = clock of e_v, tl = clock of l_v):
//   first half   back to back, one sample a clock, tl = te + FILL (the tightest legal use, initiation interval 1);
//   second half  te >= the previous tl (the table is rewritten FILL clocks later), tl = te + FILL + 0..3, gaps 0..2.
// Latency checked: out_v exactly 1 clock after l_v, for every sample.
`timescale 1ns/1ps
module tb_pe;
    localparam int MAXN = 200000;
    logic clk = 0, rst = 1, e_v = 0, l_v = 0, out_v;
    logic [37:0] e_f = '0;
    logic [7:0] l_x = '0;
    logic [1:0] out_cls;
    logic [39:0] vec [MAXN];
    int te [MAXN];
    int tl [MAXN];
    int n, ie = 0, il = 0, no = 0, cyc = 0, bad = 0, badlat = 0, fd, fill;
    logic [15:0] lfsr = 16'hACE1;
    string vf, of;
    `DUT dut (.clk, .rst, .e_v, .e_f, .l_v, .l_x, .out_v, .out_cls);
    always #1 clk = ~clk;
    always @(posedge clk) cyc <= cyc + 1;
    function automatic int rnd(input int m);
        lfsr = {lfsr[14:0], lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10]};
        return int'(lfsr[7:0]) % m;
    endfunction
    initial begin
        if (!$value$plusargs("VEC=%s", vf)) $fatal(1, "no +VEC");
        if (!$value$plusargs("N=%d", n)) $fatal(1, "no +N");
        if (!$value$plusargs("OUT=%s", of)) of = "tb_pe_summary.txt";
        fill = dut.FILL;
        $readmemh(vf, vec, 0, n - 1);
        for (int i = 0; i < n; i++) begin
            if (i < n / 2) begin
                te[i] = 8 + i; tl[i] = te[i] + fill;
            end else begin
                te[i] = tl[i-1] + rnd(3);
                tl[i] = te[i] + fill + rnd(4);
            end
        end
        repeat (4) @(posedge clk);
        rst <= 0;
        while (cyc <= tl[n-1] + 8) @(posedge clk);
        fd = $fopen(of, "w");
        $fwrite(fd, "n %0d out %0d mismatches %0d latency_bad %0d fill %0d\n", n, no, bad, badlat, fill);
        $fclose(fd);
        $display("tb_pe: n %0d out %0d mismatches %0d latency_bad %0d fill %0d", n, no, bad, badlat, fill);
        $finish;
    end
    // driver: the schedule is in clock numbers (cyc); signals change after the edge
    always @(posedge clk) begin
        e_v <= 0; l_v <= 0;
        // after reset the schedule starts at 8
        if (!rst) begin
            if (ie < n && te[ie] == cyc + 1) begin
                e_v <= 1; e_f <= vec[ie][37:0] & 38'h300FFFFFFF;
                ie <= ie + 1;
            end
            if (il < n && tl[il] == cyc + 1) begin
                l_v <= 1; l_x <= vec[il][35:28];
                il <= il + 1;
            end
        end
    end
    always @(posedge clk) begin
        if (!rst && out_v) begin
            if (out_cls !== vec[no][39:38]) begin
                if (bad < 5) $display("mismatch at %0d: got %0d want %0d", no, out_cls, vec[no][39:38]);
                bad <= bad + 1;
            end
            if (cyc - tl[no] != 1 + 0) begin
                if (badlat < 5) $display("latency at %0d: %0d", no, cyc - tl[no]);
                badlat <= badlat + 1;
            end
            no <= no + 1;
        end
    end
endmodule
