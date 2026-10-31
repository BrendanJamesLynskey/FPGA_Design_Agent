// qspi_regs.sv: the flash-ID self-check's registers in the test shell's window
// (offsets from 0x80), around qspi_rdid. There is nothing to write but GO.
//
//   0x00 CTRL    W: [0] GO (read the JEDEC ID); R: 0
//   0x01 STATUS  R: [0] busy, [1] done
//   0x02 ID0     R: ID bytes 0-3 (byte 0, the manufacturer, in [7:0])
//   0x03 ID1     R: ID bytes 4-7
//   0x04 INFO    R: [15:0] HALF (SCK half period in clocks)
//   other        R: 0

module qspi_regs #(
    parameter int HALF     = 50,
    parameter int PREAMBLE = 8
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,      // only [0] (GO) is used
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic        sck,
    output logic        cs_n,
    output logic        dq0,
    input  logic        dq1
);
    logic        go, busy, done;
    logic [63:0] id;

    always_ff @(posedge clk) begin
        if (rst) begin
            go <= 1'b0; win_rdata <= '0;
        end else begin
            go <= win_wr && win_addr == 7'h00 && win_wdata[0];
            if (win_rd) begin
                unique case (win_addr)
                    7'h01:   win_rdata <= {30'd0, done, busy};
                    7'h02:   win_rdata <= id[31:0];
                    7'h03:   win_rdata <= id[63:32];
                    7'h04:   win_rdata <= {16'd0, 16'(HALF)};
                    default: win_rdata <= '0;
                endcase
            end
        end
    end

    qspi_rdid #(.HALF(HALF), .PREAMBLE(PREAMBLE)) u_rdid (
        .clk(clk), .rst(rst), .go(go), .busy(busy), .done(done), .id(id),
        .sck(sck), .cs_n(cs_n), .dq0(dq0), .dq1(dq1));
endmodule
