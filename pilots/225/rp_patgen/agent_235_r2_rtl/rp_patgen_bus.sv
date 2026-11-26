// rp_patgen_bus: register-bus front end. One access per clock.
// Decodes sys_addr[19:0] to a word index, answers holes, unaligned offsets,
// offsets from 0x80 up and writes to read-only registers with sys_err, and
// registers sys_ack, sys_err and sys_rdata one clock after the access.
// rst is active high (inverted once in the top).
module rp_patgen_bus (
    input  logic        clk,
    input  logic        rst,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] sys_addr,   // bits 31 to 20 ignored (1 MiB window)
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic        sys_wen,
    input  logic        sys_ren,
    input  logic [31:0] rd_val,
    output logic [4:0]  idx,
    output logic        wr_en,
    output logic [31:0] sys_rdata,
    output logic        sys_err,
    output logic        sys_ack
);
    // word index of the offset: offsets below 0x80 only
    wire       aligned = (sys_addr[1:0] == 2'b00);
    wire       inwin   = (sys_addr[19:7] == 13'd0);
    wire       hole    = (sys_addr[6:2] == 5'd14) | (sys_addr[6:2] == 5'd15);
    wire       mapped  = inwin & aligned & ~hole;
    // ID (0x00), STATUS (0x28) and PERIODS_DONE (0x2C) are read-only
    wire       ro      = (sys_addr[6:2] == 5'd0) | (sys_addr[6:2] == 5'd10) |
                         (sys_addr[6:2] == 5'd11);
    wire       acc     = sys_wen | sys_ren;
    wire       err_c   = acc & (~mapped | (sys_wen & ro));

    assign idx    = sys_addr[6:2];
    assign wr_en  = sys_wen & mapped & ~ro;

    always_ff @(posedge clk) begin
        if (rst) begin
            sys_ack   <= 1'b0;
            sys_err   <= 1'b0;
            sys_rdata <= 32'd0;
        end else begin
            sys_ack   <= acc;
            sys_err   <= err_c;
            sys_rdata <= mapped ? rd_val : 32'd0;
        end
    end
endmodule
