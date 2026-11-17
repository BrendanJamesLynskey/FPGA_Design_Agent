// cmd_parser.sv: screens command packets (framing, CRC, type, sequence) for v2_e_cmd_parser.
module cmd_parser (
    input  logic        clk,
    input  logic        rst,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [6:0]  win_addr,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam logic [31:0] RES_Kbbb = 32'hDEBB20E3;
    localparam logic [3:0]  C_NONE = 4'd0, C_OK = 4'd1, C_CRC = 4'd2, C_SHORT = 4'd3, C_LONG = 4'd4,
                            C_REPLAY = 4'd5, C_OLD = 4'd6, C_TYPE = 4'd7, C_LEN = 4'd8;

    logic [7:0]  cnt;                 // bytes of the packet so far (saturates)
    logic        mid;
    logic [31:0] crc;
    logic [7:0]  h_type, h_len;
    logic [15:0] h_seq;
    logic [7:0]  pb [0:5];
    logic        over;
    logic [3:0]  result;
    logic [7:0]  o_type;
    logic [15:0] o_seq, last_seq;
    logic [15:0] o_p0;
    logic [31:0] o_p1;
    logic        have_seq;
    logic [8:0]  last_wr;
    logic [15:0] ctr [0:6];

    function automatic logic [31:0] crcbbbb(input logic [31:0] c, input logic [7:0] b);
        logic [31:0] x;
        x = c ^ {24'd0, b};
        for (int i = 0; i < 8; i++) x = x[0] ? ((x >> 1) ^ 32'hEDB88320) : (x >> 1);
        return x;
    endfunction

    logic [7:0]  n;
    logic [7:0]  b;
    logic        fin;
    logic [31:0] cn;
    logic [7:0]  ln;
    logic [15:0] sq;
    logic        ov;
    logic [7:0]  total;
    logic [3:0]  cls;
    logic [15:0] dlt;
    logic [7:0]  need_len;
    logic        type_ok;

    always_ff @(posedge clk) begin
        if (rst) begin
            cnt <= '0; mid <= 1'b0; crc <= 32'hFFFF_FFFF; h_type <= '0; h_len <= '0; h_seq <= '0; over <= 1'b0;
            result <= C_NONE; o_type <= '0; o_seq <= '0; last_seq <= '0; o_p0 <= '0; o_p1 <= '0; have_seq <= 1'b0; last_wr <= '0;
            for (int i = 0; i < 6; i++) pb[i] <= '0;
            for (int i = 0; i < 7; i++) ctr[i] <= '0;
        end else if (win_wr && win_addr == 7'h00) begin
            last_wr <= win_wdata[8:0];
            b   = win_wdata[7:0];
            fin = win_wdata[8];
            n   = mid ? cnt : 8'd0;
            cn  = crcbbbb(mid ? crc : 32'hFFFF_FFFF, b);
            ln  = (n == 8'd1) ? b : h_len;
            sq  = h_seq;
            if (n == 8'd0) begin
                h_type <= b;
                for (int i = 0; i < 6; i++) pb[i] <= '0;
            end
            if (n == 8'd1) h_len <= b;
            if (n == 8'd2) h_seq[15:8] <= b;
            if (n == 8'd3) h_seq[7:0] <= b;
            if (n >= 8'd4 && n <= 8'd9 && (n - 8'd4) < h_len) pb[n - 8'd4] <= b;
            ov = ((n == 8'd0) ? 1'b0 : over) || (n == 8'd3 && h_len > 8'd8) || (n >= 8'd4 && ({1'b0, n} + 9'd1) > ({1'b0, h_len} + 9'd8));
            total = n + 8'd1;
            sq = (n == 8'd3) ? {h_seq[15:8], b} : h_seq;
            dlt = sq - last_seq;
            type_ok = (h_type >= 8'd1) && (h_type <= 8'd5);
            case (h_type)
                8'd1, 8'd4: need_len = 8'd2;
                8'd2:       need_len = 8'd6;
                default:    need_len = 8'd0;
            endcase
            if (!fin) begin
                mid <= 1'b1;
                cnt <= (n == 8'hFF) ? n : n + 8'd1;
                crc <= cn;
                over <= ov;
            end else begin
                mid <= 1'b0; cnt <= '0; over <= 1'b0; crc <= 32'hFFFF_FFFF;
                if (ov)                                      cls = C_LONG;
                else if (total < 8'd4 || (total < (8'd8 + h_len))) cls = C_SHORT;
                else if (cn != RES_Kbbb)                      cls = C_CRC;
                else if (!type_ok)                           cls = C_TYPE;
                else if (h_len != need_len)                  cls = C_LEN;
                else if (have_seq && dlt == 16'd0)           cls = C_REPLAY;
                else if (have_seq && dlt[15])                cls = C_OLD;
                else                                         cls = C_OK;
                result <= cls;
                case (cls)
                    C_OK:     ctr[0] <= ctr[0] + 16'd1;
                    C_CRC:    ctr[1] <= ctr[1] + 16'd1;
                    C_SHORT:  ctr[2] <= ctr[2] + 16'd1;
                    C_LONG:   ctr[3] <= ctr[3] + 16'd1;
                    C_REPLAY: ctr[4] <= ctr[4] + 16'd1;
                    C_OLD:    ctr[5] <= ctr[5] + 16'd1;
                    default:  ctr[6] <= ctr[6] + 16'd1;
                endcase
                if (cls == C_OK) begin
                    o_type <= h_type; o_seq <= h_seq; last_seq <= h_seq; have_seq <= 1'b1;
                    o_p0 <= {pb[0], pb[1]}; o_p1 <= {pb[2], pb[3], pb[4], pb[5]};
                end
            end
        end
    end

    assign led = {last_seq[7:0], ctr[0][7:0]};

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= {23'd0, last_wr};
                7'h01:   win_rdata <= {28'd0, result};
                7'h02:   win_rdata <= {24'd0, o_type};
                7'h03:   win_rdata <= {16'd0, o_seq};
                7'h04:   win_rdata <= {16'd0, o_p0};
                7'h05:   win_rdata <= o_p1;
                7'h06:   win_rdata <= {15'd0, have_seq, last_seq};
                7'h07:   win_rdata <= {31'd0, mid};
                7'h10:   win_rdata <= {16'd0, ctr[0]};
                7'h11:   win_rdata <= {16'd0, ctr[1]};
                7'h12:   win_rdata <= {16'd0, ctr[2]};
                7'h13:   win_rdata <= {16'd0, ctr[3]};
                7'h14:   win_rdata <= {16'd0, ctr[4]};
                7'h15:   win_rdata <= {16'd0, ctr[5]};
                7'h16:   win_rdata <= {16'd0, ctr[6]};
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
