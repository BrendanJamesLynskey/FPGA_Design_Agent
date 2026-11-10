// spim_regs.sv: registers of the Pmod JB SPI master in the shell window.
module spim_regs (
    input  logic        clk,
    input  logic        rst,
    input  logic        miso_pin,     // JB3, synchronised
    output logic        cs_n,
    output logic        sclk,
    output logic        mosi,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam logic [6:0] R_CTRL = 7'h00, R_DIV = 7'h01, R_TXDATA = 7'h02, R_RXDATA = 7'h03, R_STATUS = 7'h04;

    logic [5:0]  ctrl;
    logic [15:0] div, txd, rxd;
    logic        busy, done_p, done_f;

    wire start = win_wr && win_addr == R_TXDATA && !busy;

    always_ff @(posedge clk) begin
        if (rst) begin
            ctrl <= '0; div <= 16'd50; txd <= '0; done_f <= 1'b0;
        end else begin
            if (win_wr && win_addr == R_CTRL) ctrl <= win_wdata[5:0];
            if (win_wr && win_addr == R_DIV && win_wdata[15:0] >= 16'd2) div <= win_wdata[15:0];
            if (start) txd <= win_wdata[15:0];
            done_f <= (done_f && !(win_wr && win_addr == R_STATUS && win_wdata[1])) || done_p;
        end
    end

    spim_core u_core (
        .clk(clk), .rst(rst), .start(start), .txd(win_wdata[15:0]), .div(div),
        .cpol(ctrl[0]), .cpha(ctrl[1]), .lsb(ctrl[2]), .w16(ctrl[3]), .cs_hold(ctrl[4]),
        .miso(ctrl[5] ? mosi : miso_pin),
        .busy(busy), .done(done_p), .rxd(rxd), .cs_n(cs_n), .sclk(sclk), .mosi(mosi));

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                R_CTRL:   win_rdata <= {26'd0, ctrl};
                R_DIV:    win_rdata <= {16'd0, div};
                R_TXDATA: win_rdata <= {16'd0, txd};
                R_RXDATA: win_rdata <= {16'd0, rxd};
                R_STATUS: win_rdata <= {29'd0, !cs_n, done_f, busy};
                default:  win_rdata <= '0;
            endcase
        end
    end
endmodule
