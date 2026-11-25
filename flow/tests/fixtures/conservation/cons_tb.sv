// Testbench for cons_filter with the fda_conservation helper. +MUTANT=1 selects the silent-drop mutant; prints CONS_PASS or CONS_FAIL.
module cons_tb;
    logic clk = 0, rst = 1;
    always #5 clk = ~clk;
    logic in_valid = 0, in_bad = 0, out_ready = 0;
    logic [15:0] in_data = 0;
    wire out_valid;
    wire [15:0] out_data;
    wire [31:0] drop_count, occupancy;
    wire violation;
    wire [31:0] n_in, n_out, first_bad_in;
    int mutant;
    // both variants are built; the plusarg chooses which one the checker watches
    wire ov0, ov1; wire [15:0] od0, od1; wire [31:0] dc0, dc1, oc0, oc1;
    cons_filter #(.SILENT_DROP(0)) good (.clk, .rst, .in_valid, .in_bad, .in_data, .out_valid(ov0), .out_ready, .out_data(od0), .drop_count(dc0), .occupancy(oc0));
    cons_filter #(.SILENT_DROP(1)) bad  (.clk, .rst, .in_valid, .in_bad, .in_data, .out_valid(ov1), .out_ready, .out_data(od1), .drop_count(dc1), .occupancy(oc1));
    initial if (!$value$plusargs("MUTANT=%d", mutant)) mutant = 0;
    assign out_valid  = mutant ? ov1 : ov0;
    assign out_data   = mutant ? od1 : od0;
    assign drop_count = mutant ? dc1 : dc0;
    assign occupancy  = mutant ? oc1 : oc0;
    fda_conservation #(.W(32)) chk (.clk, .rst, .frame_in(in_valid), .frame_out(out_valid && out_ready),
                                    .drop_count, .in_flight(occupancy), .violation, .n_in, .n_out, .first_bad_in);
    int seed;
    initial begin
        if (!$value$plusargs("SEED=%d", seed)) seed = 1;
        void'($urandom(seed));
        repeat (4) @(posedge clk);
        rst <= 0;
        repeat (4000) begin
            @(posedge clk);
            #1;
            in_valid  = ($urandom % 100) < 70;
            in_bad    = ($urandom % 100) < 10;
            in_data   = $urandom;
            out_ready = ($urandom % 100) < 40;        // slower than the input: the FIFO fills and drops
        end
        @(posedge clk); #1;
        if (violation) $display("CONS_FAIL in=%0d out=%0d dropped=%0d first_bad_in=%0d", n_in, n_out, drop_count, first_bad_in);
        else           $display("CONS_PASS in=%0d out=%0d dropped=%0d", n_in, n_out, drop_count);
        $finish;
    end
endmodule
