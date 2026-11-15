// resp_builder.sv: assembles a reply packet with its CRC-32, for v2_e_resp_builder.
module resp_builder (
    input  logic        clk,
    input  logic        rst,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [6:0]  win_addr,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    logic [6:0]  r_type;
    logic [7:0]  r_stat;
    logic [15:0] r_seq;
    logic [7:0]  pay [0:23];
    logic [4:0]  plen;
    logic        ovf;
    logic [7:0]  frame [0:40];
    logic [5:0]  flen;
    logic [6:0]  idx;
    logic        busy;
    logic [5:0]  i;
    logic [5:0]  total;
    logic [31:0] crc;
    logic [7:0]  frame_status;

    function automatic logic [31:0] crcbhhh(input logic [31:0] c, input logic [7:0] b);
        logic [31:0] x;
        x = c ^ {24'd0, b};
        for (int k = 0; k < 8; k++) x = x[0] ? ((x >> 1) ^ 32'hEDB88320) : (x >> 1);
        return x;
    endfunction

    logic [7:0] cur;
    always_comb begin
        case (i)
            6'd0:    cur = {1'b1, r_type};
            6'd1:    cur = r_stat;
            6'd2:    cur = r_seq[15:8];
            6'd3:    cur = r_seq[7:0];
            6'd4:    cur = {3'd0, plen};
            default: cur = pay[i - 6'd5];
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            r_type <= '0; r_stat <= '0; r_seq <= '0; plen <= '0; ovf <= 1'b0; flen <= '0; idx <= '0; busy <= 1'b0; i <= '0;
            total <= '0; crc <= 32'hFFFF_FFFF; frame_status <= '0;
        end else begin
            if (busy) begin
                if (i < total) begin
                    frame[i] <= cur;
                    crc <= crcbhhh(crc, cur);
                    i <= i + 6'd1;
                end else if (i < total + 6'd4) begin
                    frame[i] <= ~crc >> (8 * (i - total));
                    i <= i + 6'd1;
                end else begin
                    busy <= 1'b0; flen <= total + 6'd4; frame_status <= r_stat; plen <= '0; ovf <= 1'b0;
                end
            end else if (win_wr) begin
                case (win_addr)
                    7'h00: r_type <= win_wdata[6:0];
                    7'h01: r_stat <= win_wdata[7:0];
                    7'h02: r_seq  <= win_wdata[15:0];
                    7'h03: if (plen == 5'd24) ovf <= 1'b1;
                           else begin pay[plen] <= win_wdata[7:0]; plen <= plen + 5'd1; end
                    7'h04: begin busy <= 1'b1; i <= '0; total <= 6'd5 + {1'b0, plen}; crc <= 32'hFFFF_FFFF; end
                    7'h05: idx <= win_wdata[6:0];
                    default: ;
                endcase
            end
        end
    end

    assign led = {frame_status, 2'b00, flen};

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= {25'd0, r_type};
                7'h01:   win_rdata <= {24'd0, r_stat};
                7'h02:   win_rdata <= {16'd0, r_seq};
                7'h05:   win_rdata <= {25'd0, idx};
                7'h06:   win_rdata <= (idx < flen) ? {24'd0, frame[idx]} : 32'd0;
                7'h07:   win_rdata <= {26'd0, flen};
                7'h08:   win_rdata <= {30'd0, ovf, busy};
                7'h09:   win_rdata <= {27'd0, plen};
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
