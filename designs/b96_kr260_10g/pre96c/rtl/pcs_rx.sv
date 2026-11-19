// pcs_rx.sv: 10GBASE-R receive PCS on a 64-bit RAW GT word (brief 96): 64-to-66 gearbox with bit slip, block lock, descramble, decode.
//
// Registers on the path (clocks counted from the edge that captures the GT word that holds a block's last bit):
//   stage A  acc/cnt (the gearbox remainder) and blk (the extracted 66-bit block)          edge +0
//   stage B  x_d/x_c/x_v (descrambled, decoded block; valid only while block lock is held)  edge +1
// Block lock (clause 49, Figure 49-14 from memory, designs/b96_kr260_10g/docs/design.md section 2.8): hunting needs 64 valid sync
// headers in a row; a bad header while hunting, or 16 bad headers inside 64 while locked, slips one bit and drops the lock. The slip is
// a register (slip_r): it takes effect on the next incoming word and the FSM ignores the one block formed before that (settle).
module pcs_rx (
    input  logic        clk,
    input  logic        rst,        // hold while the GT's receive side is not up (rx_done low)
    input  logic [63:0] gt_d,       // RXDATA
    output logic        x_v,        // a decoded block, with block lock held
    output logic [63:0] x_d,
    output logic [7:0]  x_c,
    output logic        lock,
    output logic        ev_sh_err,  // pulses, one per event, for the counters
    output logic        ev_type_err,
    output logic        ev_os,
    output logic        ev_slip,
    output logic        ev_loss,
    output logic        ev_lock
);
    import b96_pkg::*;
    // stage A
    logic [135:0] acc;
    logic [7:0]   cnt;
    logic         slip_r;
    logic         blk_v;
    logic [65:0]  blk;
    logic [135:0] m0, m1;
    logic [7:0]   k0, k1;
    logic         ext;
    assign m0  = acc | ({72'd0, gt_d} << cnt);
    assign k0  = cnt + 8'd64;
    assign m1  = slip_r ? (m0 >> 1) : m0;
    assign k1  = slip_r ? (k0 - 8'd1) : k0;
    assign ext = (k1 >= 8'd66);
    always_ff @(posedge clk) begin
        if (rst) begin
            acc <= '0; cnt <= '0; blk_v <= 1'b0; blk <= '0;
        end else begin
            blk_v <= ext;
            blk   <= m1[65:0];
            if (ext) begin acc <= m1 >> 66; cnt <= k1 - 8'd66; end
            else     begin acc <= m1;       cnt <= k1; end
        end
    end
    // stage B and the block-lock FSM (both read the block registered by stage A)
    logic [57:0] hist;
    logic [63:0] pd;
    logic [73:0] dec;
    logic        valid_sh;
    logic [6:0]  sh_cnt;
    logic [4:0]  inv_cnt;
    logic        settle;
    assign pd       = desc_out(hist, blk[65:2]);
    assign dec      = dec66(blk[1:0], pd);
    assign valid_sh = (blk[1:0] == 2'b01) || (blk[1:0] == 2'b10);
    always_ff @(posedge clk) begin
        ev_sh_err <= 1'b0; ev_type_err <= 1'b0; ev_os <= 1'b0; ev_slip <= 1'b0; ev_loss <= 1'b0; ev_lock <= 1'b0;
        if (rst) begin
            hist <= '0; lock <= 1'b0; sh_cnt <= '0; inv_cnt <= '0; settle <= 1'b0; slip_r <= 1'b0;
            x_v <= 1'b0; x_d <= '0; x_c <= '0;
        end else begin
            slip_r <= 1'b0;
            x_v    <= 1'b0;
            if (blk_v) begin
                hist <= hist_next(blk[65:2]);
                x_d  <= dec[63:0];
                x_c  <= dec[71:64];
                if (lock) begin
                    x_v <= 1'b1;
                    ev_sh_err   <= (dec[73:72] == 2'd1);
                    ev_type_err <= (dec[73:72] == 2'd2);
                    ev_os       <= (dec[73:72] == 2'd3);
                end
                if (settle) begin
                    settle <= 1'b0;
                end else if (!valid_sh && (!lock || inv_cnt == 5'd15)) begin
                    ev_loss <= lock;
                    lock <= 1'b0; slip_r <= 1'b1; ev_slip <= 1'b1; settle <= 1'b1; sh_cnt <= '0; inv_cnt <= '0;
                end else if (sh_cnt == 7'd63) begin
                    if (!lock && inv_cnt == 5'd0) begin lock <= 1'b1; ev_lock <= 1'b1; end
                    sh_cnt <= '0; inv_cnt <= '0;
                end else begin
                    sh_cnt <= sh_cnt + 7'd1;
                    if (!valid_sh) inv_cnt <= inv_cnt + 5'd1;
                end
            end
        end
    end
endmodule
