// a194_fifo.sv: 512 x 64 synchronous FIFO with a registered read (data one clock after rd_en), optional ECC (brief 194).
//   ECC = 0  plain inferred block RAM
//   ECC = 1  fabric SECDED: a 72-bit word per entry (a194_secded_pkg), corrected after the read register
//   ECC = 2  the RAMB36E1 built-in ECC in simple dual port mode (UG473 ch. 3 "Built-in Error Correction"): 512 x 64 data plus 8 check bits
// Behaviour a user could guess wrong: a single-bit error is corrected on the output, never in the array (UG473); a second flip of the same
// word before it is rewritten is a double error (sbit/dbit are flags, valid with rd_vld). The inj_* inputs are test inputs: with ECC = 2 they
// are the primitive's INJECTSBITERR/INJECTDBITERR (an error created in the word written on that clock, bit DI[30] and DI[62]); otherwise unused.
`ifdef A194_FI
`define A194_FIW(name, width) wire [width-1:0] name = '0;
`else
`define A194_FIW(name, width) localparam logic [width-1:0] name = '0;
`endif
module a194_fifo #(
    parameter int ECC = 0
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        wr_en,
    input  logic [63:0] wr_data,
    input  logic        rd_en,
    output logic [63:0] rd_data,      // valid when rd_vld
    output logic        rd_vld,
    output logic        full,
    output logic        empty,
    output logic        sbit,         // single-bit error corrected on this read (ECC > 0)
    output logic        dbit,         // double-bit error detected on this read (ECC > 0); the data is not corrected
    input  logic        inj_s,
    input  logic        inj_d
);
    `A194_FIW(fi_wmask, 72)       // simulation hook: XORed into the word stored by a write (an upset of the stored bits), ECC = 0 or 1
    logic [9:0] wptr, rptr;
    assign empty = (wptr == rptr);
    assign full  = (wptr[8:0] == rptr[8:0]) && (wptr[9] != rptr[9]);

    wire do_wr = wr_en && !full;
    wire do_rd = rd_en && !empty;

    always_ff @(posedge clk) begin
        if (rst) begin
            wptr   <= '0;
            rptr   <= '0;
            rd_vld <= 1'b0;
        end else begin
            if (do_wr) wptr <= wptr + 1'b1;
            if (do_rd) rptr <= rptr + 1'b1;
            rd_vld <= do_rd;
        end
    end

    if (ECC == 2) begin : g_prim
        logic [31:0] doa, dob;
        logic        sb, db;
        RAMB36E1 #(
            .RAM_MODE("SDP"), .READ_WIDTH_A(72), .WRITE_WIDTH_B(72), .DOA_REG(0), .DOB_REG(0),
            .EN_ECC_READ("TRUE"), .EN_ECC_WRITE("TRUE"), .RDADDR_COLLISION_HWCONFIG("DELAYED_WRITE"), .SIM_COLLISION_CHECK("ALL")
        ) u_ram (
            .CLKARDCLK(clk), .CLKBWRCLK(clk),
            .ENARDEN(do_rd), .ENBWREN(do_wr),
            .REGCEAREGCE(1'b0), .REGCEB(1'b0), .RSTRAMARSTRAM(1'b0), .RSTRAMB(1'b0), .RSTREGARSTREG(1'b0), .RSTREGB(1'b0),
            .CASCADEINA(1'b0), .CASCADEINB(1'b0),
            .INJECTSBITERR(inj_s), .INJECTDBITERR(inj_d),
            .ADDRARDADDR({1'b1, rptr[8:0], 6'b0}), .ADDRBWRADDR({1'b1, wptr[8:0], 6'b0}),
            .DIADI(wr_data[31:0]), .DIBDI(wr_data[63:32]), .DIPADIP(4'b0), .DIPBDIP(4'b0),
            .WEA(4'b0), .WEBWE(8'hFF),
            .DOADO(doa), .DOBDO(dob), .DOPADOP(), .DOPBDOP(), .ECCPARITY(), .RDADDRECC(), .SBITERR(sb), .DBITERR(db),
            .CASCADEOUTA(), .CASCADEOUTB()
        );
        assign rd_data = {dob, doa};
        assign sbit = sb && rd_vld;
        assign dbit = db && rd_vld;
    end else if (ECC == 1) begin : g_fabric
        (* ram_style = "block" *) logic [71:0] mem [0:511];
        logic [71:0] raw;
        always_ff @(posedge clk) begin
            if (do_wr) mem[wptr[8:0]] <= a194_secded_pkg::encode(wr_data) ^ fi_wmask;
            if (do_rd) raw <= mem[rptr[8:0]];
        end
        wire [65:0] dec = a194_secded_pkg::decode(raw);
        assign rd_data = dec[63:0];
        assign sbit    = dec[64] && rd_vld;
        assign dbit    = dec[65] && rd_vld;
    end else begin : g_plain
        (* ram_style = "block" *) logic [63:0] mem [0:511];
        logic [63:0] raw;
        always_ff @(posedge clk) begin
            if (do_wr) mem[wptr[8:0]] <= wr_data ^ fi_wmask[63:0];
            if (do_rd) raw <= mem[rptr[8:0]];
        end
        assign rd_data = raw;
        assign sbit = 1'b0;
        assign dbit = 1'b0;
    end
endmodule
