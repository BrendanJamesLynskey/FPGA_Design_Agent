// crc32_core: register map + CRC-32 (reflected) datapath, 4 bytes per clock.
module crc32_core #(
    parameter logic [31:0] DESIGN_ID  = 32'h20930001,
    parameter logic [31:0] CRC_INIT   = 32'hFFFFFFFF,
    parameter logic [31:0] CRC_XOROUT = 32'hFFFFFFFF
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    input  logic        locked,
    output logic [1:0]  led
);
    logic [31:0] build;
    logic usr_cfgclk, usr_valid;
    USR_ACCESSE2 u_usr (.CFGCLK(usr_cfgclk), .DATA(build), .DATAVALID(usr_valid));
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_usr;
    assign unused_usr = usr_cfgclk ^ usr_valid;
    /* verilator lint_on UNUSEDSIGNAL */
    localparam logic [31:0] RPOLY = 32'hEDB88320;

    function automatic logic [31:0] crc_upd(input logic [31:0] c_in, input logic [31:0] w, input logic [2:0] n);
        logic [31:0] c;
        c = c_in;
        for (int i = 0; i < 4; i++) begin
            if (i < int'(n)) begin
                c = c ^ {24'd0, w[8*i +: 8]};
                for (int b = 0; b < 8; b++) c = c[0] ? ((c >> 1) ^ RPOLY) : (c >> 1);
            end
        end
        return c;
    endfunction

    logic [31:0] scratch, crc, bcnt, busy;
    logic [1:0]  tail;
    logic [24:0] hb;

    wire wr_scratch = h_we && (h_addr == 12'h008);
    wire wr_ctrl    = h_we && (h_addr == 12'h010);
    wire wr_push4   = h_we && (h_addr == 12'h014);
    wire wr_pushn   = h_we && (h_addr == 12'h018);
    wire wr_tail    = h_we && (h_addr == 12'h01C);
    wire init       = wr_ctrl && h_wdata[0];
    wire [2:0] n_bytes = wr_push4 ? 3'd4 : (wr_pushn ? {1'b0, tail} : 3'd0);

    always_ff @(posedge clk) begin
        if (rst) begin
            scratch <= 32'd0;
            tail    <= 2'd0;
            crc     <= CRC_INIT;
            bcnt    <= 32'd0;
            busy    <= 32'd0;
        end else begin
            if (wr_scratch) scratch <= h_wdata;
            if (wr_tail)    tail    <= h_wdata[1:0];
            if (init) begin
                crc  <= CRC_INIT;
                bcnt <= 32'd0;
                busy <= 32'd0;
            end else if (n_bytes != 3'd0) begin
                crc  <= crc_upd(crc, h_wdata, n_bytes);
                bcnt <= bcnt + {29'd0, n_bytes};
                busy <= busy + 32'd1;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) h_rdata <= 32'd0;
        else if (h_re) begin
            case (h_addr)
                12'h000: h_rdata <= DESIGN_ID;
                12'h004: h_rdata <= build;
                12'h008: h_rdata <= scratch;
                12'h010: h_rdata <= 32'd0;
                12'h01C: h_rdata <= {30'd0, tail};
                12'h020: h_rdata <= (bcnt != 32'd0) ? (crc ^ CRC_XOROUT) : 32'd0;
                12'h024: h_rdata <= bcnt;
                12'h028: h_rdata <= busy;
                default: h_rdata <= 32'd0;
            endcase
        end
    end

    always_ff @(posedge clk) begin
        if (rst) hb <= '0;
        else hb <= hb + 25'd1;
    end
    assign led = {hb[24], locked};
endmodule
