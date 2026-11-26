// crc_core: register map and Ethernet CRC-32 datapath (4 bytes per clock) behind the jtag_bus register port.
module crc_core (
    input  logic        clk,
    input  logic        rst,            // active high, synchronous
    input  logic        locked,         // MMCM locked, already synchronised to clk
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    localparam logic [31:0] DESIGN_ID = 32'h2093_0001;
    localparam logic [31:0] POLY_R    = 32'hEDB8_8320;

    localparam logic [11:0] A_ID = 12'h000, A_BUILD = 12'h004, A_SCRATCH = 12'h008, A_CTRL = 12'h010,
                            A_PUSH4 = 12'h014, A_PUSHN = 12'h018, A_TAIL = 12'h01C, A_CRC = 12'h020,
                            A_BCNT = 12'h024, A_BUSY = 12'h028;

    // build stamp
    logic [31:0] build_word;
    /* verilator lint_off PINCONNECTEMPTY */
    USR_ACCESSE2 u_usr (.CFGCLK(), .DATA(build_word), .DATAVALID());
    /* verilator lint_on PINCONNECTEMPTY */

    logic [31:0] scratch, crc_state, bcnt, busy;
    logic [1:0]  tail;

    // CRC update of the low n bytes of d (n 0..4)
    function automatic logic [31:0] crc_bytes(input logic [31:0] s_in, input logic [31:0] d, input logic [2:0] n);
        logic [31:0] s;
        s = s_in;
        for (int i = 0; i < 4; i++) begin
            if (i < int'(n)) begin
                s = s ^ {24'h0, d[8*i +: 8]};
                for (int k = 0; k < 8; k++) s = s[0] ? ((s >> 1) ^ POLY_R) : (s >> 1);
            end
        end
        return s;
    endfunction

    logic wr_push4, wr_pushn, wr_init;
    assign wr_push4 = h_we && (h_addr == A_PUSH4);
    assign wr_pushn = h_we && (h_addr == A_PUSHN) && (tail != 2'd0);
    assign wr_init  = h_we && (h_addr == A_CTRL) && h_wdata[0];

    logic [2:0]  n_bytes;
    logic [31:0] crc_next;
    assign n_bytes  = wr_push4 ? 3'd4 : {1'b0, tail};
    assign crc_next = crc_bytes(crc_state, h_wdata, n_bytes);

    always_ff @(posedge clk) begin
        if (rst) begin
            scratch   <= 32'h0;
            tail      <= 2'd0;
            crc_state <= 32'hFFFF_FFFF;
            bcnt      <= 32'h0;
            busy      <= 32'h0;
            h_rdata   <= 32'h0;
        end else begin
            if (h_we && h_addr == A_SCRATCH) scratch <= h_wdata;
            if (h_we && h_addr == A_TAIL)    tail    <= h_wdata[1:0];
            if (wr_init) begin
                crc_state <= 32'hFFFF_FFFF;
                bcnt      <= 32'h0;
                busy      <= 32'h0;
            end else if (wr_push4 || wr_pushn) begin
                crc_state <= crc_next;
                bcnt      <= bcnt + {29'h0, n_bytes};
                busy      <= busy + 32'd1;
            end
            if (h_re) begin
                case (h_addr)
                    A_ID:      h_rdata <= DESIGN_ID;
                    A_BUILD:   h_rdata <= build_word;
                    A_SCRATCH: h_rdata <= scratch;
                    A_TAIL:    h_rdata <= {30'h0, tail};
                    A_CRC:     h_rdata <= crc_state ^ 32'hFFFF_FFFF;
                    A_BCNT:    h_rdata <= bcnt;
                    A_BUSY:    h_rdata <= busy;
                    default:   h_rdata <= 32'h0;
                endcase
            end
        end
    end

    assign led            = {1'b0, locked};
    assign sfp_tx_disable = 1'b1;
endmodule
