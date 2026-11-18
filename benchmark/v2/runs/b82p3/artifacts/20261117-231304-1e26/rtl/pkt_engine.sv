// pkt_engine.sv: packet parser (length, CRC-32, type, sequence, register rules), registers
// R0..R7, status counters and the reply builder. One byte per window write; the packet is
// processed after the end-flag byte, the reply is readable a few tens of clocks later.
module pkt_engine #(
    parameter logic [31:0] ID_WORD    = 32'h55445031,
    parameter logic [31:0] CRC_POLY   = 32'hEDB88320,
    parameter logic [31:0] CRC_INIT   = 32'hFFFFFFFF
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        in_wr,
    input  logic [8:0]  in_data,
    output logic        busy,
    // reply read-out
    input  logic [6:0]  ridx,
    output logic [5:0]  rlen,
    output logic [31:0] rword,
    // telemetry side
    input  logic [31:0] uptime,
    input  logic [15:0] period,
    input  logic        tel_on,
    input  logic [15:0] fcount,
    output logic        tstart,
    output logic [15:0] tstart_period,
    output logic        tstop,
    output logic [31:0] cmds,
    output logic [31:0] refused
);
    typedef enum logic [2:0] {S_IDLE, S_START, S_CRC, S_CMP, S_EXEC, S_RCRC, S_RFIN} state_t;
    state_t state;

    logic [7:0]  pb [0:15];     // packet bytes
    logic [4:0]  n;             // bytes received (saturating at 31)
    logic [5:0]  i;
    logic [31:0] crc;
    logic [7:0]  rb [0:31];     // reply bytes
    logic [5:0]  rtot;          // reply bytes before the CRC
    logic [15:0] last;
    logic        last_v;
    logic [31:0] sreg1, sreg2, sreg3;    // R1..R3
    logic [15:0] c_bad, c_short, c_long, c_rep, c_ooo, c_err;

    // ---------------------------------------------------------------- shared CRC engine
    logic [7:0]  crc_data;
    logic [31:0] crc_nxt;
    assign crc_data = (state == S_CRC) ? pb[i[3:0]] : rb[i[4:0]];
    crc32_byte #(.POLY(CRC_POLY)) u_crc (.crc_in(crc), .data(crc_data), .crc_out(crc_nxt));

    // ---------------------------------------------------------------- start-of-processing decisions
    wire [7:0] typ = pb[0];
    wire [7:0] ln  = pb[1];
    wire [8:0] full_len = 9'd8 + {1'b0, ln};
    wire       st_short0 = (n < 5'd4);
    wire       st_long   = !st_short0 && ((ln > 8'd8) || ({4'b0, n} > full_len));
    wire       st_short1 = !st_short0 && !st_long && ({4'b0, n} < full_len);
    wire [4:0] bl        = 5'd4 + ln[4:0];     // body length (valid when ln <= 8)

    // ---------------------------------------------------------------- CRC compare
    wire [3:0]  bi = bl[3:0];
    wire [31:0] rx_crc = {pb[bi + 4'd3], pb[bi + 4'd2], pb[bi + 4'd1], pb[bi]};
    wire        crc_ok = (~crc == rx_crc);

    // ---------------------------------------------------------------- execute decisions
    wire [15:0] seq   = {pb[2], pb[3]};
    wire [15:0] dseq  = seq - last;
    wire        seq_ok = !last_v || ((dseq != 16'd0) && !dseq[15]);
    wire        typ_ok = (typ >= 8'd1) && (typ <= 8'd5);
    logic [7:0] need;
    always_comb begin
        case (typ)
            8'd1:    need = 8'd2;
            8'd2:    need = 8'd6;
            8'd4:    need = 8'd2;
            default: need = 8'd0;
        endcase
    end
    wire        len_ok = (ln == need);
    wire [15:0] rnum   = {pb[4], pb[5]};
    wire        has_reg = (typ == 8'd1) || (typ == 8'd2);
    wire        reg_ok  = (rnum < 16'd8);
    wire        wr_ok   = (rnum[15:2] == 14'd0) && (rnum[1:0] != 2'd0);

    logic [31:0] rval;
    always_comb begin
        case (rnum[2:0])
            3'd0:    rval = ID_WORD;
            3'd1:    rval = sreg1;
            3'd2:    rval = sreg2;
            3'd3:    rval = sreg3;
            3'd4:    rval = cmds;
            3'd5:    rval = refused;
            3'd6:    rval = {16'd0, period};
            default: rval = uptime;
        endcase
    end

    logic [7:0] x_status;
    logic       x_err, x_rep, x_ooo, x_ok, x_consume;
    always_comb begin
        x_status  = 8'd0;
        x_err     = 1'b0;
        x_rep     = 1'b0;
        x_ooo     = 1'b0;
        x_ok      = 1'b0;
        x_consume = 1'b0;
        if (!typ_ok) begin
            x_status = 8'd1; x_err = 1'b1;
        end else if (!len_ok) begin
            x_status = 8'd2; x_err = 1'b1;
        end else if (!seq_ok) begin
            x_status = 8'd4;
            x_rep = (dseq == 16'd0);
            x_ooo = (dseq != 16'd0);
        end else begin
            x_consume = 1'b1;
            if (has_reg && !reg_ok) begin
                x_status = 8'd3; x_err = 1'b1;
            end else if ((typ == 8'd2) && !wr_ok) begin
                x_status = 8'd5; x_err = 1'b1;
            end else begin
                x_ok = 1'b1;
            end
        end
    end

    assign tstart        = (state == S_EXEC) && x_ok && (typ == 8'd4);
    assign tstart_period = {pb[4], pb[5]};
    assign tstop         = (state == S_EXEC) && x_ok && (typ == 8'd5);
    assign busy          = (state != S_IDLE);

    // ---------------------------------------------------------------- control
    logic refuse_pulse;
    always_comb begin
        refuse_pulse = 1'b0;
        case (state)
            S_START: refuse_pulse = st_short0 || st_long || st_short1;
            S_CMP:   refuse_pulse = !crc_ok;
            S_EXEC:  refuse_pulse = !x_ok;
            default: ;
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state   <= S_IDLE;
            n       <= 5'd0;
            last_v  <= 1'b0;
            cmds    <= 32'd0;
            refused <= 32'd0;
            c_bad   <= 16'd0;
            c_short <= 16'd0;
            c_long  <= 16'd0;
            c_rep   <= 16'd0;
            c_ooo   <= 16'd0;
            c_err   <= 16'd0;
            rlen    <= 6'd0;
            sreg1   <= 32'd0;
            sreg2   <= 32'd0;
            sreg3   <= 32'd0;
        end else begin
            if (refuse_pulse) refused <= refused + 32'd1;
            case (state)
                S_IDLE: begin
                    if (in_wr) begin
                        if (n != 5'd31) n <= n + 5'd1;
                        if (in_data[8]) state <= S_START;
                    end
                end
                S_START: begin
                    rlen <= 6'd0;
                    n    <= 5'd0;
                    if (st_short0 || st_short1) begin
                        c_short <= c_short + 16'd1;
                        state   <= S_IDLE;
                    end else if (st_long) begin
                        c_long <= c_long + 16'd1;
                        state  <= S_IDLE;
                    end else begin
                        state <= S_CRC;
                    end
                end
                S_CRC: begin
                    if ((i + 6'd1) == {1'b0, bl}) state <= S_CMP;
                end
                S_CMP: begin
                    if (crc_ok) state <= S_EXEC;
                    else begin
                        c_bad <= c_bad + 16'd1;
                        state <= S_IDLE;
                    end
                end
                S_EXEC: begin
                    state <= S_RCRC;
                    if (x_consume) last_v <= 1'b1;
                    if (x_ok) cmds <= cmds + 32'd1;
                    if (x_err) c_err <= c_err + 16'd1;
                    if (x_rep) c_rep <= c_rep + 16'd1;
                    if (x_ooo) c_ooo <= c_ooo + 16'd1;
                    if (x_ok && (typ == 8'd2)) begin
                        case (rnum[1:0])
                            2'd1:    sreg1 <= {pb[6], pb[7], pb[8], pb[9]};
                            2'd2:    sreg2 <= {pb[6], pb[7], pb[8], pb[9]};
                            default: sreg3 <= {pb[6], pb[7], pb[8], pb[9]};
                        endcase
                    end
                end
                S_RCRC: begin
                    if ((i + 6'd1) == rtot) state <= S_RFIN;
                end
                S_RFIN: begin
                    rlen  <= rtot + 6'd4;
                    state <= S_IDLE;
                end
                default: state <= S_IDLE;
            endcase
        end
    end

    // ---------------------------------------------------------------- datapath, no reset
    always_ff @(posedge clk) begin
        if (state == S_IDLE) begin
            if (in_wr && (n < 5'd16)) pb[n[3:0]] <= in_data[7:0];
        end
        case (state)
            S_START: begin
                crc <= CRC_INIT;
                i   <= 6'd0;
            end
            S_CRC: begin
                crc <= crc_nxt;
                i   <= i + 6'd1;
            end
            S_EXEC: begin
                crc  <= CRC_INIT;
                i    <= 6'd0;
                if (x_consume) last <= seq;
                rb[0] <= typ | 8'h80;
                rb[1] <= x_status;
                rb[2] <= pb[2];
                rb[3] <= pb[3];
                rb[4] <= 8'd0;
                rtot  <= 6'd5;
                if (x_ok && (typ == 8'd1)) begin
                    rb[4] <= 8'd4;
                    rtot  <= 6'd9;
                    {rb[5], rb[6], rb[7], rb[8]} <= rval;
                end
                if (x_ok && (typ == 8'd3)) begin
                    rb[4] <= 8'd17;
                    rtot  <= 6'd22;
                    {rb[5], rb[6]}   <= cmds[15:0];
                    {rb[7], rb[8]}   <= c_bad;
                    {rb[9], rb[10]}  <= c_short;
                    {rb[11], rb[12]} <= c_long;
                    {rb[13], rb[14]} <= c_rep;
                    {rb[15], rb[16]} <= c_ooo;
                    {rb[17], rb[18]} <= c_err;
                    {rb[19], rb[20]} <= fcount;
                    rb[21] <= {7'd0, tel_on};
                end
            end
            S_RCRC: begin
                crc <= crc_nxt;
                i   <= i + 6'd1;
            end
            S_RFIN: begin
                rb[rtot[4:0]]        <= ~crc[7:0];
                rb[rtot[4:0] + 5'd1] <= ~crc[15:8];
                rb[rtot[4:0] + 5'd2] <= ~crc[23:16];
                rb[rtot[4:0] + 5'd3] <= ~crc[31:24];
            end
            default: ;
        endcase
    end

    // ---------------------------------------------------------------- reply words
    always_comb begin
        logic [8:0] j;
        logic [7:0] bv [0:3];
        for (int k = 0; k < 4; k++) begin
            j = {ridx, 2'b00} + 9'(k);
            bv[k] = (j < {3'b0, rlen}) ? rb[j[4:0]] : 8'h00;
        end
        rword = {bv[0], bv[1], bv[2], bv[3]};
    end
endmodule
