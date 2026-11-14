// resp_rules_tb: seeded faults for axil_resp_rules (brief 71). MODE 0: a clean slave (one B per write, one R per read,
// 1-6 clocks late); 1: the AXI DMA register port's fault (brief 69: a second write accepted while the first B waits, one
// B for both); 2: a read accepted and never answered; 3: a legal slave just inside the bound (B after TIMEOUT-1 clocks).
// Prints "RESULT lost_w=<n> lost_r=<n>" (cycles with each bit high) and finishes.
`timescale 1ns/1ps
module resp_rules_tb;
    parameter int MODE = 0;
    localparam int TIMEOUT = 32;
    logic aclk = 0, aresetn = 0;
    always #5 aclk = ~aclk;
    logic awvalid = 0, awready = 0, wvalid = 0, wready = 0, bvalid = 0, bready = 1;
    logic arvalid = 0, arready = 0, rvalid = 0, rready = 1;
    logic [1:0] lost;
    axil_resp_rules #(.TIMEOUT(TIMEOUT)) dut (.*);
    int lost_w = 0, lost_r = 0;
    always @(posedge aclk) begin
        if (lost[0]) lost_w++;
        if (lost[1]) lost_r++;
    end
    task automatic write_req();       // AW and W together, held until accepted (the slave below accepts at once)
        @(posedge aclk); awvalid <= 1; wvalid <= 1; awready <= 1; wready <= 1;
        @(posedge aclk); awvalid <= 0; wvalid <= 0; awready <= 0; wready <= 0;
    endtask
    task automatic b_resp(int dly);
        repeat (dly) @(posedge aclk);
        bvalid <= 1; @(posedge aclk); bvalid <= 0;
    endtask
    task automatic read(int dly, bit answer);
        @(posedge aclk); arvalid <= 1; arready <= 1;
        @(posedge aclk); arvalid <= 0; arready <= 0;
        if (answer) begin repeat (dly) @(posedge aclk); rvalid <= 1; @(posedge aclk); rvalid <= 0; end
    endtask
    initial begin
        repeat (3) @(posedge aclk);
        aresetn <= 1;
        for (int i = 0; i < 8; i++) begin
            if (MODE == 3) begin write_req(); b_resp(TIMEOUT - 1); end
            else begin write_req(); b_resp(1 + (i % 6)); end
            read(1 + (i % 5), 1);
        end
        if (MODE == 1) begin write_req(); write_req(); b_resp(2); end      // two writes accepted, one B
        if (MODE == 2) read(0, 0);                                         // a read never answered
        repeat (3 * TIMEOUT) @(posedge aclk);
        $display("RESULT lost_w=%0d lost_r=%0d", lost_w, lost_r);
        $finish;
    end
endmodule
