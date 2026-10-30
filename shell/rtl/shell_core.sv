// shell_core.sv: the test shell's frame parser and register file.
// The protocol is in shell/PROTOCOL.md. In short: every request is 8 bytes,
//   0xA5, CMD, ADDR, D0, D1, D2, D3, CHK     (CHK = XOR of CMD..D3, D0 = bits 7:0)
// and every response is 7 bytes,
//   0x5A, STATUS, D0, D1, D2, D3, CHK        (CHK = XOR of STATUS..D3).
// Bytes are ignored until a 0xA5 is seen; a frame that stops for longer than
// TIMEOUT_CYCLES is dropped without a response; bytes that arrive while a
// response is being sent are dropped.

module shell_core #(
    parameter int          TIMEOUT_CYCLES = 100_000,   // 1 ms at 100 MHz
    parameter logic [31:0] DESIGN_ID      = 32'h0,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic        clk,
    input  logic        rst,
    // from uart_rx
    input  logic        rx_valid,
    input  logic [7:0]  rx_data,
    input  logic        rx_frame_err,
    // to uart_tx
    output logic        tx_start,
    output logic [7:0]  tx_data,
    input  logic        tx_busy,
    // register window, addresses 0x80-0xFF; read data is due one cycle after win_rd
    output logic [6:0]  win_addr,
    output logic        win_wr,
    output logic        win_rd,
    output logic [31:0] win_wdata,
    input  logic [31:0] win_rdata
);
    localparam logic [7:0] SYNC_REQ  = 8'hA5;
    localparam logic [7:0] SYNC_RESP = 8'h5A;
    localparam logic [7:0] CMD_READ  = 8'h01;
    localparam logic [7:0] CMD_WRITE = 8'h02;
    localparam logic [7:0] ST_OK        = 8'h00;
    localparam logic [7:0] ST_BAD_CHK   = 8'h01;
    localparam logic [7:0] ST_BAD_CMD   = 8'h02;
    localparam logic [7:0] ST_BAD_ADDR  = 8'h03;
    localparam logic [7:0] ST_READ_ONLY = 8'h04;
    localparam logic [31:0] SHELL_VERSION = 32'h0001_0000;   // 1.0
    localparam int TW = $clog2(TIMEOUT_CYCLES + 1);

    typedef enum logic [2:0] {S_HUNT, S_RECV, S_EXEC, S_WIN_WAIT, S_WIN_CAP, S_SEND, S_SEND_WAIT} state_t;
    state_t state;

    logic [7:0]    frame [7];     // CMD, ADDR, D0..D3, CHK
    logic [2:0]    idx;
    logic [TW-1:0] tcount;
    logic [7:0]    resp [7];
    logic [2:0]    ridx;

    logic [31:0] scratch;
    logic [7:0]  cnt_chk, cnt_req, cnt_frame, cnt_timeout;   // saturating error counters

    wire [7:0]  cmd   = frame[0];
    wire [7:0]  addr  = frame[1];
    wire [31:0] wdata = {frame[5], frame[4], frame[3], frame[2]};
    wire [7:0]  chk_calc = frame[0] ^ frame[1] ^ frame[2] ^ frame[3] ^ frame[4] ^ frame[5];
    wire [31:0] status_reg = {cnt_timeout, cnt_frame, cnt_req, cnt_chk};

    function automatic logic [7:0] sat_inc(input logic [7:0] v);
        return (v == 8'hFF) ? v : v + 8'd1;
    endfunction

    task automatic respond(input logic [7:0] st, input logic [31:0] d);
        resp[0] <= SYNC_RESP;
        resp[1] <= st;
        resp[2] <= d[7:0];
        resp[3] <= d[15:8];
        resp[4] <= d[23:16];
        resp[5] <= d[31:24];
        resp[6] <= st ^ d[7:0] ^ d[15:8] ^ d[23:16] ^ d[31:24];
    endtask

    assign win_addr  = addr[6:0];
    assign win_wdata = wdata;
    assign tx_data   = resp[ridx];

    always_ff @(posedge clk) begin
        win_wr   <= 1'b0;
        win_rd   <= 1'b0;
        tx_start <= 1'b0;
        if (rst) begin
            state       <= S_HUNT;
            idx         <= '0;
            ridx        <= '0;
            tcount      <= '0;
            scratch     <= '0;
            cnt_chk     <= '0;
            cnt_req     <= '0;
            cnt_frame   <= '0;
            cnt_timeout <= '0;
            for (int i = 0; i < 7; i++) begin
                frame[i] <= '0;
                resp[i]  <= '0;
            end
        end else begin
            if (rx_frame_err) cnt_frame <= sat_inc(cnt_frame);
            case (state)
                S_HUNT: begin
                    idx    <= '0;
                    tcount <= '0;
                    if (rx_valid && rx_data == SYNC_REQ) state <= S_RECV;
                end
                S_RECV: begin
                    if (rx_frame_err) begin
                        state <= S_HUNT;                 // the frame lost a byte
                    end else if (rx_valid) begin
                        frame[idx] <= rx_data;
                        tcount     <= '0;
                        if (idx == 3'd6) state <= S_EXEC;
                        idx <= idx + 1'b1;
                    end else if (tcount == TW'(TIMEOUT_CYCLES - 1)) begin
                        cnt_timeout <= sat_inc(cnt_timeout);
                        state       <= S_HUNT;
                    end else begin
                        tcount <= tcount + 1'b1;
                    end
                end
                S_EXEC: begin
                    state <= S_SEND;
                    ridx  <= '0;
                    if (chk_calc != frame[6]) begin
                        cnt_chk <= sat_inc(cnt_chk);
                        respond(ST_BAD_CHK, 32'h0);
                    end else if (cmd != CMD_READ && cmd != CMD_WRITE) begin
                        cnt_req <= sat_inc(cnt_req);
                        respond(ST_BAD_CMD, 32'h0);
                    end else if (addr[7]) begin           // the design's window
                        if (cmd == CMD_WRITE) begin
                            win_wr <= 1'b1;
                            respond(ST_OK, wdata);
                        end else begin
                            win_rd <= 1'b1;
                            state  <= S_WIN_WAIT;
                        end
                    end else begin
                        case (addr)
                            8'h00: if (cmd == CMD_READ) respond(ST_OK, DESIGN_ID);
                                   else begin cnt_req <= sat_inc(cnt_req); respond(ST_READ_ONLY, 32'h0); end
                            8'h01: if (cmd == CMD_READ) respond(ST_OK, SHELL_VERSION);
                                   else begin cnt_req <= sat_inc(cnt_req); respond(ST_READ_ONLY, 32'h0); end
                            8'h02: if (cmd == CMD_READ) respond(ST_OK, BUILD_STAMP);
                                   else begin cnt_req <= sat_inc(cnt_req); respond(ST_READ_ONLY, 32'h0); end
                            8'h03: if (cmd == CMD_READ) respond(ST_OK, scratch);
                                   else begin scratch <= wdata; respond(ST_OK, wdata); end
                            8'h04: if (cmd == CMD_READ) respond(ST_OK, status_reg);
                                   else begin                 // any write clears the counters
                                       cnt_chk     <= '0;
                                       cnt_req     <= '0;
                                       cnt_frame   <= '0;
                                       cnt_timeout <= '0;
                                       respond(ST_OK, 32'h0);
                                   end
                            default: begin
                                cnt_req <= sat_inc(cnt_req);
                                respond(ST_BAD_ADDR, 32'h0);
                            end
                        endcase
                    end
                end
                S_WIN_WAIT: state <= S_WIN_CAP;           // the design registers its read data
                S_WIN_CAP: begin
                    respond(ST_OK, win_rdata);
                    state <= S_SEND;
                end
                S_SEND: begin
                    if (!tx_busy) begin
                        tx_start <= 1'b1;
                        state    <= S_SEND_WAIT;
                    end
                end
                S_SEND_WAIT: begin
                    // busy rises the cycle after tx_start, so wait one cycle before trusting it
                    if (!tx_start && !tx_busy) begin
                        if (ridx == 3'd6) begin
                            state <= S_HUNT;
                        end else begin
                            ridx  <= ridx + 1'b1;
                            state <= S_SEND;
                        end
                    end
                end
                default: state <= S_HUNT;
            endcase
        end
    end
endmodule
