// Command packet screener: board top. UART test shell, packet parser, CRC-32, classifier, counters.
module v2_e_cmd_parser_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0,
    parameter logic [31:0] DESIGN_ID      = 32'h43505331
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED
);
    localparam int TW = $clog2(TIMEOUT_CYCLES + 1);

    logic        rst;
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;

    v2_e_cmd_parser_rst_sync u_rst (.clk(CLK100MHZ), .arstn(CPU_RESETN), .rst(rst));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(DESIGN_ID), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    // ------------------------------------------------------------ packet state
    logic [7:0]  cnt;                 // bytes taken so far (saturating)
    logic [7:0]  p_typ, p_len, p_sh, p_sl;
    logic [7:0]  p_pay [6];
    logic [31:0] win, crc;
    logic        busy, fin, cls_v;
    logic [TW-1:0] idle;
    logic [3:0]  cls_r;
    logic [8:0]  byte_reg;

    // results
    logic [3:0]  result;
    logic [7:0]  r_typ;
    logic [15:0] r_seq, last_seq;
    logic [15:0] r_pay0;
    logic [31:0] r_pay1;
    logic        have_last;
    logic [15:0] ctr [7];

    localparam logic [31:0] CRC_INIT = 32'hFFFFFFFF;

    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] x;
        x = c ^ {24'b0, d};
        for (int i = 0; i < 8; i++) x = x[0] ? ((x >> 1) ^ 32'hEDB88320) : (x >> 1);
        return x;
    endfunction

    wire        wr_byte = win_wr && (win_addr == 7'd0);
    wire [7:0]  in_b    = win_wdata[7:0];
    wire        in_end  = win_wdata[8];

    // ------------------------------------------------------------ classification (from state, after end byte)
    logic [3:0] cls_c;
    logic [15:0] seq_c, dseq;
    logic [8:0] full_len;
    logic type_ok, len_ok;
    always_comb begin
        seq_c    = {p_sh, p_sl};
        dseq     = seq_c - last_seq;
        full_len = {1'b0, p_len} + 9'd8;
        type_ok  = (p_typ >= 8'd1) && (p_typ <= 8'd5);
        case (p_typ)
            8'd1:    len_ok = (p_len == 8'd2);
            8'd2:    len_ok = (p_len == 8'd6);
            8'd3:    len_ok = (p_len == 8'd0);
            8'd4:    len_ok = (p_len == 8'd2);
            8'd5:    len_ok = (p_len == 8'd0);
            default: len_ok = 1'b0;
        endcase
        if (cnt < 8'd4)                                  cls_c = 4'd3;
        else if (p_len > 8'd8 || {1'b0, cnt} > full_len) cls_c = 4'd4;
        else if ({1'b0, cnt} < full_len)                 cls_c = 4'd3;
        else if (~crc != win)                            cls_c = 4'd2;
        else if (!type_ok)                               cls_c = 4'd7;
        else if (!len_ok)                                cls_c = 4'd8;
        else if (have_last && dseq == 16'd0)             cls_c = 4'd5;
        else if (have_last && dseq > 16'd32767)          cls_c = 4'd6;
        else                                             cls_c = 4'd1;
    end

    // ------------------------------------------------------------ sequential logic
    logic [2:0] cidx;
    always_comb begin
        case (cls_r)
            4'd1: cidx = 3'd0;
            4'd2: cidx = 3'd1;
            4'd3: cidx = 3'd2;
            4'd4: cidx = 3'd3;
            4'd5: cidx = 3'd4;
            4'd6: cidx = 3'd5;
            default: cidx = 3'd6;
        endcase
    end

    always_ff @(posedge CLK100MHZ) begin
        // datapath capture (no reset needed: only read after a full packet)
        if (wr_byte) begin
            case (cnt)
                8'd0: p_typ <= in_b;
                8'd1: p_len <= in_b;
                8'd2: p_sh  <= in_b;
                8'd3: p_sl  <= in_b;
                8'd4: p_pay[0] <= in_b;
                8'd5: p_pay[1] <= in_b;
                8'd6: p_pay[2] <= in_b;
                8'd7: p_pay[3] <= in_b;
                8'd8: p_pay[4] <= in_b;
                8'd9: p_pay[5] <= in_b;
                default: ;
            endcase
            win <= {in_b, win[31:8]};
        end

        if (rst) begin
            cnt       <= 8'd0;
            crc       <= CRC_INIT;
            busy      <= 1'b0;
            fin       <= 1'b0;
            cls_v     <= 1'b0;
            cls_r     <= 4'd0;
            idle      <= '0;
            byte_reg  <= 9'd0;
            result    <= 4'd0;
            r_typ     <= 8'd0;
            r_seq     <= 16'd0;
            r_pay0    <= 16'd0;
            r_pay1    <= 32'd0;
            last_seq  <= 16'd0;
            have_last <= 1'b0;
            for (int i = 0; i < 7; i++) ctr[i] <= 16'd0;
        end else begin
            fin   <= 1'b0;
            cls_v <= 1'b0;

            // stage 3: commit
            if (cls_v) begin
                result     <= cls_r;
                ctr[cidx]  <= ctr[cidx] + 16'd1;
                cnt        <= 8'd0;
                crc        <= CRC_INIT;
                if (cls_r == 4'd1) begin
                    r_typ     <= p_typ;
                    r_seq     <= seq_c;
                    r_pay0    <= (p_len >= 8'd2) ? {p_pay[0], p_pay[1]} : 16'd0;
                    r_pay1    <= (p_len >= 8'd6) ? {p_pay[2], p_pay[3], p_pay[4], p_pay[5]} : 32'd0;
                    last_seq  <= seq_c;
                    have_last <= 1'b1;
                end
            end

            // stage 2: classify
            if (fin) begin
                cls_r <= cls_c;
                cls_v <= 1'b1;
            end

            // timeout: abandon silently
            if (busy) begin
                idle <= idle + 1'b1;
                if (idle >= TW'(TIMEOUT_CYCLES - 1)) begin
                    busy <= 1'b0;
                    cnt  <= 8'd0;
                    crc  <= CRC_INIT;
                    idle <= '0;
                end
            end

            // stage 1: take a byte
            if (wr_byte) begin
                byte_reg <= win_wdata[8:0];
                idle     <= '0;
                if (cnt >= 8'd4) crc <= crc8(crc, win[7:0]);
                if (cnt != 8'd255) cnt <= cnt + 8'd1;
                busy <= !in_end;
                fin  <= in_end;
            end
        end
    end

    // ------------------------------------------------------------ register window read
    always_ff @(posedge CLK100MHZ) begin
        if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= {23'd0, byte_reg};
                7'h01:   win_rdata <= {28'd0, result};
                7'h02:   win_rdata <= {24'd0, r_typ};
                7'h03:   win_rdata <= {16'd0, r_seq};
                7'h04:   win_rdata <= {16'd0, r_pay0};
                7'h05:   win_rdata <= r_pay1;
                7'h06:   win_rdata <= {15'd0, have_last, last_seq};
                7'h07:   win_rdata <= {31'd0, busy};
                7'h10:   win_rdata <= {16'd0, ctr[0]};
                7'h11:   win_rdata <= {16'd0, ctr[1]};
                7'h12:   win_rdata <= {16'd0, ctr[2]};
                7'h13:   win_rdata <= {16'd0, ctr[3]};
                7'h14:   win_rdata <= {16'd0, ctr[4]};
                7'h15:   win_rdata <= {16'd0, ctr[5]};
                7'h16:   win_rdata <= {16'd0, ctr[6]};
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    assign LED = {last_seq[7:0], ctr[0][7:0]};

    /* verilator lint_off UNUSEDSIGNAL */
    wire unused_ok = &{1'b0, win_wdata[31:9]};
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
