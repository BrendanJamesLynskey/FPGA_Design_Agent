// Glitch-free clock mux for two synchronous clocks (fixed phase).
// Enables are mutually exclusive: each is set only when the other,
// seen from its own clock domain, is already off. Reset is synchronous for
// the enable flops; clkout is additionally gated by rst_n so that rst_n low
// still forces clkout low asynchronously (spec REQ-09).
module glitch_free_mux (
    input  logic clk1,
    input  logic clk2,
    input  logic rst_n,
    input  logic sel,
    output logic clkout
);

    logic en1;
    logic en2;

    // clk1 enable: on when sel=0 and clk2 path is off
    always_ff @(posedge clk1) begin
        if (!rst_n) en1 <= 1'b0;
        else        en1 <= ~sel & ~en2;
    end

    // clk2 enable: on when sel=1 and clk1 path is off
    always_ff @(posedge clk2) begin
        if (!rst_n) en2 <= 1'b0;
        else        en2 <= sel & ~en1;
    end

    assign clkout = rst_n & ((clk1 & en1) | (clk2 & en2));

endmodule
