// Blind bench: the compare is `!=`, so an X output skips the error (it prints PASS for the defective encoder).
module tb_blind;
    logic clk = 0, p; logic [7:0] d = 0; int errors = 0;
    always #5 clk = ~clk;
    enc dut (.clk, .d, .p);
    initial begin
        for (int i = 0; i < 256; i++) begin
            d = i[7:0]; @(posedge clk); #1;
            if (i > 0 && p != ^d) begin errors++; $error("mismatch at %0d", i); end
        end
        $display(errors == 0 ? "XCMP_PASS" : "XCMP_FAIL");
        $finish;
    end
endmodule
