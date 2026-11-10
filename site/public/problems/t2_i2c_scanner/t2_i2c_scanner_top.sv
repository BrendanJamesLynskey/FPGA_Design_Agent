// t2_i2c_scanner_top.sv: board top (Nexys A7-100T, master-XDC port names).
// Reference design for benchmark task t2_i2c_scanner; DESIGN_ID "SCAN".
// Scans I2C addresses 0x08..0x77 on the sensor bus; LED shows the count.
module t2_i2c_scanner_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter int          QUARTER        = 250,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    inout  wire         TMP_SCL,
    inout  wire         TMP_SDA,
    output logic [15:0] LED,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
    logic         clk, rst, win_wr, win_rd, scl_oe, sda_oe, busy, done;
    logic [1:0]   lines;
    logic [6:0]   win_addr;
    logic [31:0]  win_wdata, win_rdata;
    logic [7:0]   count, lowest;
    logic [127:0] map;

    assign clk = CLK100MHZ;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h5343_414E), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    assign TMP_SCL = scl_oe ? 1'b0 : 1'bz;
    assign TMP_SDA = sda_oe ? 1'b0 : 1'bz;
    sync2 #(.WIDTH(2), .RESET_VALUE(2'b11)) u_sync (.clk(clk), .rst(rst), .d({TMP_SCL, TMP_SDA}), .q(lines));

    scan_core #(.QUARTER(QUARTER)) u_scan (
        .clk(clk), .rst(rst), .go(win_wr && win_addr == 7'h00 && win_wdata[0]),
        .scl_in(lines[1]), .sda_in(lines[0]), .scl_oe(scl_oe), .sda_oe(sda_oe),
        .busy(busy), .done(done), .count(count), .lowest(lowest), .map(map));

    always_ff @(posedge clk) begin
        if (rst) LED <= '0;
        else     LED <= {8'd0, count};
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h01:   win_rdata <= {30'd0, done, busy};
                7'h02:   win_rdata <= {24'd0, count};
                7'h03:   win_rdata <= {24'd0, lowest};
                7'h04:   win_rdata <= map[31:0];
                7'h05:   win_rdata <= map[63:32];
                7'h06:   win_rdata <= map[95:64];
                7'h07:   win_rdata <= map[127:96];
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
