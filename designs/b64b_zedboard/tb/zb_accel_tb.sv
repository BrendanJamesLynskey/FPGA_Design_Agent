// Self-checking testbench for zb_accel (Icarus): CRC-32 and FIR packets driven through the real register block, with random
// stream stalls on both sides. Prints "TB PASS" or "TB FAIL ...". Run: sim/run_tb.sh (iverilog -g2012).
`timescale 1ns/1ps
module zb_accel_tb;
    logic aclk = 0, aresetn = 0;
    always #5 aclk = ~aclk;
    logic [11:0] awaddr, araddr; logic awvalid, awready, wvalid, wready, bvalid, bready = 1, arvalid, arready, rvalid, rready = 1;
    logic [31:0] wdata, rdata; logic [1:0] bresp, rresp;
    logic [31:0] sd, md; logic sl, sv, sr, ml, mv, mr; logic [3:0] mk;
    zb_accel dut (.aclk, .aresetn, .s_axil_awaddr(awaddr), .s_axil_awprot(3'b0), .s_axil_awvalid(awvalid), .s_axil_awready(awready),
        .s_axil_wdata(wdata), .s_axil_wstrb(4'hF), .s_axil_wvalid(wvalid), .s_axil_wready(wready), .s_axil_bresp(bresp),
        .s_axil_bvalid(bvalid), .s_axil_bready(bready), .s_axil_araddr(araddr), .s_axil_arprot(3'b0), .s_axil_arvalid(arvalid),
        .s_axil_arready(arready), .s_axil_rdata(rdata), .s_axil_rresp(rresp), .s_axil_rvalid(rvalid), .s_axil_rready(rready),
        .s_axis_tdata(sd), .s_axis_tkeep(4'hF), .s_axis_tlast(sl), .s_axis_tvalid(sv), .s_axis_tready(sr),
        .m_axis_tdata(md), .m_axis_tkeep(mk), .m_axis_tlast(ml), .m_axis_tvalid(mv), .m_axis_tready(mr));
    task automatic wr(input [11:0] a, input [31:0] d);
        @(posedge aclk); awaddr <= a; wdata <= d; awvalid <= 1; wvalid <= 1;
        fork begin wait (awready); end begin wait (wready); end join
        @(posedge aclk); awvalid <= 0; wvalid <= 0; wait (bvalid); @(posedge aclk);
    endtask
    task automatic rd(input [11:0] a, output [31:0] d);
        @(posedge aclk); araddr <= a; arvalid <= 1; wait (arready); @(posedge aclk); arvalid <= 0; wait (rvalid); d = rdata; @(posedge aclk);
    endtask
    function automatic [31:0] crc_ref(input [31:0] words [], input int n);
        logic [31:0] c, ww; c = '1;
        for (int w = 0; w < n; w++) begin ww = words[w]; for (int i = 0; i < 32; i++) c = (c >> 1) ^ ((c[0] ^ ww[i]) ? 32'hEDB88320 : 0); end
        return ~c;
    endfunction
    int errors = 0;
    logic [31:0] inw [];
    logic [31:0] outw [$];
    logic [31:0] v;
    initial begin
        awvalid = 0; wvalid = 0; arvalid = 0; sv = 0; sl = 0; sd = 0; mr = 0;
        repeat (4) @(posedge aclk); aresetn = 1; repeat (4) @(posedge aclk);
        rd(12'h000, v); if (v !== 32'h64B30100) begin $display("TB FAIL ID %h", v); errors++; end
        for (int run = 0; run < 8; run++) begin
            int n; int mode; logic signed [11:0] h [16]; logic signed [15:0] x;
            n = (run == 0) ? 1 : 5 + $urandom_range(0, 60); mode = run % 2;
            inw = new[n]; outw.delete();
            for (int i = 0; i < n; i++) inw[i] = $urandom;
            wr(12'h004, mode);
            for (int k = 0; k < 16; k++) begin h[k] = $urandom; wr(12'h040 + 4*k, {20'b0, h[k]}); end
            wr(12'h008, 1);
            fork
                begin : feed
                    for (int i = 0; i < n; i++) begin
                        while ($urandom_range(0, 3) == 0) @(posedge aclk);
                        sd <= inw[i]; sl <= (i == n-1); sv <= 1; @(posedge aclk); while (!sr) @(posedge aclk); sv <= 0;
                    end
                end
                begin : drain
                    int need; int got; need = mode ? n : 1; got = 0;
                    while (got < need) begin
                        mr <= ($urandom_range(0, 2) != 0); @(posedge aclk);
                        if (mv && mr) begin outw.push_back(md); got++; if (ml !== (got == need)) begin $display("TB FAIL tlast at %0d/%0d", got, need); errors++; end end
                    end
                    mr <= 0;
                end
            join
            repeat (5) @(posedge aclk);
            if (mode == 0) begin
                if (outw[0] !== crc_ref(inw, n)) begin $display("TB FAIL crc run %0d: got %h want %h", run, outw[0], crc_ref(inw, n)); errors++; end
            end else begin
                for (int i = 0; i < n; i++) begin
                    longint acc; logic [31:0] tmp; acc = 0;
                    for (int k = 0; k < 16; k++) if (i - k >= 0) begin tmp = inw[i-k]; x = tmp[15:0]; acc += longint'(h[k]) * longint'(x); end
                    if ($signed(outw[i]) !== int'(acc)) begin $display("TB FAIL fir run %0d [%0d]: got %0d want %0d", run, i, $signed(outw[i]), acc); errors++; end
                end
            end
            rd(12'h00C, v); if (v[0] !== 0) begin $display("TB FAIL still busy"); errors++; end
            rd(12'h010, v); $display("run %0d mode %0d n %0d job_cycles %0d", run, mode, n, v);
        end
        if (errors == 0) $display("TB PASS"); else $display("TB FAIL %0d errors", errors);
        $finish;
    end
    initial begin #2000000; $display("TB FAIL timeout"); $finish; end
endmodule
