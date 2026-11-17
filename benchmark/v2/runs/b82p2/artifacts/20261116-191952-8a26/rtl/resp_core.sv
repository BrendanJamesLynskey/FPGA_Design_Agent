// Register window, payload store and reply builder (one byte per clock, CRC-32).
module resp_core (
    input  logic        clk,
    input  logic        rst,          // synchronous, active high
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,    // only bits 15:0 are used
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam logic [6:0] A_TYPE = 7'd0, A_STATUS = 7'd1, A_SEQ = 7'd2, A_PBYTE = 7'd3,
                           A_BUILD = 7'd4, A_IDX = 7'd5, A_BYTE = 7'd6, A_LEN = 7'd7,
                           A_STAT = 7'd8, A_PLEN = 7'd9;
    localparam logic [31:0] POLY = 32'hEDB88320;

    // user registers
    logic [6:0]  r_type;
    logic [7:0]  r_status;
    logic [15:0] r_seq;
    logic [6:0]  r_idx;
    logic [4:0]  cnt;        // payload bytes held (0..24)
    logic        ovf;
    logic        building;

    // payload store (no reset needed: count gates it)
    (* ram_style = "distributed" *) logic [7:0] pay_mem [0:31];

    // build snapshot and state
    logic [6:0]  s_type;
    logic [7:0]  s_status;
    logic [15:0] s_seq;
    logic [5:0]  k;
    logic [31:0] crc;

    // reply store: two banks of 64 bytes, bank flips on completion
    (* ram_style = "distributed" *) logic [7:0] rep_mem [0:127];
    logic        bank;
    logic [5:0]  rep_len;
    logic [7:0]  rep_status;

    wire wr_ok   = win_wr && !building;
    wire pb_wr   = wr_ok && (win_addr == A_PBYTE);
    wire bld_st  = wr_ok && (win_addr == A_BUILD);

    // ---- byte generation ----
    wire [5:0] data_end = 6'd5 + {1'b0, cnt};            // first CRC byte index
    wire [4:0] pidx     = k[4:0] - 5'd5;
    wire [7:0] pay_rd   = pay_mem[pidx];
    logic [7:0] cur_byte;
    wire in_data = (k < data_end);
    always_comb begin
        case (k)
            6'd0:    cur_byte = {1'b1, s_type};
            6'd1:    cur_byte = s_status;
            6'd2:    cur_byte = s_seq[15:8];
            6'd3:    cur_byte = s_seq[7:0];
            6'd4:    cur_byte = {3'b000, cnt};
            default: cur_byte = in_data ? pay_rd : ~crc[7:0];
        endcase
    end

    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] x;
        x = c ^ {24'h0, d};
        for (int i = 0; i < 8; i++) x = x[0] ? ((x >> 1) ^ POLY) : (x >> 1);
        return x;
    endfunction

    wire last = (k == data_end + 6'd3);

    always_ff @(posedge clk) begin
        if (building) rep_mem[{~bank, k}] <= cur_byte;
        if (pb_wr && cnt < 5'd24) pay_mem[cnt[4:0]] <= win_wdata[7:0];
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            r_type <= '0; r_status <= '0; r_seq <= '0; r_idx <= '0;
            cnt <= '0; ovf <= 1'b0; building <= 1'b0;
            s_type <= '0; s_status <= '0; s_seq <= '0; k <= '0; crc <= '0;
            bank <= 1'b0; rep_len <= '0; rep_status <= '0;
        end else begin
            if (win_wr) begin
                case (win_addr)
                    A_TYPE:   r_type   <= win_wdata[6:0];
                    A_STATUS: r_status <= win_wdata[7:0];
                    A_SEQ:    r_seq    <= win_wdata[15:0];
                    A_IDX:    r_idx    <= win_wdata[6:0];
                    default: ;
                endcase
            end
            if (pb_wr) begin
                if (cnt < 5'd24) cnt <= cnt + 5'd1;
                else             ovf <= 1'b1;
            end
            if (bld_st) begin
                building <= 1'b1;
                k        <= '0;
                crc      <= 32'hFFFFFFFF;
                s_type   <= r_type;
                s_status <= r_status;
                s_seq    <= r_seq;
            end else if (building) begin
                k   <= k + 6'd1;
                crc <= in_data ? crc8(crc, cur_byte) : {8'hFF, crc[31:8]};
                if (last) begin
                    building   <= 1'b0;
                    bank       <= ~bank;
                    rep_len    <= 6'd9 + {1'b0, cnt};
                    rep_status <= s_status;
                    cnt        <= '0;
                    ovf        <= 1'b0;
                end
            end
        end
    end

    // ---- read path ----
    wire [7:0] rd_byte = ({1'b0, r_idx} < {2'b0, rep_len}) ? rep_mem[{bank, r_idx[5:0]}] : 8'h00;
    logic [31:0] rd_mux;
    always_comb begin
        case (win_addr)
            A_TYPE:   rd_mux = {25'h0, r_type};
            A_STATUS: rd_mux = {24'h0, r_status};
            A_SEQ:    rd_mux = {16'h0, r_seq};
            A_IDX:    rd_mux = {25'h0, r_idx};
            A_BYTE:   rd_mux = {24'h0, rd_byte};
            A_LEN:    rd_mux = {26'h0, rep_len};
            A_STAT:   rd_mux = {30'h0, ovf, building};
            A_PLEN:   rd_mux = {27'h0, cnt};
            default:  rd_mux = 32'h0;
        endcase
    end
    always_ff @(posedge clk) begin
        if (rst)         win_rdata <= '0;
        else if (win_rd) win_rdata <= rd_mux;
    end

    assign led = {rep_status, 2'b00, rep_len};
endmodule
