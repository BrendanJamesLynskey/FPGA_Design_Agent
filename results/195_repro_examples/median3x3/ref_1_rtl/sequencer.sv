// sequencer: window store, pattern, go, 32-clock run, medians, count and record, register decode.
module sequencer (
    input  logic        clk,
    input  logic        rst,          // synchronous, active high
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic        pix_valid,
    output logic [71:0] pix,
    input  logic [7:0]  med,
    input  logic        med_valid
);
    logic [23:0] store [0:23];
    logic [31:0] mask, record;
    logic [3:0]  nwin, nxt, nxt_n;
    logic [5:0]  t;
    logic [5:0]  count;
    logic        running, done;
    logic [7:0]  meds [0:7];

    wire go_wr   = win_wr && (win_addr == 7'h01);
    wire in_win  = (win_addr >= 7'h10) && (win_addr <= 7'h27);
    wire [4:0] widx = 5'(win_addr - 7'h10);
    wire [3:0] wk   = 4'(widx / 5'd3);

    wire present = running && !go_wr && (t < 6'd32) && mask[t[4:0]] && (nxt < nwin);
    assign pix_valid = present;

    always_comb begin
        nxt_n = nxt;
        if (go_wr)        nxt_n = 4'd0;
        else if (present) nxt_n = nxt + 4'd1;
    end

    // prefetch register: the window that will be presented next
    always_ff @(posedge clk) begin
        for (int p = 0; p < 9; p++)
            pix[8*p +: 8] <= (nxt_n < 4'd8) ? store[3*int'(nxt_n[2:0]) + p/3][8*(p%3) +: 8] : 8'd0;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < 24; i++) store[i] <= 24'd0;
            for (int i = 0; i < 8; i++)  meds[i]  <= 8'd0;
            mask    <= 32'd0;
            record  <= 32'd0;
            nwin    <= 4'd0;
            nxt     <= 4'd0;
            t       <= 6'd0;
            count   <= 6'd0;
            running <= 1'b0;
            done    <= 1'b0;
        end else begin
            nxt <= nxt_n;
            if (win_wr && win_addr == 7'h00) mask <= win_wdata;
            if (win_wr && in_win) begin
                store[widx[4:0]] <= win_wdata[23:0];
                if (nwin < wk + 4'd1) nwin <= wk + 4'd1;
            end
            if (go_wr) begin
                running <= 1'b1;
                t       <= 6'd0;
                done    <= 1'b0;
                count   <= 6'd0;
                record  <= 32'd0;
                for (int i = 0; i < 8; i++) meds[i] <= 8'd0;
            end else begin
                if (running) begin
                    t <= t + 6'd1;
                    if (present) record[t[4:0]] <= 1'b1;
                    if (t == 6'd32) begin
                        running <= 1'b0;
                        done    <= 1'b1;
                    end
                end
                if (med_valid) begin
                    count <= count + 6'd1;
                    if (count < 6'd8) meds[count[2:0]] <= med;
                end
            end
        end
    end

    // read: registered, valid the cycle after win_rd
    always_ff @(posedge clk) begin
        if (win_rd) begin
            win_rdata <= 32'd0;
            if (win_addr == 7'h00)      win_rdata <= mask;
            else if (win_addr == 7'h02) win_rdata <= {31'd0, done};
            else if (win_addr == 7'h03) win_rdata <= {26'd0, count};
            else if (win_addr == 7'h04) win_rdata <= record;
            else if (in_win)            win_rdata <= {8'd0, store[widx[4:0]]};
            else if (win_addr >= 7'h30 && win_addr <= 7'h37)
                win_rdata <= {24'd0, meds[win_addr[2:0]]};
        end
    end
endmodule
