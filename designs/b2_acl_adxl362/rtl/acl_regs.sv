// acl_regs.sv: the accelerometer self-check's registers in the test shell's
// window (offsets from 0x80), around spi_burst.
//
//   0x00 CTRL    W: [0] GO, [11:8] bytes in the transfer (1..8); R: the byte count
//   0x01 STATUS  R: [0] busy, [1] done
//   0x02 TX0     RW: bytes 0-3 to send (byte 0 in [7:0], sent first)
//   0x03 TX1     RW: bytes 4-7
//   0x04 RX0     R: bytes 0-3 received (byte 0 in [7:0])
//   0x05 RX1     R: bytes 4-7
//   0x06 INFO    R: [15:0] HALF (SCLK half period in clocks)
//   other        R: 0

module acl_regs #(
    parameter int HALF = 50
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic        sclk,
    output logic        mosi,
    output logic        cs_n,
    input  logic        miso
);
    logic        go, busy, done;
    logic [3:0]  nbytes;
    logic [63:0] tx, rx;

    always_ff @(posedge clk) begin
        if (rst) begin
            go <= 1'b0; nbytes <= 4'd1; tx <= '0; win_rdata <= '0;
        end else begin
            go <= 1'b0;
            if (win_wr) begin
                unique case (win_addr)
                    7'h00:   begin nbytes <= win_wdata[11:8]; go <= win_wdata[0]; end
                    7'h02:   tx[31:0]  <= win_wdata;
                    7'h03:   tx[63:32] <= win_wdata;
                    default: ;
                endcase
            end
            if (win_rd) begin
                unique case (win_addr)
                    7'h00:   win_rdata <= {20'd0, nbytes, 8'd0};
                    7'h01:   win_rdata <= {30'd0, done, busy};
                    7'h02:   win_rdata <= tx[31:0];
                    7'h03:   win_rdata <= tx[63:32];
                    7'h04:   win_rdata <= rx[31:0];
                    7'h05:   win_rdata <= rx[63:32];
                    7'h06:   win_rdata <= {16'd0, 16'(HALF)};
                    default: win_rdata <= '0;
                endcase
            end
        end
    end

    spi_burst #(.HALF(HALF)) u_spi (
        .clk(clk), .rst(rst), .go(go), .nbytes(nbytes), .tx(tx), .rx(rx), .busy(busy), .done(done),
        .sclk(sclk), .mosi(mosi), .cs_n(cs_n), .miso(miso));
endmodule
