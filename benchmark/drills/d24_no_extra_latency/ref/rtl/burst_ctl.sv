// burst_ctl.sv: the burst sequencer of drill d24_no_extra_latency (brief 24). One clock. IDLE LOAD REQ ADDR DATA TURN WACK RETRY RESP ERR COOL.
module burst_ctl (
    input  logic        clk,
    input  logic        rst,
    input  logic        cmd_valid, gnt, ack, nack, rsp_ready,
    output logic        o_req, o_addr_v, o_valid, o_last, o_rsp_valid, o_rsp_err, o_cmd_ready, o_cmd_ack,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    typedef enum logic [3:0] {IDLE, LOAD, REQ, ADDR, DATA, TURN, WACK, RETRY, RESP, ERR, COOL} st_t;
    st_t st, nx;
    logic [3:0] cnt;
    wire zero = (cnt == 4'd0);
    logic [15:0] bursts, errs;
    wire clear = win_wr && win_addr == 7'h02;

    always_comb begin
        nx = st;
        case (st)
            IDLE:  if (cmd_valid) nx = LOAD;
            LOAD:  nx = REQ;
            REQ:   if (gnt) nx = ADDR;
            ADDR:  nx = DATA;
            DATA:  if (zero) nx = TURN;
            TURN:  nx = WACK;
            WACK:  if (ack) nx = RESP; else if (nack) nx = RETRY; else if (zero) nx = ERR;
            RETRY: nx = REQ;
            RESP:  if (rsp_ready) nx = COOL;
            ERR:   if (rsp_ready) nx = COOL;
            COOL:  if (zero) nx = IDLE;
            default: nx = IDLE;
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            st <= IDLE; cnt <= '0;
        end else begin
            st <= nx;
            if (st == ADDR) cnt <= 4'd3;
            else if (st == TURN) cnt <= 4'd7;
            else if ((st == RESP || st == ERR) && rsp_ready) cnt <= 4'd2;
            else if (st == DATA || st == WACK || st == COOL) cnt <= cnt - 4'd1;
        end
    end

    always_ff @(posedge clk) begin
        if (rst || clear) begin bursts <= '0; errs <= '0; end
        else begin
            if (st == RESP && rsp_ready) bursts <= bursts + 16'd1;
            if (st == ERR && rsp_ready) errs <= errs + 16'd1;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= 32'(bursts);
                7'h01:   win_rdata <= 32'(errs);
                default: win_rdata <= '0;
            endcase
        end
    end

    // combinational Moore decode of the state; cmd_ack is Mealy (state and cmd_valid): no added latency anywhere
    assign o_req       = (st == REQ || st == ADDR || st == DATA);
    assign o_addr_v    = (st == ADDR);
    assign o_valid     = (st == DATA);
    assign o_last      = (st == DATA) && zero;
    assign o_rsp_valid = (st == RESP || st == ERR);
    assign o_rsp_err   = (st == ERR);
    assign o_cmd_ready = (st == IDLE);
    assign o_cmd_ack   = (st == IDLE) && cmd_valid;
endmodule
