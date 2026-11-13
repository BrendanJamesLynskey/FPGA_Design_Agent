// bd_axil_win.sv: an AXI4-Lite slave in front of a block with a test-shell style register window (block-design
// support). Word w of the slave's range is window offset w (0..127), at byte offsets 0x000-0x1FC. The slave decodes
// its whole range (2**ADDR_W bytes): an access above 0x1FF is not passed to the window and answers SLVERR (a read
// returns 0), so the rest of the range never aliases the window.
// A write pulses win_wr for one clock; a read pulses win_rd and takes win_rdata the next clock, which suits a block
// whose read data is registered after win_rd (the shell's rule) and one whose read data follows win_addr at once.
// The window has no byte strobes: a write with WSTRB other than 4'hF is not performed and answers SLVERR.
// One transfer at a time; a write and a read never overlap (the window has one address).
module bd_axil_win #(
    parameter int ADDR_W = 9
) (
    input  logic              clk,
    input  logic              rst,
    input  logic [ADDR_W-1:0] s_axil_awaddr,
    input  logic [2:0]        s_axil_awprot,
    input  logic              s_axil_awvalid,
    output logic              s_axil_awready,
    input  logic [31:0]       s_axil_wdata,
    input  logic [3:0]        s_axil_wstrb,
    input  logic              s_axil_wvalid,
    output logic              s_axil_wready,
    output logic [1:0]        s_axil_bresp,
    output logic              s_axil_bvalid,
    input  logic              s_axil_bready,
    input  logic [ADDR_W-1:0] s_axil_araddr,
    input  logic [2:0]        s_axil_arprot,
    input  logic              s_axil_arvalid,
    output logic              s_axil_arready,
    output logic [31:0]       s_axil_rdata,
    output logic [1:0]        s_axil_rresp,
    output logic              s_axil_rvalid,
    input  logic              s_axil_rready,
    output logic [6:0]        win_addr,
    output logic              win_wr,
    output logic              win_rd,
    output logic [31:0]       win_wdata,
    input  logic [31:0]       win_rdata
);
    // Parameter guard: an initial block, so it stops a simulation; synthesis ignores it (the generator checks first).
    initial if (ADDR_W < 9 || ADDR_W > 32) $error("bd_axil_win: ADDR_W %0d outside 9..32", ADDR_W);

    logic idle, rd_wait, aw_out, ar_out;
    assign aw_out = |(s_axil_awaddr >> 9);                                   // above the 128-word window
    assign ar_out = |(s_axil_araddr >> 9);
    assign idle           = !s_axil_bvalid && !s_axil_rvalid && !rd_wait;
    assign s_axil_awready = idle && s_axil_awvalid && s_axil_wvalid;          // writes win over reads in the same clock
    assign s_axil_wready  = s_axil_awready;
    assign s_axil_arready = idle && s_axil_arvalid && !(s_axil_awvalid && s_axil_wvalid);

    always_ff @(posedge clk) begin
        if (rst) begin
            s_axil_bvalid <= 1'b0; s_axil_rvalid <= 1'b0; rd_wait <= 1'b0; s_axil_bresp <= 2'b00; s_axil_rresp <= 2'b00;
            s_axil_rdata <= '0; win_addr <= '0; win_wr <= 1'b0; win_rd <= 1'b0; win_wdata <= '0;
        end else begin
            win_wr <= 1'b0;
            win_rd <= 1'b0;
            if (s_axil_awready) begin
                win_addr  <= s_axil_awaddr[8:2];
                win_wdata <= s_axil_wdata;
                win_wr    <= (s_axil_wstrb == 4'hF) && !aw_out;
                s_axil_bresp  <= (s_axil_wstrb == 4'hF && !aw_out) ? 2'b00 : 2'b10;
                s_axil_bvalid <= 1'b1;
            end else if (s_axil_bvalid && s_axil_bready) s_axil_bvalid <= 1'b0;
            if (s_axil_arready && ar_out) begin                              // outside the window: SLVERR at once
                s_axil_rdata  <= '0;
                s_axil_rresp  <= 2'b10;
                s_axil_rvalid <= 1'b1;
            end else if (s_axil_arready) begin
                win_addr <= s_axil_araddr[8:2];
                win_rd   <= 1'b1;
                rd_wait  <= 1'b1;
            end else if (rd_wait && !win_rd) begin                       // the clock after win_rd
                s_axil_rdata  <= win_rdata;
                s_axil_rresp  <= 2'b00;
                s_axil_rvalid <= 1'b1;
                rd_wait       <= 1'b0;
            end else if (s_axil_rvalid && s_axil_rready) s_axil_rvalid <= 1'b0;
        end
    end

    /* verilator lint_off UNUSEDSIGNAL */
    logic unused;          // protection and the byte-lane address bits are not used
    assign unused = ^{s_axil_awprot, s_axil_arprot, s_axil_awaddr[1:0], s_axil_araddr[1:0]};
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
