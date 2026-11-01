// Deliberately non-portable: a covergroup. Verilator 5.020 rejects it (Unsupported: covergroup);
// Icarus 12 does not parse it either. Used only by flow/tests/test_portability.py.
module nonportable_covergroup (input logic clk, input logic [3:0] a);
    covergroup cg @(posedge clk);
        coverpoint a;
    endgroup
    cg cg_i = new;
endmodule
