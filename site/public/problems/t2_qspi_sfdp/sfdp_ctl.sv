// sfdp_ctl.sv: on a start command, RDID (9Fh, 3 bytes) then RSFDP (5Ah,
// address 0, 8 dummy cycles, 16 bytes). The only opcodes are these two
// constants; no write, erase, register-write or reset command exists here.
module sfdp_ctl #(
    parameter int HALF = 10
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        miso,
    output logic        sck,
    output logic        mosi,
    output logic        csn,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam logic [7:0] OP_RDID = 8'h9F, OP_RSFDP = 8'h5A;

    typedef enum logic [2:0] {IDLE, ID, ID_W, SF, SF_W} st_t;
    st_t st;

    logic         go, sbusy, rx_valid, busy, done, sig_ok;
    logic [31:0]  hdr;
    logic [2:0]   nhdr;
    logic [4:0]   nrd, ridx;
    logic [7:0]   rx_byte;
    logic [23:0]  id;
    logic [127:0] sf;

    sf_spi #(.HALF(HALF)) u_spi (
        .clk(clk), .rst(rst), .go(go), .hdr(hdr), .nhdr(nhdr), .nrd(nrd), .miso(miso),
        .sck(sck), .mosi(mosi), .csn(csn), .busy(sbusy), .rx_valid(rx_valid), .rx_byte(rx_byte));

    wire start = win_wr && win_addr == 7'h00 && win_wdata[0] && !busy;

    always_ff @(posedge clk) begin
        go <= 1'b0;
        if (rst) begin
            st <= IDLE; hdr <= '0; nhdr <= '0; nrd <= '0; ridx <= '0; busy <= 1'b0; done <= 1'b0; sig_ok <= 1'b0;
            id <= '0; sf <= '0;
        end else begin
            case (st)
                IDLE: if (start) begin busy <= 1'b1; done <= 1'b0; sig_ok <= 1'b0; st <= ID; end
                ID: if (!sbusy) begin
                    hdr <= {OP_RDID, 24'h0}; nhdr <= 3'd1; nrd <= 5'd3; go <= 1'b1; ridx <= '0; st <= ID_W;
                end
                ID_W: begin
                    if (rx_valid) id <= {id[15:0], rx_byte};
                    if (!go && !sbusy) st <= SF;
                end
                SF: begin
                    hdr <= {OP_RSFDP, 24'h000000}; nhdr <= 3'd4; nrd <= 5'd17; go <= 1'b1; ridx <= '0; st <= SF_W;
                end
                SF_W: begin
                    if (rx_valid) begin
                        ridx <= ridx + 1'b1;
                        if (ridx != 5'd0) sf <= {rx_byte, sf[127:8]};      // byte 0 ends in [7:0]
                    end
                    if (!go && !sbusy) begin
                        st <= IDLE; busy <= 1'b0; done <= 1'b1;
                        sig_ok <= sf[31:0] == 32'h5044_4653;
                    end
                end
                default: st <= IDLE;
            endcase
        end
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h01:   win_rdata <= {29'd0, sig_ok, done, busy};
                7'h02:   win_rdata <= {8'd0, id};
                7'h03:   win_rdata <= sf[31:0];
                7'h04:   win_rdata <= sf[63:32];
                7'h05:   win_rdata <= sf[95:64];
                7'h06:   win_rdata <= sf[127:96];
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
