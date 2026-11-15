// dc_block.sv: first-order DC blocker, pole 1 - 2^-7, floor shift, saturating, 4-entry newest-wins queue (v2_b_dc_block).
module dc_block (
    input  logic        clk_db,
    input  logic        rst_db,
    input  logic [6:0]  win_addr_db,
    input  logic        win_wr_db,
    input  logic        win_rd_db,
    input  logic [31:0] win_wdata_db,
    output logic [31:0] win_rdata_db
);
    logic signed [15:0] xp_db, yp_db;
    logic signed [15:0] q_db [4];
    logic [1:0]         rp_db, wp_db;
    logic [2:0]         cnt_db;
    logic               sat_db, lost_db;

    wire clr_db  = win_wr_db && win_addr_db == 7'h00 && win_wdata_db[0];
    wire smp_db  = win_wr_db && win_addr_db == 7'h01;
    wire pop_db  = win_wr_db && win_addr_db == 7'h04 && cnt_db != 3'd0;
    wire signed [15:0] x0_db = win_wdata_db[15:0];

    wire signed [31:0] w_db  = 32'(x0_db) - 32'(xp_db) + 32'(yp_db) - (32'(yp_db) >>> 7);
    wire               hi_db = w_db > 32'sd32767;
    wire               lo_db = w_db < -32'sd32768;
    wire signed [15:0] y_db  = hi_db ? 16'sh7FFF : lo_db ? 16'sh8000 : w_db[15:0];

    always_ff @(posedge clk_db) begin
        if (rst_db || clr_db) begin
            xp_db <= '0; yp_db <= '0; rp_db <= '0; wp_db <= '0; cnt_db <= '0; sat_db <= 1'b0; lost_db <= 1'b0;
        end else begin
            if (smp_db) begin
                xp_db <= x0_db;
                yp_db <= y_db;
                if (hi_db || lo_db) sat_db <= 1'b1;
                q_db[wp_db] <= y_db;
                wp_db <= wp_db + 2'd1;
                if (cnt_db == 3'd4) begin
                    rp_db   <= rp_db + 2'd1;
                    lost_db <= 1'b1;
                end else begin
                    cnt_db <= cnt_db + 3'd1;
                end
            end else if (pop_db) begin
                rp_db  <= rp_db + 2'd1;
                cnt_db <= cnt_db - 3'd1;
            end
        end
    end

    always_ff @(posedge clk_db) begin
        if (rst_db) win_rdata_db <= '0;
        else if (win_rd_db) begin
            case (win_addr_db)
                7'h02:   win_rdata_db <= {27'd0, lost_db, sat_db, cnt_db};
                7'h03:   win_rdata_db <= (cnt_db != 3'd0) ? 32'(q_db[rp_db]) : 32'd0;
                default: win_rdata_db <= '0;
            endcase
        end
    end
endmodule
