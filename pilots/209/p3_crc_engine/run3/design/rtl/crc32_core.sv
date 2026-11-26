// crc32_core: register file, 4-bytes-per-clock reflected CRC-32, counters, LEDs.
module crc32_core #(
    parameter logic [31:0] DESIGN_ID = 32'h20930001,
    parameter int unsigned HB_HALF   = 50_000_000
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        locked,
    input  logic [31:0] build_word,
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    localparam logic [11:0] A_ID = 12'h000, A_BUILD = 12'h004, A_SCR = 12'h008, A_CTRL = 12'h010,
                            A_P4 = 12'h014, A_PN = 12'h018, A_TAIL = 12'h01C, A_CRC = 12'h020,
                            A_BYTES = 12'h024, A_BUSY = 12'h028;

    logic [31:0] crc, bytes, busy, scratch;
    logic [1:0]  tail;

    // CRC byte-serial update unrolled (reflected polynomial 0xEDB88320)
    function automatic logic [31:0] step8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] r;
        r = c ^ {24'd0, d};
        for (int i = 0; i < 8; i++) r = r[0] ? ((r >> 1) ^ 32'hEDB88320) : (r >> 1);
        return r;
    endfunction

    function automatic logic [31:0] upd(input logic [31:0] c, input logic [31:0] w, input logic [2:0] n);
        logic [31:0] r;
        r = c;
        for (int i = 0; i < 4; i++) if (i < n) r = step8(r, w[8*i +: 8]);
        return r;
    endfunction

    wire push4  = h_we && (h_addr == A_P4);
    wire pushn  = h_we && (h_addr == A_PN) && (tail != 2'd0);
    wire init   = h_we && (h_addr == A_CTRL) && h_wdata[0];

    always_ff @(posedge clk) begin
        if (rst) begin
            crc <= 32'hFFFFFFFF; bytes <= '0; busy <= '0; scratch <= '0; tail <= '0;
        end else begin
            if (init) begin
                crc <= 32'hFFFFFFFF; bytes <= '0; busy <= '0;
            end else if (push4) begin
                crc <= upd(crc, h_wdata, 3'd4); bytes <= bytes + 32'd4; busy <= busy + 32'd1;
            end else if (pushn) begin
                crc <= upd(crc, h_wdata, {1'b0, tail}); bytes <= bytes + {30'd0, tail}; busy <= busy + 32'd1;
            end
            if (h_we && h_addr == A_SCR) scratch <= h_wdata;
            if (h_we && h_addr == A_TAIL && h_wdata <= 32'd3) tail <= h_wdata[1:0];
        end
    end

    // read data register: valid 1 clk after h_re, held until next h_re
    always_ff @(posedge clk) begin
        if (rst) h_rdata <= '0;
        else if (h_re) begin
            case (h_addr)
                A_ID:    h_rdata <= DESIGN_ID;
                A_BUILD: h_rdata <= build_word;
                A_SCR:   h_rdata <= scratch;
                A_TAIL:  h_rdata <= {30'd0, tail};
                A_CRC:   h_rdata <= crc ^ 32'hFFFFFFFF;
                A_BYTES: h_rdata <= bytes;
                A_BUSY:  h_rdata <= busy;
                default: h_rdata <= '0;
            endcase
        end
    end

    // heartbeat
    logic [26:0] hb;
    logic        hb_led;
    always_ff @(posedge clk) begin
        if (rst) begin hb <= '0; hb_led <= 1'b0; end
        else if (32'(hb) == HB_HALF - 1) begin hb <= '0; hb_led <= ~hb_led; end
        else hb <= hb + 27'd1;
    end

    assign led = {locked, hb_led};
    assign sfp_tx_disable = 1'b1;
endmodule
