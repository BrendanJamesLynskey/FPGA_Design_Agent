// ep_core.sv: the command and telemetry endpoint behind a UDP payload stream, for v2_e_udp_endpoint.
// One packet at a time: store, check the CRC, decide, execute, build the reply byte by byte into a buffer.
module ep_core (
    input  logic        clk,
    input  logic        rst,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [6:0]  win_addr,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam logic [31:0] RES_Kzzz = 32'hDEBB20E3;
    typedef enum logic [2:0] {S_IDLE, S_CRC, S_DEC, S_EMIT} st_t;
    st_t st;

    // receive side
    logic [7:0]  pkt [0:15];
    logic [7:0]  cnt, pktn, k;
    logic        over;
    logic [31:0] crc;
    // build buffer and the two output frames
    logic [7:0]  bld [0:21];
    logic [4:0]  blen;
    logic [5:0]  e;
    logic        to_tlm;
    logic [7:0]  rsp [0:26];
    logic [7:0]  tlm [0:20];
    logic [5:0]  rlen, tlen;
    logic [6:0]  ridx, tidx;
    // state of the endpoint
    logic [31:0] scratch [0:2];
    logic [31:0] n_ok, n_err, uptime;
    logic [15:0] ctr [1:6];                    // bad_crc, truncated, oversize, replay, out_of_order, protocol
    logic [15:0] last_seq, period, tcnt, tseq, tframes;
    logic        have_seq, tlm_on, tlm_req;
    logic [7:0]  todo;
    logic [31:0] snap_up, snap_ok, snap_err;
    logic [15:0] snap_seq;

    function automatic logic [31:0] crcbzzz(input logic [31:0] c, input logic [7:0] b);
        logic [31:0] x;
        x = c ^ {24'd0, b};
        for (int q = 0; q < 8; q++) x = x[0] ? ((x >> 1) ^ 32'hEDB88320) : (x >> 1);
        return x;
    endfunction

    // temporaries of the decision step
    logic [7:0]  t_typ, t_len, t_stat;
    logic [15:0] t_seq, t_addr, t_dlt;
    logic [31:0] t_val;
    logic [4:0]  t_plen;
    logic        t_cmd_ok;
    logic [31:0] bank_v;
    logic [7:0]  want;

    task automatic reject(input int which);
        ctr[which] <= ctr[which] + 16'd1;
        n_err <= n_err + 32'd1;
    endtask

    always_ff @(posedge clk) begin
        if (rst) begin
            st <= S_IDLE; cnt <= '0; pktn <= '0; k <= '0; over <= 1'b0; crc <= 32'hFFFF_FFFF; blen <= '0; e <= '0; to_tlm <= 1'b0;
            rlen <= '0; tlen <= '0; ridx <= '0; tidx <= '0; n_ok <= '0; n_err <= '0; uptime <= '0;
            for (int q = 1; q <= 6; q++) ctr[q] <= '0;
            for (int q = 0; q < 3; q++) scratch[q] <= '0;
            last_seq <= '0; period <= 16'd100; tcnt <= '0; tseq <= '0; tframes <= '0; have_seq <= 1'b0; tlm_on <= 1'b0; tlm_req <= 1'b0; todo <= '0;
            snap_up <= '0; snap_ok <= '0; snap_err <= '0; snap_seq <= '0;
        end else begin
            // ---- time: one tick per clock for the number of ticks written
            if (todo != 8'd0) begin
                todo <= todo - 8'd1;
                uptime <= uptime + 32'd1;
                if (tlm_on) begin
                    if ({1'b0, tcnt} + 17'd1 >= {1'b0, period}) begin
                        tcnt <= '0;
                        if (tlen != 6'd0 || tlm_req) ;                       // an overrun: dropped, not queued
                        else begin
                            tlm_req <= 1'b1; snap_up <= uptime + 32'd1; snap_ok <= n_ok; snap_err <= n_err;
                            snap_seq <= tseq; tseq <= tseq + 16'd1; tframes <= tframes + 16'd1;
                        end
                    end else tcnt <= tcnt + 16'd1;
                end
            end
            // ---- the packet engine
            case (st)
                S_IDLE: begin
                    if (win_wr && win_addr == 7'h00) begin
                        if (cnt < 8'd16) pkt[cnt[3:0]] <= win_wdata[7:0];
                        if (cnt == 8'd3 && pkt[1] > 8'd8) over <= 1'b1;
                        if (cnt >= 8'd4 && {1'b0, cnt} + 9'd1 > {1'b0, pkt[1]} + 9'd8) over <= 1'b1;
                        cnt <= (cnt == 8'hFF) ? cnt : cnt + 8'd1;
                        if (win_wdata[8]) begin
                            rlen <= '0;
                            pktn <= cnt + 8'd1;
                            cnt <= '0; over <= 1'b0;
                            if (over || (cnt == 8'd3 && pkt[1] > 8'd8) || (cnt >= 8'd4 && {1'b0, cnt} + 9'd1 > {1'b0, pkt[1]} + 9'd8)) reject(3);
                            else if (cnt + 8'd1 < 8'd4 || cnt + 8'd1 < 8'd8 + pkt[1]) reject(2);
                            else begin st <= S_CRC; k <= '0; crc <= 32'hFFFF_FFFF; end
                        end
                    end else if (tlm_req && !(win_wr && win_addr == 7'h08)) begin
                        // build a telemetry frame from the snapshot
                        bld[0] <= 8'hC0; bld[1] <= 8'h00; bld[2] <= snap_seq[15:8]; bld[3] <= snap_seq[7:0]; bld[4] <= 8'd8;
                        bld[5] <= snap_up[31:24]; bld[6] <= snap_up[23:16]; bld[7] <= snap_up[15:8]; bld[8] <= snap_up[7:0];
                        bld[9] <= snap_ok[15:8]; bld[10] <= snap_ok[7:0]; bld[11] <= snap_err[15:8]; bld[12] <= snap_err[7:0];
                        blen <= 5'd13; e <= '0; to_tlm <= 1'b1; crc <= 32'hFFFF_FFFF; st <= S_EMIT; tlm_req <= 1'b0;
                    end
                end
                S_CRC: begin
                    if (k < pktn) begin crc <= crcbzzz(crc, pkt[k[3:0]]); k <= k + 8'd1; end
                    else st <= S_DEC;
                end
                S_DEC: begin
                    st <= S_EMIT; e <= '0; to_tlm <= 1'b0; crc <= 32'hFFFF_FFFF;
                    t_typ = pkt[0]; t_len = pkt[1]; t_seq = {pkt[2], pkt[3]}; t_addr = {pkt[4], pkt[5]};
                    t_stat = 8'd0; t_plen = 5'd0; t_cmd_ok = 1'b0;
                    case (t_addr[2:0])
                        3'd0: bank_v = 32'h5544_5031;
                        3'd1: bank_v = scratch[0];
                        3'd2: bank_v = scratch[1];
                        3'd3: bank_v = scratch[2];
                        3'd4: bank_v = n_ok;
                        3'd5: bank_v = n_err;
                        3'd6: bank_v = {16'd0, period};
                        default: bank_v = uptime;
                    endcase
                    case (t_typ)
                        8'd1, 8'd4: want = 8'd2;
                        8'd2:       want = 8'd6;
                        default:    want = 8'd0;
                    endcase
                    t_dlt = t_seq - last_seq;
                    if (crc != RES_Kzzz) begin
                        reject(1); st <= S_IDLE;
                    end else if (t_typ < 8'd1 || t_typ > 8'd5) begin
                        reject(6); t_stat = 8'd1;
                    end else if (t_len != want) begin
                        reject(6); t_stat = 8'd2;
                    end else if (have_seq && t_dlt == 16'd0) begin
                        reject(4); t_stat = 8'd4;
                    end else if (have_seq && t_dlt[15]) begin
                        reject(5); t_stat = 8'd4;
                    end else begin
                        last_seq <= t_seq; have_seq <= 1'b1;
                        if ((t_typ == 8'd1 || t_typ == 8'd2) && t_addr > 16'd7) begin reject(6); t_stat = 8'd3; end
                        else if (t_typ == 8'd2 && (t_addr[2:0] == 3'd0 || t_addr[2:0] >= 3'd4)) begin reject(6); t_stat = 8'd5; end
                        else begin
                            n_ok <= n_ok + 32'd1;
                            case (t_typ)
                                8'd1: begin t_plen = 5'd4; end
                                8'd2: scratch[t_addr[2:0] - 3'd1] <= {pkt[6], pkt[7], pkt[8], pkt[9]};
                                8'd3: t_plen = 5'd17;
                                8'd4: begin
                                    tlm_on <= 1'b1; tcnt <= '0;
                                    if (t_addr != 16'd0) period <= (t_addr < 16'd4) ? 16'd4 : t_addr;
                                end
                                default: begin tlm_on <= 1'b0; tlm_req <= 1'b0; tlen <= '0; end
                            endcase
                        end
                    end
                    bld[0] <= t_typ | 8'h80; bld[1] <= t_stat; bld[2] <= t_seq[15:8]; bld[3] <= t_seq[7:0]; bld[4] <= {3'd0, t_plen};
                    if (t_typ == 8'd1) begin bld[5] <= bank_v[31:24]; bld[6] <= bank_v[23:16]; bld[7] <= bank_v[15:8]; bld[8] <= bank_v[7:0]; end
                    if (t_typ == 8'd3) begin
                        bld[5] <= n_ok[15:8]; bld[6] <= n_ok[7:0];
                        bld[7] <= ctr[1][15:8]; bld[8] <= ctr[1][7:0]; bld[9] <= ctr[2][15:8]; bld[10] <= ctr[2][7:0];
                        bld[11] <= ctr[3][15:8]; bld[12] <= ctr[3][7:0]; bld[13] <= ctr[4][15:8]; bld[14] <= ctr[4][7:0];
                        bld[15] <= ctr[5][15:8]; bld[16] <= ctr[5][7:0]; bld[17] <= ctr[6][15:8]; bld[18] <= ctr[6][7:0];
                        bld[19] <= tframes[15:8]; bld[20] <= tframes[7:0]; bld[21] <= {7'd0, tlm_on};
                    end
                    blen <= 5'd5 + {2'd0, 3'd0} + t_plen;
                end
                S_EMIT: begin
                    if (e < {1'b0, blen}) begin
                        if (to_tlm) tlm[e] <= bld[e]; else rsp[e] <= bld[e];
                        crc <= crcbzzz(crc, bld[e]);
                        e <= e + 6'd1;
                    end else if (e < {1'b0, blen} + 6'd4) begin
                        if (to_tlm) tlm[e] <= ~crc >> (8 * (e - blen)); else rsp[e] <= ~crc >> (8 * (e - blen));
                        e <= e + 6'd1;
                    end else begin
                        if (to_tlm) tlen <= blen + 6'd4; else rlen <= blen + 6'd4;
                        st <= S_IDLE;
                    end
                end
                default: st <= S_IDLE;
            endcase
            if (win_wr) begin
                case (win_addr)
                    7'h01: todo <= win_wdata[7:0];
                    7'h03: ridx <= win_wdata[6:0];
                    7'h06: tidx <= win_wdata[6:0];
                    7'h08: tlen <= '0;
                    default: ;
                endcase
            end
        end
    end

    assign led = n_ok[15:0];

    function automatic logic [7:0] rbyte(input logic [6:0] w, input int j);
        logic [8:0] p;
        p = {w, 2'b00} + 9'(j);
        return (p < {3'd0, rlen}) ? rsp[p[4:0]] : 8'd0;
    endfunction
    function automatic logic [7:0] tbyte(input logic [6:0] w, input int j);
        logic [8:0] p;
        p = {w, 2'b00} + 9'(j);
        return (p < {3'd0, tlen}) ? tlm[p[4:0]] : 8'd0;
    endfunction

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h02:   win_rdata <= {26'd0, rlen};
                7'h03:   win_rdata <= {25'd0, ridx};
                7'h04:   win_rdata <= {rbyte(ridx, 0), rbyte(ridx, 1), rbyte(ridx, 2), rbyte(ridx, 3)};
                7'h05:   win_rdata <= {26'd0, tlen};
                7'h06:   win_rdata <= {25'd0, tidx};
                7'h07:   win_rdata <= {tbyte(tidx, 0), tbyte(tidx, 1), tbyte(tidx, 2), tbyte(tidx, 3)};
                7'h09:   win_rdata <= {30'd0, (st != S_IDLE) || tlm_req, tlm_on};
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
