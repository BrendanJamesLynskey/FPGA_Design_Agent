// mic_regs.sv: the microphone self-check's registers in the test shell's window
// (offsets from 0x80), around pdm_stats.
//
//   0x00 CTRL     W: [0] GO; R: 0
//   0x01 STATUS   R: [0] busy, [1] done
//   0x02 NBITS    RW: window length in PDM bits (reset 1,048,576)
//   0x03 ONES     R: bits that were 1 in the last window
//   0x04 CHANGES  R: bit-to-bit changes in the last window
//   0x05 INFO     R: [15:0] HALF (M_CLK half period in clocks)
//   other         R: 0

module mic_regs #(
    parameter int HALF = 21
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic        mclk,
    input  logic        mdata
);
    logic        go, busy, done;
    logic [31:0] nbits, ones, changes;

    always_ff @(posedge clk) begin
        if (rst) begin
            go <= 1'b0; nbits <= 32'd1_048_576; win_rdata <= '0;
        end else begin
            go <= win_wr && win_addr == 7'h00 && win_wdata[0];
            if (win_wr && win_addr == 7'h02) nbits <= win_wdata;
            if (win_rd) begin
                unique case (win_addr)
                    7'h01:   win_rdata <= {30'd0, done, busy};
                    7'h02:   win_rdata <= nbits;
                    7'h03:   win_rdata <= ones;
                    7'h04:   win_rdata <= changes;
                    7'h05:   win_rdata <= {16'd0, 16'(HALF)};
                    default: win_rdata <= '0;
                endcase
            end
        end
    end

    pdm_stats #(.HALF(HALF)) u_pdm (
        .clk(clk), .rst(rst), .go(go), .nbits(nbits), .busy(busy), .done(done),
        .ones(ones), .changes(changes), .mclk(mclk), .mdata(mdata));
endmodule
