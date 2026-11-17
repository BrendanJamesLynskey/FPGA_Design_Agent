// udp_engine: packet collector, CRC-32 check, refusal order, sequence rule,
// command execution, counters, scratch registers and the reply builder.
module udp_engine #(
    parameter logic [31:0] ID_WORD = 32'h55445031
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        in_wr,
    input  logic [8:0]  in_data,
    input  logic [6:0]  ridx,
    output logic [31:0] rword,
    output logic [4:0]  rlen,
    output logic        busy,
    output logic [15:0] cmds,
    output logic [15:0] refd,
    input  logic        tel_on,
    input  logic [15:0] tel_period,
    input  logic [31:0] tel_ticks,
    input  logic [15:0] tel_fcount,
    output logic        tel_start,
    output logic [15:0] tel_start_per,
    output logic        tel_stop
);
    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] r;
        r = c ^ {24'h0, d};
        for (int b = 0; b < 8; b++) r = r[0] ? ((r >> 1) ^ 32'hEDB88320) : (r >> 1);
        return r;
    endfunction

    typedef enum logic [2:0] {S_IDLE, S_PRE, S_CRC, S_DECA, S_DECB, S_BUILD, S_APPLY} state_t;
    state_t state;

    logic [7:0]  pk   [0:15];
    logic [7:0]  rbuf [0:31];
    logic [8:0]  n;
    logic [15:0] cnt  [0:6];
    logic [15:0] refused;
    logic [31:0] scratch [0:2];
    logic        have_last;
    logic [15:0] last;
    logic [31:0] crc;
    logic [4:0]  ix;

    // decision flags
    logic f_crc_ok, f_type_ok, f_len_ok, f_seq_new, f_seq_rep, f_reg_ok;
    logic [2:0]  rc, st;
    logic        consume, ok;
    logic [4:0]  plen;
    logic [31:0] rval;

    logic [7:0]  typ, ln;
    logic [15:0] seq, dseq;
    logic [2:0]  regn;
    logic [7:0]  need;

    assign typ  = pk[0];
    assign ln   = pk[1];
    assign seq  = {pk[2], pk[3]};
    assign dseq = seq - last;
    assign regn = pk[5][2:0];

    always_comb begin
        case (typ)
            8'd1:    need = 8'd2;
            8'd2:    need = 8'd6;
            8'd4:    need = 8'd2;
            default: need = 8'd0;
        endcase
    end

    assign busy = (state != S_IDLE);
    assign cmds = cnt[0];
    assign refd = refused;

    // reply word read-out
    always_comb begin
        logic [8:0] bi;
        rword = 32'h0;
        for (int j = 0; j < 4; j++) begin
            bi = {ridx, 2'b00} + 9'(j);
            if (bi < {4'b0, rlen}) rword[31 - 8*j -: 8] = rbuf[bi[4:0]];
        end
    end

    // reply byte at index ix
    logic [7:0]  rbyte;
    logic [4:0]  pidx;
    logic [1:0]  jt;
    logic [15:0] cw;
    always_comb begin
        pidx = ix - 5'd5;
        jt   = 2'(ix - 5'd5 - plen);
        cw   = 16'h0;
        if (pidx[4:1] < 4'd7) cw = cnt[pidx[3:1]];
        rbyte = 8'h00;
        case (ix)
            5'd0: rbyte = typ | 8'h80;
            5'd1: rbyte = {5'b0, st};
            5'd2: rbyte = pk[2];
            5'd3: rbyte = pk[3];
            5'd4: rbyte = {3'b0, plen};
            default: begin
                if (ix < 5'd5 + plen) begin
                    if (typ == 8'd1) begin
                        case (pidx[1:0])
                            2'd0: rbyte = rval[31:24];
                            2'd1: rbyte = rval[23:16];
                            2'd2: rbyte = rval[15:8];
                            default: rbyte = rval[7:0];
                        endcase
                    end else begin
                        if (pidx < 5'd14)       rbyte = pidx[0] ? cw[7:0] : cw[15:8];
                        else if (pidx == 5'd14) rbyte = tel_fcount[15:8];
                        else if (pidx == 5'd15) rbyte = tel_fcount[7:0];
                        else                    rbyte = {7'b0, tel_on};
                    end
                end else begin
                    case (jt)
                        2'd0: rbyte = ~crc[7:0];
                        2'd1: rbyte = ~crc[15:8];
                        2'd2: rbyte = ~crc[23:16];
                        default: rbyte = ~crc[31:24];
                    endcase
                end
            end
        endcase
    end

    // register read value for a read command
    logic [31:0] rdv;
    always_comb begin
        case (regn)
            3'd0: rdv = ID_WORD;
            3'd1: rdv = scratch[0];
            3'd2: rdv = scratch[1];
            3'd3: rdv = scratch[2];
            3'd4: rdv = {16'h0, cnt[0]};
            3'd5: rdv = {16'h0, refused};
            3'd6: rdv = {16'h0, tel_period};
            default: rdv = tel_ticks;
        endcase
    end

    always_ff @(posedge clk) begin
        tel_start <= 1'b0;
        tel_stop  <= 1'b0;
        if (rst) begin
            state     <= S_IDLE;
            n         <= 9'd0;
            rlen      <= 5'd0;
            refused   <= 16'd0;
            have_last <= 1'b0;
            last      <= 16'd0;
            for (int i = 0; i < 7; i++) cnt[i] <= 16'd0;
            for (int i = 0; i < 3; i++) scratch[i] <= 32'd0;
            tel_start_per <= 16'd0;
        end else begin
            case (state)
            S_IDLE: begin
                if (in_wr) begin
                    if (n < 9'd16) pk[n[3:0]] <= in_data[7:0];
                    if (n != 9'd511) n <= n + 9'd1;
                    if (in_data[8]) state <= S_PRE;
                end
            end
            S_PRE: begin
                rlen    <= 5'd0;
                crc     <= 32'hFFFFFFFF;
                ix      <= 5'd0;
                consume <= 1'b0;
                ok      <= 1'b0;
                plen    <= 5'd0;
                if (n < 9'd4) begin
                    rc <= 3'd2; state <= S_APPLY;
                end else if (ln > 8'd8 || n > ({1'b0, ln} + 9'd8)) begin
                    rc <= 3'd3; state <= S_APPLY;
                end else if (n < ({1'b0, ln} + 9'd8)) begin
                    rc <= 3'd2; state <= S_APPLY;
                end else begin
                    state <= S_CRC;
                end
            end
            S_CRC: begin
                crc <= crc8(crc, pk[ix[3:0]]);
                ix  <= ix + 5'd1;
                if ({4'b0, ix} + 9'd1 == n) state <= S_DECA;
            end
            S_DECA: begin
                f_crc_ok   <= (crc == 32'hDEBB20E3);
                f_type_ok  <= (typ >= 8'd1) && (typ <= 8'd5);
                f_len_ok   <= (ln == need);
                f_seq_new  <= !have_last || ((dseq != 16'd0) && !dseq[15]);
                f_seq_rep  <= have_last && (dseq == 16'd0);
                f_reg_ok   <= (pk[4] == 8'd0) && (pk[5] < 8'd8);
                state      <= S_DECB;
            end
            S_DECB: begin
                rc      <= 3'd0;
                st      <= 3'd0;
                consume <= 1'b0;
                ok      <= 1'b0;
                plen    <= 5'd0;
                rval    <= rdv;
                state   <= S_BUILD;
                if (!f_crc_ok) begin
                    rc <= 3'd1; state <= S_APPLY;
                end else if (!f_type_ok) begin
                    rc <= 3'd6; st <= 3'd1;
                end else if (!f_len_ok) begin
                    rc <= 3'd6; st <= 3'd2;
                end else if (!f_seq_new) begin
                    rc <= f_seq_rep ? 3'd4 : 3'd5; st <= 3'd4;
                end else begin
                    consume <= 1'b1;
                    if (typ == 8'd1 || typ == 8'd2) begin
                        if (!f_reg_ok) begin
                            rc <= 3'd6; st <= 3'd3;
                        end else if (typ == 8'd2 && (regn == 3'd0 || regn >= 3'd4)) begin
                            rc <= 3'd6; st <= 3'd5;
                        end else begin
                            ok <= 1'b1;
                            if (typ == 8'd1) plen <= 5'd4;
                        end
                    end else begin
                        ok <= 1'b1;
                        if (typ == 8'd3) plen <= 5'd17;
                    end
                end
                crc <= 32'hFFFFFFFF;
                ix  <= 5'd0;
            end
            S_BUILD: begin
                rbuf[ix] <= rbyte;
                if (ix < 5'd5 + plen) crc <= crc8(crc, rbyte);
                ix <= ix + 5'd1;
                if (ix == 5'd8 + plen) begin
                    rlen  <= 5'd9 + plen;
                    state <= S_APPLY;
                end
            end
            S_APPLY: begin
                if (rc != 3'd0) begin
                    cnt[rc] <= cnt[rc] + 16'd1;
                    refused <= refused + 16'd1;
                end
                if (consume) begin
                    have_last <= 1'b1;
                    last      <= seq;
                end
                if (ok) begin
                    cnt[0] <= cnt[0] + 16'd1;
                    case (typ)
                        8'd2: scratch[regn[1:0] - 2'd1] <= {pk[6], pk[7], pk[8], pk[9]};
                        8'd4: begin
                            tel_start     <= 1'b1;
                            tel_start_per <= {pk[4], pk[5]};
                        end
                        8'd5: tel_stop <= 1'b1;
                        default: ;
                    endcase
                end
                n     <= 9'd0;
                state <= S_IDLE;
            end
            default: state <= S_IDLE;
            endcase
        end
    end
endmodule
