// P13-1 reference glue (v1.1 scope): a picture goes in as a stream of 8-bit pixels (80 x 60) into a picture store; when the last pixel is in, a scan engine builds the
// 7 x 7 window of every pixel (edge pixels replicated), one column per clock, and hands it to the course's Harris response and non-maximum suppression (harris.sv).
// The picture is held in seven block-RAM copies (one per window row, each written together and read through a registered port), so Vivado infers block RAM
// instead of 38,400 flip-flops with seven read multiplexers each; the address is registered before the RAM, so a column arrives two clocks after its address (the drain states 5 and 6).
// Each corner is appended to a list (x, y); `count` counts all corners found (the list holds the first 64); `done` is high from the end of the scan until the next picture starts.
module harris_pic_ram #(
    parameter int N = 4800
) (
    input  logic        clk,
    input  logic        we,
    input  logic [12:0] waddr,
    input  logic [7:0]  wdata,
    input  logic [12:0] raddr,
    output logic [7:0]  rdata
);
    (* ram_style = "block" *) logic [7:0] mem [0:N-1];
    always_ff @(posedge clk) begin
        if (we) mem[waddr] <= wdata;
        rdata <= mem[raddr];
    end
endmodule

module harris_detect #(
    parameter int W = 80,
    parameter int H = 60
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [7:0]  s_tdata,
    input  logic        s_tvalid,
    output logic        s_tready,
    input  logic        s_tuser,
    input  logic        s_tlast,
    output logic        done,
    output logic [15:0] count,
    input  logic [5:0]  rd_idx,
    output logic [6:0]  rd_x,
    output logic [6:0]  rd_y
);
    localparam int N = W * H;
    logic [12:0] wn;                        // pixels stored
    logic [6:0]  px, py;                    // pixel being examined
    logic [2:0]  k;                         // window column being loaded
    logic [2:0]  st;                        // 0 idle/store, 1 fill, 2 fire, 3 wait, 4 collect
    logic [7:0]  wreg [0:6][0:6];
    logic [391:0] win;
    logic        in_valid, h_valid, h_corner;
    logic signed [47:0] h_resp;
    logic [6:0]  lx [0:63], ly [0:63];
    logic        cap_en, cap_en1;           // a column was addressed two clocks ago: its pixels are on q now
    logic [2:0]  kd, kd1;                   // the window column those pixels belong to
    logic [7:0]  q [0:6];                   // registered read of the seven picture copies
    logic [12:0] raddr [0:6], raddr_q [0:6];
    wire         pic_we = (st == 3'd0) && s_tvalid && s_tready;
    wire  [12:0] pic_wa = s_tuser ? 13'd0 : wn;

    harris u_h (.clk(clk), .rst_n(rst_n), .in_valid(in_valid), .win(win), .thresh(48'sd50000000), .out_valid(h_valid), .resp(h_resp), .corner(h_corner));

    assign s_tready = (st == 3'd0) && !(wn == N);
    wire acc = s_tvalid && s_tready;
    assign rd_x = lx[rd_idx];
    assign rd_y = ly[rd_idx];

    function automatic integer clamp(input integer v, input integer hi);
        clamp = (v < 0) ? 0 : (v > hi) ? hi : v;
    endfunction

    integer r, c;
    always_comb begin
        for (int i = 0; i < 7; i++)
            raddr[i] = 13'(clamp(int'(py) - 3 + i, H - 1) * W + clamp(int'(px) - 3 + int'(k), W - 1));
    end
    for (genvar g = 0; g < 7; g++) begin : g_pic
        harris_pic_ram #(.N(N)) u_ram (.clk(clk), .we(pic_we), .waddr(pic_wa), .wdata(s_tdata), .raddr(raddr_q[g]), .rdata(q[g]));
    end

    always_ff @(posedge clk) begin
        in_valid <= 1'b0;
        for (r = 0; r < 7; r = r + 1) raddr_q[r] <= raddr[r];
        cap_en1 <= (st == 3'd1);
        kd1 <= k;
        cap_en <= cap_en1;
        kd <= kd1;
        if (cap_en) for (r = 0; r < 7; r = r + 1) wreg[r][kd] <= q[r];
        if (!rst_n) begin
            st <= 3'd0; wn <= 13'd0; done <= 1'b0; count <= 16'd0;
        end else begin
            case (st)
                3'd0: if (acc) begin
                    if (s_tuser) begin
                        wn <= 13'd1; done <= 1'b0; count <= 16'd0;
                    end else begin
                        wn <= wn + 13'd1;
                        if (wn == N - 1) begin st <= 3'd1; px <= 7'd0; py <= 7'd0; k <= 3'd0; end
                    end
                end
                3'd1: begin                                        // address one column of the window per clock (the pixels follow one clock later)
                    k <= k + 3'd1;
                    if (k == 3'd6) st <= 3'd5;
                end
                3'd5: st <= 3'd6;                                  // drain: the last two columns are still on their way
                3'd6: st <= 3'd2;                                  // the last column is captured into wreg at the end of this clock
                3'd2: begin
                    for (r = 0; r < 7; r = r + 1)
                        for (c = 0; c < 7; c = c + 1)
                            win[(7*r + c)*8 +: 8] <= wreg[r][c];
                    in_valid <= 1'b1;
                    st <= 3'd3;
                end
                3'd3: st <= 3'd4;                                  // harris.sv registers the answer one clock after in_valid
                3'd4: begin
                    if (h_valid) begin
                        if (h_corner) begin
                            if (count < 64) begin lx[count[5:0]] <= px; ly[count[5:0]] <= py; end
                            count <= count + 16'd1;
                        end
                        k <= 3'd0;
                        if (px == W - 1) begin
                            px <= 7'd0;
                            if (py == H - 1) begin st <= 3'd0; done <= 1'b1; wn <= 13'd0; end
                            else begin py <= py + 7'd1; st <= 3'd1; end
                        end else begin px <= px + 7'd1; st <= 3'd1; end
                    end
                end
                default: st <= 3'd0;
            endcase
        end
    end
endmodule
