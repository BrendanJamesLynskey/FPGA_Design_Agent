// Window/pattern storage, 32-clock burst sequencer, result slots, count and record.
module c9_sequencer (
    input  logic        clk,
    input  logic        rst,            // synchronous, active high
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic        med_valid_in,
    output logic [71:0] med_pix,
    input  logic        med_valid_out,
    input  logic [7:0]  med_median
);
    logic [23:0] regs [24];
    logic [31:0] mask, vmask;
    logic [5:0]  cnt;
    logic        running, done;
    logic [3:0]  nwin;                  // windows presented so far (0..8)
    logic [3:0]  nout;                  // results seen (0..8)
    logic [7:0]  meds [8];

    wire go = win_wr && (win_addr == 7'h01);

    // window presented in this clock
    wire present = running && (cnt < 6'd32) && mask[cnt[4:0]] && !nwin[3];

    always_comb begin
        med_pix = 72'd0;
        for (int k = 0; k < 8; k++)
            if (nwin[2:0] == 3'(k)) med_pix = {regs[3*k+2], regs[3*k+1], regs[3*k]};
    end
    assign med_valid_in = present;

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < 24; i++) regs[i] <= 24'd0;
            for (int i = 0; i < 8; i++)  meds[i] <= 8'd0;
            mask    <= 32'd0;
            vmask   <= 32'd0;
            cnt     <= 6'd0;
            running <= 1'b0;
            done    <= 1'b0;
            nwin    <= 4'd0;
            nout    <= 4'd0;
        end else begin
            if (win_wr) begin
                if (win_addr == 7'h00) mask <= win_wdata;
                for (int i = 0; i < 24; i++)
                    if (win_addr == 7'(7'h10 + i)) regs[i] <= win_wdata[23:0];
            end

            if (go) begin
                vmask   <= 32'd0;
                nout    <= 4'd0;
                nwin    <= 4'd0;
                done    <= 1'b0;
                running <= 1'b1;
                cnt     <= 6'd0;
                for (int i = 0; i < 8; i++) meds[i] <= 8'd0;
            end else begin
                if (running) begin
                    cnt <= cnt + 6'd1;
                    if (cnt == 6'd32) begin
                        running <= 1'b0;
                        done    <= 1'b1;
                    end
                end
                if (present) nwin <= nwin + 4'd1;
                if (med_valid_out && running) begin
                    // result for the window presented in the previous clock (cnt-1)
                    if (!nout[3]) begin
                        for (int i = 0; i < 8; i++)
                            if (nout[2:0] == 3'(i)) meds[i] <= med_median;
                        nout <= nout + 4'd1;
                    end
                    vmask[cnt[4:0] - 5'd1] <= 1'b1;
                end
            end
        end
    end

    // registered read, data valid the cycle after win_rd
    always_ff @(posedge clk) begin
        if (rst) win_rdata <= 32'd0;
        else if (win_rd) begin
            win_rdata <= 32'd0;
            if (win_addr == 7'h00)      win_rdata <= mask;
            else if (win_addr == 7'h02) win_rdata <= {31'd0, done};
            else if (win_addr == 7'h03) win_rdata <= {28'd0, nout};
            else if (win_addr == 7'h04) win_rdata <= vmask;
            else begin
                for (int i = 0; i < 24; i++)
                    if (win_addr == 7'(7'h10 + i)) win_rdata <= {8'd0, regs[i]};
                for (int i = 0; i < 8; i++)
                    if (win_addr == 7'(7'h30 + i)) win_rdata <= {24'd0, meds[i]};
            end
        end
    end
endmodule
