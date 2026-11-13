// formal_mdio.sv: drives rtl/mdio_master.sv freely (DIV = 2 keeps the state space small) after one reset clock;
// the properties are in the RTL's `ifdef FORMAL block.
module formal_mdio (
    input logic        clk,
    input logic        go, rd, mdio_i,
    input logic [4:0]  phy, reg_a,
    input logic [15:0] wdata
);
    logic f_past = 1'b0;
    always_ff @(posedge clk) f_past <= 1'b1;
    logic [15:0] rdata;
    logic busy, mdc, mdio_o, mdio_t;
    mdio_master #(.DIV(2)) dut (.clk, .rst(!f_past), .go, .rd, .phy, .reg_a, .wdata, .rdata, .busy, .mdc, .mdio_o,
                                .mdio_t, .mdio_i);
endmodule
