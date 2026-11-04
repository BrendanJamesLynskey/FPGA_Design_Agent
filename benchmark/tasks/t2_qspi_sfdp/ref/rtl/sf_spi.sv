// sf_spi.sv: single-bit SPI mode-0 transaction engine for the configuration
// flash. CS low, nhdr header bytes from hdr (MSB byte first), then nrd bytes
// with DQ0 = 0 whose received values come out on rx_valid / rx_byte, CS high,
// then a gap. Once after reset it first makes STARTUP SCK cycles with CS high.
module sf_spi #(
    parameter int HALF    = 10,
    parameter int STARTUP = 8
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        go,
    input  logic [31:0] hdr,
    input  logic [2:0]  nhdr,
    input  logic [4:0]  nrd,
    input  logic        miso,          // synchronised
    output logic        sck,
    output logic        mosi,
    output logic        csn,
    output logic        busy,          // includes the start-up cycles
    output logic        rx_valid,
    output logic [7:0]  rx_byte
);
    localparam int CW = $clog2(4 * HALF + 1);
    typedef enum logic [2:0] {BOOT, IDLE, LEAD, LOW, HIGH, TAIL, GAP} st_t;
    st_t st;

    logic [CW-1:0] cnt;
    logic [2:0]    bitn;
    logic [5:0]    b, total;
    logic [31:0]   h;
    logic [2:0]    nh;
    logic [7:0]    sh_out, sh_in;
    logic [4:0]    boot_n;

    function automatic logic [7:0] tx_byte(input logic [5:0] idx, input logic [31:0] hh, input logic [2:0] n);
        if (idx >= {3'd0, n}) tx_byte = 8'h00;
        else                  tx_byte = hh[31 - 8 * idx[1:0] -: 8];
    endfunction
    function automatic logic msb(input logic [7:0] v);
        msb = v[7];
    endfunction

    always_ff @(posedge clk) begin
        rx_valid <= 1'b0;
        if (rst) begin
            st <= BOOT; cnt <= CW'(HALF - 1); bitn <= '0; b <= '0; total <= '0; h <= '0; nh <= '0;
            sh_out <= '0; sh_in <= '0; sck <= 1'b0; mosi <= 1'b0; csn <= 1'b1; busy <= 1'b1; rx_byte <= '0;
            boot_n <= '0;
        end else begin
            case (st)
                // start-up: STARTUP SCK cycles with CS high
                BOOT: if (cnt == '0) begin
                    cnt <= CW'(HALF - 1);
                    sck <= ~sck;
                    if (sck) begin
                        if (boot_n == 5'(STARTUP - 1)) begin st <= GAP; cnt <= CW'(4 * HALF - 1); end
                        boot_n <= boot_n + 1'b1;
                    end
                end else cnt <= cnt - 1'b1;
                IDLE: if (go) begin
                    busy <= 1'b1; csn <= 1'b0; h <= hdr; nh <= nhdr;
                    total <= {3'd0, nhdr} + {1'b0, nrd};
                    b <= '0; st <= LEAD; cnt <= CW'(HALF - 1);
                end
                LEAD: if (cnt == '0) begin
                    st <= LOW; cnt <= CW'(HALF - 1); bitn <= '0;
                    sh_out <= tx_byte(6'd0, h, nh); mosi <= msb(tx_byte(6'd0, h, nh));
                end else cnt <= cnt - 1'b1;
                LOW: if (cnt == '0) begin
                    st <= HIGH; cnt <= CW'(HALF - 1); sck <= 1'b1;
                    sh_in <= {sh_in[6:0], miso};
                end else cnt <= cnt - 1'b1;
                HIGH: if (cnt == '0) begin
                    sck <= 1'b0; cnt <= CW'(HALF - 1);
                    if (bitn == 3'd7) begin
                        if (b >= {3'd0, nh}) begin rx_valid <= 1'b1; rx_byte <= sh_in; end
                        if (b + 1'b1 == total) begin
                            st <= TAIL; mosi <= 1'b0;
                        end else begin
                            b <= b + 1'b1; bitn <= '0; st <= LOW;
                            sh_out <= tx_byte(b + 1'b1, h, nh); mosi <= msb(tx_byte(b + 1'b1, h, nh));
                        end
                    end else begin
                        bitn <= bitn + 1'b1; st <= LOW;
                        sh_out <= {sh_out[6:0], 1'b0}; mosi <= sh_out[6];
                    end
                end else cnt <= cnt - 1'b1;
                TAIL: if (cnt == '0) begin st <= GAP; csn <= 1'b1; cnt <= CW'(4 * HALF - 1); end
                      else cnt <= cnt - 1'b1;
                GAP: if (cnt == '0) begin st <= IDLE; busy <= 1'b0; end else cnt <= cnt - 1'b1;
                default: st <= IDLE;
            endcase
        end
    end
endmodule
