// Reply frame builder: board top. Test shell + register window + byte-serial CRC-32 builder.
// Reset bridge: the shell library's reset_sync (two-flop, async assert, sync release).

module v2_e_resp_builder_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED
);
    localparam int MAXP = 24;

    logic rst;
    reset_sync u_rs (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] win_wdata;
    /* verilator lint_on UNUSEDSIGNAL */
    logic [31:0] win_rdata;

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h52534231), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    // configuration registers
    logic [6:0]  r_type;
    logic [7:0]  r_status;
    logic [15:0] r_seq;
    logic [7:0]  r_idx;
    // payload
    logic [7:0]  pay [0:MAXP-1];
    logic [4:0]  plen;
    logic        ovf;
    // build state
    logic        building;
    logic [5:0]  pos;
    logic [6:0]  c_type;
    logic [7:0]  c_status;
    logic [15:0] c_seq;
    logic [4:0]  c_n;
    logic [31:0] crc;
    // reply store (two banks), act selects the readable reply
    logic [7:0]  rb0 [0:32];
    logic [7:0]  rb1 [0:32];
    logic        act;
    logic [5:0]  r_len;
    logic [7:0]  r_rstat;

    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] x;
        x = c ^ {24'h0, d};
        for (int i = 0; i < 8; i++)
            x = x[0] ? ((x >> 1) ^ 32'hEDB88320) : (x >> 1);
        return x;
    endfunction

    wire wr_cfg  = win_wr && !win_addr[6] && (win_addr[5:4] == 2'b00);
    wire do_pb   = win_wr && (win_addr == 7'd3) && !building;
    wire do_bld  = win_wr && (win_addr == 7'd4) && !building;

    logic [7:0] cur_b;
    logic       is_data;
    logic [1:0] k_crc;
    logic [5:0] hdr_end;
    always_comb begin
        hdr_end = 6'(c_n) + 6'd5;
        is_data = (pos < hdr_end);
        k_crc   = 2'(pos - hdr_end);
        cur_b   = 8'h00;
        if (is_data) begin
            case (pos)
                6'd0: cur_b = {1'b1, c_type};
                6'd1: cur_b = c_status;
                6'd2: cur_b = c_seq[15:8];
                6'd3: cur_b = c_seq[7:0];
                6'd4: cur_b = {3'b000, c_n};
                default: cur_b = pay[5'(pos - 6'd5)];
            endcase
        end else begin
            case (k_crc)
                2'd0: cur_b = ~crc[7:0];
                2'd1: cur_b = ~crc[15:8];
                2'd2: cur_b = ~crc[23:16];
                default: cur_b = ~crc[31:24];
            endcase
        end
    end

    wire last = building && !is_data && (k_crc == 2'd3);

    always_ff @(posedge CLK100MHZ) begin
        // payload data (no reset needed: masked by plen)
        if (do_pb && plen != 5'(MAXP)) pay[plen] <= win_wdata[7:0];
        // reply store (no reset needed: masked by r_len)
        if (building) begin
            if (act) rb0[pos] <= cur_b; else rb1[pos] <= cur_b;
        end
        if (building && is_data) crc <= crc8(crc, cur_b);
        if (do_bld) begin
            crc <= 32'hFFFFFFFF;
            c_type <= r_type; c_status <= r_status; c_seq <= r_seq; c_n <= plen;
        end

        if (rst) begin
            r_type <= '0; r_status <= '0; r_seq <= '0; r_idx <= '0;
            plen <= '0; ovf <= 1'b0; building <= 1'b0; pos <= '0;
            act <= 1'b0; r_len <= '0; r_rstat <= '0;
        end else begin
            if (wr_cfg) begin
                case (win_addr[3:0])
                    4'd0: r_type   <= win_wdata[6:0];
                    4'd1: r_status <= win_wdata[7:0];
                    4'd2: r_seq    <= win_wdata[15:0];
                    4'd5: r_idx    <= win_wdata[7:0];
                    default: ;
                endcase
            end
            if (do_pb) begin
                if (plen == 5'(MAXP)) ovf <= 1'b1;
                else plen <= plen + 5'd1;
            end
            if (do_bld) begin
                building <= 1'b1;
                pos <= '0;
            end else if (building) begin
                pos <= pos + 6'd1;
                if (last) begin
                    building <= 1'b0;
                    act      <= ~act;
                    r_len    <= 6'(c_n) + 6'd9;
                    r_rstat  <= c_status;
                    plen     <= '0;
                    ovf      <= 1'b0;
                end
            end
        end
    end

    // readback
    logic [7:0] byte_rd;
    always_comb begin
        byte_rd = 8'h00;
        if (r_idx < {2'b00, r_len})
            byte_rd = act ? rb1[r_idx[5:0]] : rb0[r_idx[5:0]];
    end

    always_ff @(posedge CLK100MHZ) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'd0: win_rdata <= {25'h0, r_type};
                7'd1: win_rdata <= {24'h0, r_status};
                7'd2: win_rdata <= {16'h0, r_seq};
                7'd5: win_rdata <= {24'h0, r_idx};
                7'd6: win_rdata <= {24'h0, byte_rd};
                7'd7: win_rdata <= {26'h0, r_len};
                7'd8: win_rdata <= {30'h0, ovf, building};
                7'd9: win_rdata <= {27'h0, plen};
                default: win_rdata <= 32'h0;
            endcase
        end
    end

    assign LED = {r_rstat, 2'b00, r_len};
endmodule
