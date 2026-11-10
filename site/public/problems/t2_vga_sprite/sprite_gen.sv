// sprite_gen.sv: 640x480 at 60 Hz raster (800 x 525, negative syncs) on a
// pixel enable every 4th clock, one 16x16 1-bit sprite over a background.
module sprite_gen (
    input  logic            clk,
    input  logic            rst,
    input  logic [255:0]    rows,        // row r = rows[16*r +: 16], bit 15 of a row = leftmost pixel
    input  logic [9:0]      sx,
    input  logic [9:0]      sy,
    input  logic            en,
    input  logic [11:0]     sprite_color,
    input  logic [11:0]     bg_color,
    output logic            frame_tick,  // one clock at the wrap to (0, 0)
    output logic [11:0]     rgb,
    output logic            hs_n,
    output logic            vs_n
);
    localparam int HV = 640, HFP = 16, HSW = 96, HT = 800;
    localparam int VV = 480, VFP = 10, VSW = 2, VT = 525;

    logic [1:0]  ph;
    logic [9:0]  x, y;
    logic [10:0] dx, dy;           // x - X, y - Y (11 bits: negative = outside)
    logic        hit;
    logic [11:0] pix;
    logic [3:0]  c, r;
    logic [15:0] row;

    always_comb begin
        dx  = {1'b0, x} - {1'b0, sx};
        dy  = {1'b0, y} - {1'b0, sy};
        c   = dx[3:0];
        r   = dy[3:0];
        row = rows[16 * r +: 16];
        hit = en && dx < 11'd16 && dy < 11'd16 && row[4'd15 - c];
        if (x >= 10'(HV) || y >= 10'(VV)) pix = 12'h000;
        else if (hit)                     pix = sprite_color;
        else                              pix = bg_color;
    end

    always_ff @(posedge clk) begin
        frame_tick <= 1'b0;
        if (rst) begin
            ph <= '0; x <= '0; y <= '0; rgb <= '0; hs_n <= 1'b1; vs_n <= 1'b1;
        end else begin
            ph <= ph + 1'b1;
            if (ph == 2'd3) begin
                rgb  <= pix;
                hs_n <= !(x >= 10'(HV + HFP) && x < 10'(HV + HFP + HSW));
                vs_n <= !(y >= 10'(VV + VFP) && y < 10'(VV + VFP + VSW));
                if (x == 10'(HT - 1)) begin
                    x <= '0;
                    if (y == 10'(VT - 1)) begin
                        y <= '0;
                        frame_tick <= 1'b1;
                    end else begin
                        y <= y + 1'b1;
                    end
                end else begin
                    x <= x + 1'b1;
                end
            end
        end
    end
endmodule
