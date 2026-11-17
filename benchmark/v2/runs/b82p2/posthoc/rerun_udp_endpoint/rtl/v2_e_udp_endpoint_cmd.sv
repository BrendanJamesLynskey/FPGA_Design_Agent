// Packet collector, refusal rules, register file, counters and reply builder.
module v2_e_udp_endpoint_cmd #(
    parameter logic [31:0] ID_WORD = 32'h55445031
) (
    input  logic        clk,
    input  logic        rst,
    // IN register of the shell window
    input  logic        in_wr,
    input  logic [7:0]  in_byte,
    input  logic        in_end,
    // reply read-out
    input  logic [6:0]  ridx,
    output logic [5:0]  rlen,
    output logic [31:0] rword,
    output logic        busy,
    // telemetry block
    input  logic        tel_on,
    input  logic [15:0] tel_period,
    input  logic [31:0] tel_ticks,
    input  logic [15:0] tel_fcount,
    output logic        start_en,
    output logic [15:0] start_period,
    output logic        stop_en,
    output logic [15:0] cmds,
    output logic [15:0] refused
);
    typedef enum logic [2:0] {S_IDLE, S_D1, S_D2, S_D3, S_BLD, S_COMMIT} st_t;
    st_t st;

    logic [7:0]  pbuf    [0:9];
    logic [7:0]  rep_buf [0:31];
    logic [4:0]  n;
    logic [4:0]  k;
    logic [31:0] rxcrc, rcrc;
    logic [15:0] last_seq;
    logic        last_valid;
    logic [31:0] scratch [0:2];
    logic [15:0] cnt     [0:5];

    // decision flags (D1) and outcome (D2)
    logic        f_s1, f_long, f_s2, f_crc, f_tk, f_len, f_seqnew, f_seqrep, f_unk, f_rw;
    logic        o_drop, o_ref, o_acc;
    logic [2:0]  o_cls, o_status;
    logic [4:0]  o_plen;
    logic [31:0] rdval;

    wire [7:0]  typ   = pbuf[0];
    wire [7:0]  ln    = pbuf[1];
    wire [15:0] seqn  = {pbuf[2], pbuf[3]};
    wire [15:0] reg16 = {pbuf[4], pbuf[5]};
    wire [15:0] dseq  = seqn - last_seq;

    logic [7:0] want;
    always_comb begin
        case (typ)
            8'd1:    want = 8'd2;
            8'd2:    want = 8'd6;
            8'd4:    want = 8'd2;
            default: want = 8'd0;
        endcase
    end

    wire accept = in_wr && (st == S_IDLE);

    logic [31:0] rx_crc_o, r_crc_o;
    v2_e_udp_endpoint_crc8 u_crc_rx (.crc_in(rxcrc), .data(in_byte), .crc_out(rx_crc_o));

    // reply byte generator
    wire [4:0] k5 = 5'd5 + o_plen;
    wire [4:0] kj = k - 5'd5;
    logic [135:0] sv_all;
    assign sv_all = {cmds, cnt[0], cnt[1], cnt[2], cnt[3], cnt[4], cnt[5], tel_fcount, 7'd0, tel_on};
    logic [7:0] sbyte, rbyte, bld_byte;
    always_comb begin
        sbyte = (kj < 5'd17) ? sv_all[(5'd16 - kj) * 8 +: 8] : 8'h00;
        case (kj[1:0])
            2'd0:    rbyte = rdval[31:24];
            2'd1:    rbyte = rdval[23:16];
            2'd2:    rbyte = rdval[15:8];
            default: rbyte = rdval[7:0];
        endcase
        case (k)
            5'd0:    bld_byte = typ | 8'h80;
            5'd1:    bld_byte = {5'd0, o_status};
            5'd2:    bld_byte = pbuf[2];
            5'd3:    bld_byte = pbuf[3];
            5'd4:    bld_byte = {3'd0, o_plen};
            default: begin
                if (k < k5) bld_byte = (typ == 8'd3) ? sbyte : rbyte;
                else        bld_byte = ~rcrc[7:0];
            end
        endcase
    end
    v2_e_udp_endpoint_crc8 u_crc_r (.crc_in(rcrc), .data(bld_byte), .crc_out(r_crc_o));

    assign busy = (st != S_IDLE);

    // control
    always_ff @(posedge clk) begin
        if (rst) begin
            st         <= S_IDLE;
            n          <= 5'd0;
            k          <= 5'd0;
            rxcrc      <= 32'hFFFFFFFF;
            rlen       <= 6'd0;
            cmds       <= 16'd0;
            refused    <= 16'd0;
            last_valid <= 1'b0;
            start_en   <= 1'b0;
            stop_en    <= 1'b0;
            for (int i = 0; i < 6; i++) cnt[i] <= 16'd0;
            for (int i = 0; i < 3; i++) scratch[i] <= 32'd0;
        end else begin
            start_en <= 1'b0;
            stop_en  <= 1'b0;
            case (st)
                S_IDLE: begin
                    if (in_wr) begin
                        if (n != 5'd31) n <= n + 5'd1;
                        rxcrc <= rx_crc_o;
                        if (in_end) begin
                            rlen <= 6'd0;
                            st   <= S_D1;
                        end
                    end
                end
                S_D1: st <= S_D2;
                S_D2: st <= S_D3;
                S_D3: begin
                    k  <= 5'd0;
                    st <= o_drop ? S_COMMIT : S_BLD;
                end
                S_BLD: begin
                    k <= k + 5'd1;
                    if (k == (5'd8 + o_plen)) begin
                        rlen <= 6'd9 + {1'b0, o_plen};
                        st   <= S_COMMIT;
                    end
                end
                S_COMMIT: begin
                    n     <= 5'd0;
                    rxcrc <= 32'hFFFFFFFF;
                    st    <= S_IDLE;
                    if (o_ref) begin
                        refused <= refused + 16'd1;
                        cnt[o_cls] <= cnt[o_cls] + 16'd1;
                    end
                    if (o_acc) last_valid <= 1'b1;
                    if (!o_drop && o_status == 3'd0) begin
                        cmds <= cmds + 16'd1;
                        case (typ)
                            8'd2: begin
                                case (reg16[1:0])
                                    2'd1:    scratch[0] <= {pbuf[6], pbuf[7], pbuf[8], pbuf[9]};
                                    2'd2:    scratch[1] <= {pbuf[6], pbuf[7], pbuf[8], pbuf[9]};
                                    default: scratch[2] <= {pbuf[6], pbuf[7], pbuf[8], pbuf[9]};
                                endcase
                            end
                            8'd4:    start_en <= 1'b1;
                            8'd5:    stop_en  <= 1'b1;
                            default: ;
                        endcase
                    end
                end
                default: st <= S_IDLE;
            endcase
        end
    end

    // datapath (no reset)
    always_ff @(posedge clk) begin
        if (accept && n < 5'd10) pbuf[n[3:0]] <= in_byte;

        case (st)
            S_D1: begin
                f_s1     <= (n < 5'd4);
                f_long   <= (ln > 8'd8) || ({3'd0, n} > ln + 8'd8);
                f_s2     <= ({3'd0, n} < ln + 8'd8);
                f_crc    <= (rxcrc != 32'hDEBB20E3);
                f_tk     <= (typ >= 8'd1) && (typ <= 8'd5);
                f_len    <= (ln == want);
                f_seqnew <= !last_valid || (dseq != 16'd0 && !dseq[15]);
                f_seqrep <= last_valid && (dseq == 16'd0);
                f_unk    <= |reg16[15:3];
                f_rw     <= !(|reg16[15:3]) && (reg16[2:0] >= 3'd1) && (reg16[2:0] <= 3'd3);
            end
            S_D2: begin
                o_drop   <= 1'b0;
                o_ref    <= 1'b0;
                o_acc    <= 1'b0;
                o_cls    <= 3'd0;
                o_status <= 3'd0;
                o_plen   <= 5'd0;
                if (f_s1) begin
                    o_drop <= 1'b1; o_ref <= 1'b1; o_cls <= 3'd1;
                end else if (f_long) begin
                    o_drop <= 1'b1; o_ref <= 1'b1; o_cls <= 3'd2;
                end else if (f_s2) begin
                    o_drop <= 1'b1; o_ref <= 1'b1; o_cls <= 3'd1;
                end else if (f_crc) begin
                    o_drop <= 1'b1; o_ref <= 1'b1; o_cls <= 3'd0;
                end else if (!f_tk) begin
                    o_ref <= 1'b1; o_cls <= 3'd5; o_status <= 3'd1;
                end else if (!f_len) begin
                    o_ref <= 1'b1; o_cls <= 3'd5; o_status <= 3'd2;
                end else if (!f_seqnew) begin
                    o_ref <= 1'b1; o_status <= 3'd4;
                    o_cls <= f_seqrep ? 3'd3 : 3'd4;
                end else begin
                    o_acc <= 1'b1;
                    if ((typ == 8'd1 || typ == 8'd2) && f_unk) begin
                        o_ref <= 1'b1; o_cls <= 3'd5; o_status <= 3'd3;
                    end else if (typ == 8'd2 && !f_rw) begin
                        o_ref <= 1'b1; o_cls <= 3'd5; o_status <= 3'd5;
                    end else begin
                        if (typ == 8'd1) o_plen <= 5'd4;
                        if (typ == 8'd3) o_plen <= 5'd17;
                    end
                end
                case (reg16[2:0])
                    3'd0:    rdval <= ID_WORD;
                    3'd1:    rdval <= scratch[0];
                    3'd2:    rdval <= scratch[1];
                    3'd3:    rdval <= scratch[2];
                    3'd4:    rdval <= {16'd0, cmds};
                    3'd5:    rdval <= {16'd0, refused};
                    3'd6:    rdval <= {16'd0, tel_period};
                    default: rdval <= tel_ticks;
                endcase
                rcrc <= 32'hFFFFFFFF;
            end
            S_BLD: begin
                rep_buf[k[4:0]] <= bld_byte;
                rcrc <= (k < k5) ? r_crc_o : (rcrc >> 8);
            end
            S_COMMIT: begin
                if (o_acc) last_seq <= seqn;
                start_period <= reg16;
            end
            default: ;
        endcase
    end

    // word read-out, zero past the end
    wire [8:0] ridx4 = {ridx, 2'b00};
    function automatic logic [7:0] rb(input logic [8:0] idx);
        if (idx < {3'd0, rlen} && idx < 9'd32) rb = rep_buf[idx[4:0]];
        else rb = 8'h00;
    endfunction
    assign rword = {rb(ridx4), rb(ridx4 + 9'd1), rb(ridx4 + 9'd2), rb(ridx4 + 9'd3)};
endmodule
