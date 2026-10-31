// tmp_regs.sv: the temperature-sensor self-check's registers in the test
// shell's window (offsets from 0x80), around i2c_ptr_read.
//
//   0x00 CTRL    W: [0] GO, [15:8] register pointer, [17:16] bytes to read (2 = two, else one)
//                R: the last pointer and byte count written
//   0x01 STATUS  R: [0] busy, [1] done, [2] nack
//   0x02 RDATA   R: [15:0] the bytes read (2-byte read: first byte in [15:8])
//   0x03 INFO    R: [22:16] device address, [15:0] QUARTER
//   other        R: 0

module tmp_regs #(
    parameter int         QUARTER  = 250,
    parameter logic [6:0] DEV_ADDR = 7'h4B
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,      // only [17:8] and [0] are used
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic        scl_oe,
    output logic        sda_oe,
    input  logic        scl_in,
    input  logic        sda_in
);
    logic        go, busy, done, nack;
    logic [7:0]  ptr;
    logic [1:0]  nbytes;
    logic [15:0] rdata;

    always_ff @(posedge clk) begin
        if (rst) begin
            go <= 1'b0; ptr <= '0; nbytes <= 2'd1; win_rdata <= '0;
        end else begin
            go <= 1'b0;
            if (win_wr && win_addr == 7'h00) begin
                ptr    <= win_wdata[15:8];
                nbytes <= win_wdata[17:16];
                go     <= win_wdata[0];
            end
            if (win_rd) begin
                unique case (win_addr)
                    7'h00:   win_rdata <= {14'd0, nbytes, ptr, 8'd0};
                    7'h01:   win_rdata <= {29'd0, nack, done, busy};
                    7'h02:   win_rdata <= {16'd0, rdata};
                    7'h03:   win_rdata <= {9'd0, DEV_ADDR, 16'(QUARTER)};
                    default: win_rdata <= '0;
                endcase
            end
        end
    end

    i2c_ptr_read #(.QUARTER(QUARTER), .DEV_ADDR(DEV_ADDR)) u_i2c (
        .clk(clk), .rst(rst), .go(go), .ptr(ptr), .nbytes(nbytes),
        .busy(busy), .done(done), .nack(nack), .rdata(rdata),
        .scl_oe(scl_oe), .sda_oe(sda_oe), .scl_in(scl_in), .sda_in(sda_in));
endmodule
