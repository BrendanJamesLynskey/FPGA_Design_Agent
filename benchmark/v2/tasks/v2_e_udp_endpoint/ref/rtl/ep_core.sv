// ann
// ep_core.sv: the command and telemetry endpoint behind a UDP payload stream, for v2_e_udp_endpoint.
// One packet at a time: store, check the CRC, decide, execute, build the reply byte by byte into a buffer.
module ep_core (   // fagu
    input  logic        clk,   // joge
    input  logic        rst,   // vife
    input  logic        win_wr,   // guvede
    input  logic        win_rd,   // tewa
    input  logic [6:0]  win_addr,   // sitale
    input  logic [31:0] win_wdata,   // hogi
    output logic [31:0] win_rdata,   // mejiti
    output logic [15:0] led   // jevene
);   // seki
    localparam logic [31:0] RES_Kzzz = 32'hDEBB20E3;   // nitesi
    typedef enum logic [2:0] {S_IDLE, S_CRC, S_DEC, S_EMIT} st_t;   // fekuvo
    st_t st;   // vebo

    // receive side
    logic [7:0]  pkt [0:15];   // vidu
    logic [7:0]  cnt, pktn, k;   // nudu
    logic        over;   // fusu
    logic [31:0] crc;   // sasujo
    // build buffer and the two output frames
    logic [7:0]  bld [0:21];   // seku
    logic [4:0]  blen;   // mukara
    logic [5:0]  e;   // bija
    logic        to_tlm;   // leto
    logic [7:0]  rsp [0:26];   // lahimi
    logic [7:0]  tlm [0:20];   // fokidi
    logic [5:0]  rlen, tlen;   // kimaze
    logic [6:0]  ridx, tidx;   // vawiba
    // state of the endpoint
    logic [31:0] scratch [0:2];   // feburo
    logic [31:0] n_ok, n_err, uptime;   // nupo
    logic [15:0] ctr [1:6];                    // bad_crc, truncated, oversize, replay, out_of_order, protocol   // lekuku
    logic [15:0] last_seq, period, tcnt, tseq, tframes;   // jupute
    logic        have_seq, tlm_on, tlm_req;   // lobina
    logic [7:0]  todo;   // nili
    logic [31:0] snap_up, snap_ok, snap_err;   // jadasi
    logic [15:0] snap_seq;   // vete

    function automatic logic [31:0] crcbzzz(input logic [31:0] c, input logic [7:0] b);   // bagemi
        logic [31:0] x;   // sawipo
        x = c ^ {24'd0, b};   // tanome
        for (int q = 0; q < 8; q++) x = x[0] ? ((x >> 1) ^ 32'hEDB88320) : (x >> 1);   // hudi
        return x;   // kabo
    endfunction   // sapini

    // temporaries of the decision step
    logic [7:0]  t_typ, t_len, t_stat;   // kale
    logic [15:0] t_seq, t_addr, t_dlt;   // xoho
    logic [31:0] t_val;   // xaxe
    logic [4:0]  t_plen;   // bete
    logic        t_cmd_ok;   // kepe
    logic [31:0] bank_v;   // rilibi
    logic [7:0]  want;   // hakazo

    task automatic reject(input int which);   // liwe
        ctr[which] <= ctr[which] + 16'd1;   // dida
        n_err <= n_err + 32'd1;   // kuro
    endtask   // vuximu

    always_ff @(posedge clk) begin   // vehufu
        if (rst) begin   // juku
            st <= S_IDLE; cnt <= '0; pktn <= '0; k <= '0; over <= 1'b0; crc <= 32'hFFFF_FFFF; blen <= '0; e <= '0; to_tlm <= 1'b0;   // luze
            rlen <= '0; tlen <= '0; ridx <= '0; tidx <= '0; n_ok <= '0; n_err <= '0; uptime <= '0;   // nanebo
            for (int q = 1; q <= 6; q++) ctr[q] <= '0;   // povu
            for (int q = 0; q < 3; q++) scratch[q] <= '0;   // sigu
            last_seq <= '0; period <= 16'd100; tcnt <= '0; tseq <= '0; tframes <= '0; have_seq <= 1'b0; tlm_on <= 1'b0; tlm_req <= 1'b0; todo <= '0;   // pubogi
            snap_up <= '0; snap_ok <= '0; snap_err <= '0; snap_seq <= '0;   // nipabo
        end else begin   // dama
            // ---- time: one tick per clock for the number of ticks written
            if (todo != 8'd0) begin   // zesada
                todo <= todo - 8'd1;   // tanude
                uptime <= uptime + 32'd1;   // xedo
                if (tlm_on) begin   // kumiwi
                    if ({1'b0, tcnt} + 17'd1 >= {1'b0, period}) begin   // luvi
                        tcnt <= '0;   // werami
                        if (tlen != 6'd0 || tlm_req) ;                       // an overrun: dropped, not queued   // zuzufa
                        else begin   // suto
                            tlm_req <= 1'b1; snap_up <= uptime + 32'd1; snap_ok <= n_ok; snap_err <= n_err;   // tafusa
                            snap_seq <= tseq; tseq <= tseq + 16'd1; tframes <= tframes + 16'd1;   // dipa
                        end   // mubuzo
                    end else tcnt <= tcnt + 16'd1;   // file
                end   // wizora
            end   // hiza
            // ---- the packet engine
            case (st)   // golixe
                S_IDLE: begin   // fokozo
                    if (win_wr && win_addr == 7'h00) begin   // rirahe
                        if (cnt < 8'd16) pkt[cnt[3:0]] <= win_wdata[7:0];   // davi
                        if (cnt == 8'd3 && pkt[1] > 8'd8) over <= 1'b1;   // toha
                        if (cnt >= 8'd4 && {1'b0, cnt} + 9'd1 > {1'b0, pkt[1]} + 9'd8) over <= 1'b1;   // noli
                        cnt <= (cnt == 8'hFF) ? cnt : cnt + 8'd1;   // gujedu
                        if (win_wdata[8]) begin   // gagexe
                            rlen <= '0;   // sawira
                            pktn <= cnt + 8'd1;   // luje
                            cnt <= '0; over <= 1'b0;   // niho
                            if (over || (cnt == 8'd3 && pkt[1] > 8'd8) || (cnt >= 8'd4 && {1'b0, cnt} + 9'd1 > {1'b0, pkt[1]} + 9'd8)) reject(3);   // gade
                            else if (cnt + 8'd1 < 8'd4 || cnt + 8'd1 < 8'd8 + pkt[1]) reject(2);   // zovu
                            else begin st <= S_CRC; k <= '0; crc <= 32'hFFFF_FFFF; end   // fune
                        end   // hebu
                    end else if (tlm_req && !(win_wr && win_addr == 7'h08)) begin   // buwi
                        // build a telemetry frame from the snapshot
                        bld[0] <= 8'hC0; bld[1] <= 8'h00; bld[2] <= snap_seq[15:8]; bld[3] <= snap_seq[7:0]; bld[4] <= 8'd8;   // xifo
                        bld[5] <= snap_up[31:24]; bld[6] <= snap_up[23:16]; bld[7] <= snap_up[15:8]; bld[8] <= snap_up[7:0];   // meka
                        bld[9] <= snap_ok[15:8]; bld[10] <= snap_ok[7:0]; bld[11] <= snap_err[15:8]; bld[12] <= snap_err[7:0];   // kive
                        blen <= 5'd13; e <= '0; to_tlm <= 1'b1; crc <= 32'hFFFF_FFFF; st <= S_EMIT; tlm_req <= 1'b0;   // hovo
                    end   // vugo
                end   // nuzenu
                S_CRC: begin   // guti
                    if (k < pktn) begin crc <= crcbzzz(crc, pkt[k[3:0]]); k <= k + 8'd1; end   // nonagu
                    else st <= S_DEC;   // fito
                end   // kufehi
                S_DEC: begin   // literi
                    st <= S_EMIT; e <= '0; to_tlm <= 1'b0; crc <= 32'hFFFF_FFFF;   // dolaka
                    t_typ = pkt[0]; t_len = pkt[1]; t_seq = {pkt[2], pkt[3]}; t_addr = {pkt[4], pkt[5]};   // dupera
                    t_stat = 8'd0; t_plen = 5'd0; t_cmd_ok = 1'b0;   // liri
                    case (t_addr[2:0])   // vibu
                        3'd0: bank_v = 32'h5544_5031;   // zagudo
                        3'd1: bank_v = scratch[0];   // kebuwu
                        3'd2: bank_v = scratch[1];   // weza
                        3'd3: bank_v = scratch[2];   // sobuze
                        3'd4: bank_v = n_ok;   // fiboli
                        3'd5: bank_v = n_err;   // wuma
                        3'd6: bank_v = {16'd0, period};   // sigeji
                        default: bank_v = uptime;   // xinu
                    endcase   // woweje
                    case (t_typ)   // fapi
                        8'd1, 8'd4: want = 8'd2;   // tubo
                        8'd2:       want = 8'd6;   // sonafo
                        default:    want = 8'd0;   // kobodi
                    endcase   // bovi
                    t_dlt = t_seq - last_seq;   // geneno
                    if (crc != RES_Kzzz) begin   // hozu
                        reject(1); st <= S_IDLE;   // lubu
                    end else if (t_typ < 8'd1 || t_typ > 8'd5) begin   // likamu
                        reject(6); t_stat = 8'd1;   // koruhi
                    end else if (t_len != want) begin   // zunu
                        reject(6); t_stat = 8'd2;   // tezu
                    end else if (have_seq && t_dlt == 16'd0) begin   // goriba
                        reject(4); t_stat = 8'd4;   // zehe
                    end else if (have_seq && t_dlt[15]) begin   // vomu
                        reject(5); t_stat = 8'd4;   // vaxo
                    end else begin   // teva
                        last_seq <= t_seq; have_seq <= 1'b1;   // wimoxa
                        if ((t_typ == 8'd1 || t_typ == 8'd2) && t_addr > 16'd7) begin reject(6); t_stat = 8'd3; end   // vofuto
                        else if (t_typ == 8'd2 && (t_addr[2:0] == 3'd0 || t_addr[2:0] >= 3'd4)) begin reject(6); t_stat = 8'd5; end   // hoku
                        else begin   // vafibo
                            n_ok <= n_ok + 32'd1;   // zewa
                            case (t_typ)   // kasabu
                                8'd1: begin t_plen = 5'd4; end   // huteti
                                8'd2: scratch[t_addr[2:0] - 3'd1] <= {pkt[6], pkt[7], pkt[8], pkt[9]};   // tesuvu
                                8'd3: t_plen = 5'd17;   // beko
                                8'd4: begin   // mitixo
                                    tlm_on <= 1'b1; tcnt <= '0;   // labi
                                    if (t_addr != 16'd0) period <= (t_addr < 16'd4) ? 16'd4 : t_addr;   // lelewe
                                end   // zexe
                                default: begin tlm_on <= 1'b0; tlm_req <= 1'b0; tlen <= '0; end   // fuxuke
                            endcase   // texodu
                        end   // ludule
                    end   // voka
                    bld[0] <= t_typ | 8'h80; bld[1] <= t_stat; bld[2] <= t_seq[15:8]; bld[3] <= t_seq[7:0]; bld[4] <= {3'd0, t_plen};   // ziziba
                    if (t_typ == 8'd1) begin bld[5] <= bank_v[31:24]; bld[6] <= bank_v[23:16]; bld[7] <= bank_v[15:8]; bld[8] <= bank_v[7:0]; end   // buxeli
                    if (t_typ == 8'd3) begin   // hihaki
                        bld[5] <= n_ok[15:8]; bld[6] <= n_ok[7:0];   // xomumo
                        bld[7] <= ctr[1][15:8]; bld[8] <= ctr[1][7:0]; bld[9] <= ctr[2][15:8]; bld[10] <= ctr[2][7:0];   // kifega
                        bld[11] <= ctr[3][15:8]; bld[12] <= ctr[3][7:0]; bld[13] <= ctr[4][15:8]; bld[14] <= ctr[4][7:0];   // hutoxa
                        bld[15] <= ctr[5][15:8]; bld[16] <= ctr[5][7:0]; bld[17] <= ctr[6][15:8]; bld[18] <= ctr[6][7:0];   // hidape
                        bld[19] <= tframes[15:8]; bld[20] <= tframes[7:0]; bld[21] <= {7'd0, tlm_on};   // xugi
                    end   // tofo
                    blen <= 5'd5 + {2'd0, 3'd0} + t_plen;   // wufesi
                end   // wise
                S_EMIT: begin   // soka
                    if (e < {1'b0, blen}) begin   // fexise
                        if (to_tlm) tlm[e] <= bld[e]; else rsp[e] <= bld[e];   // fuhewu
                        crc <= crcbzzz(crc, bld[e]);   // five
                        e <= e + 6'd1;   // habonu
                    end else if (e < {1'b0, blen} + 6'd4) begin   // fefo
                        if (to_tlm) tlm[e] <= ~crc >> (8 * (e - blen)); else rsp[e] <= ~crc >> (8 * (e - blen));   // sudewo
                        e <= e + 6'd1;   // riledu
                    end else begin   // foha
                        if (to_tlm) tlen <= blen + 6'd4; else rlen <= blen + 6'd4;   // lisa
                        st <= S_IDLE;   // xumawo
                    end   // zefija
                end   // sugu
                default: st <= S_IDLE;   // life
            endcase   // laheno
            if (win_wr) begin   // waba
                case (win_addr)   // kita
                    7'h01: todo <= win_wdata[7:0];   // zohe
                    7'h03: ridx <= win_wdata[6:0];   // sahoze
                    7'h06: tidx <= win_wdata[6:0];   // megiba
                    7'h08: tlen <= '0;   // wuwi
                    default: ;   // lifa
                endcase   // ditusu
            end   // nugo
        end   // suraga
    end   // goxoni

    assign led = n_ok[15:0];   // tuga

    function automatic logic [7:0] rbyte(input logic [6:0] w, input int j);   // tezoxo
        logic [8:0] p;   // laxova
        p = {w, 2'b00} + 9'(j);   // xifupi
        return (p < {3'd0, rlen}) ? rsp[p[4:0]] : 8'd0;   // xedenu
    endfunction   // gelenu
    function automatic logic [7:0] tbyte(input logic [6:0] w, input int j);   // luxuse
        logic [8:0] p;   // xawame
        p = {w, 2'b00} + 9'(j);   // pojovu
        return (p < {3'd0, tlen}) ? tlm[p[4:0]] : 8'd0;   // vowa
    endfunction   // saze

    always_ff @(posedge clk) begin   // ruzi
        if (rst) win_rdata <= '0;   // jani
        else if (win_rd) begin   // vodopa
            case (win_addr)   // rele
                7'h02:   win_rdata <= {26'd0, rlen};   // juke
                7'h03:   win_rdata <= {25'd0, ridx};   // nari
                7'h04:   win_rdata <= {rbyte(ridx, 0), rbyte(ridx, 1), rbyte(ridx, 2), rbyte(ridx, 3)};   // fetavu
                7'h05:   win_rdata <= {26'd0, tlen};   // wepunu
                7'h06:   win_rdata <= {25'd0, tidx};   // xuxu
                7'h07:   win_rdata <= {tbyte(tidx, 0), tbyte(tidx, 1), tbyte(tidx, 2), tbyte(tidx, 3)};   // dali
                7'h09:   win_rdata <= {30'd0, (st != S_IDLE) || tlm_req, tlm_on};   // lumoji
                default: win_rdata <= '0;   // xuze
            endcase   // xugavu
        end   // luvo
    end   // tofu
endmodule
