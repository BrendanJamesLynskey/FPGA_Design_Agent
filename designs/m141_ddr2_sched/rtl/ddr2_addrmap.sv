// ddr2_addrmap.sv (brief 141): burst address -> {row, bank, burst column} for a x16 DDR2 part, three maps. Purely combinational.
//
// A "burst address" counts BL8 bursts (16 bytes on a x16 part): the 128 MiB MT47H64M16 has 2**23 of them = 13 row bits + 3 bank bits + 7 burst-column bits (a 2 KiB page holds 128 bursts).
//   MAP 0  {row, bank, col}          page-interleaved: a sequential stream stays in one row for 128 bursts, then moves to the next bank (row-hit rate highest, no overlap of row cycles)
//   MAP 1  {row, col_hi, bank, col_lo} sequential bursts stay in a bank for 2**LO bursts, then rotate through the banks (hits and bank overlap)
//   MAP 2  {row, col, bank}          every burst goes to the next bank (maximum bank interleave, one row hit per bank per visit)
module ddr2_addrmap #(
    parameter int MAP = 0,
    parameter int RW  = 13,
    parameter int BW  = 3,
    parameter int CB  = 7,
    parameter int LO  = 3       // MAP 1: sequential bursts kept in a bank (2**LO); 0 < LO < CB
) (
    input  logic [RW+BW+CB-1:0] addr,
    output logic [BW-1:0]       bank,
    output logic [RW-1:0]       row,
    output logic [CB-1:0]       col
);
    if (MAP == 0) begin : g_m0
        assign col  = addr[CB-1:0];
        assign bank = addr[CB+BW-1:CB];
    end else if (MAP == 1) begin : g_m1
        assign col  = {addr[CB+BW-1:LO+BW], addr[LO-1:0]};
        assign bank = addr[LO+BW-1:LO];
    end else begin : g_m2
        assign bank = addr[BW-1:0];
        assign col  = addr[CB+BW-1:BW];
    end
    assign row = addr[RW+BW+CB-1:CB+BW];
endmodule
