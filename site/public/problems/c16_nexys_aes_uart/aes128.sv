// source: solutions/p16l02_aes128/aes128.sv (course file, unchanged below this line)
// Part 16 lesson 2 exercise: an iterative AES-128 encryptor, one round per clock, round keys expanded on the fly (FIPS 197). The S-box is given (aes_sbox_tab.sv, a look-up table).
//
// Blocks are 128-bit vectors in FIPS 197 byte order: byte 0 (state row 0, column 0) is bits [127:120], byte 1 is [119:112], ... byte 15 is [7:0]; byte i is row i%4, column i/4. A key is the same.
// start (one clock, while !busy) samples key and pt: round 0 (AddRoundKey) is done in that clock. Rounds 1..10 take one clock each (round 10 has no MixColumns). busy is high from the clock after start until the
// result is ready. done is high for exactly one clock when ct is valid; ct then keeps its value until the next start. The latency is constant: done is high 10 rising edges after the edge that sampled start,
// whatever the key and data. rst_n is synchronous, active low, and clears busy and done.
module aes128 (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         start,
    input  logic [127:0] key,
    input  logic [127:0] pt,
    output logic         busy,
    output logic         done,
    output logic [127:0] ct
);
    logic [127:0] st, rk;
    logic [3:0]   rnd;
    logic [7:0]   rcon;
    logic [7:0]   sb [0:15];
    logic [7:0]   kb [0:3];
    for (genvar i = 0; i < 16; i++) begin : g_sb
        aes_sbox_tab u (.x(st[127 - 8*i -: 8]), .y(sb[i]));
    end
    for (genvar i = 0; i < 4; i++) begin : g_kb
        aes_sbox_tab u (.x(rk[(3 - ((i + 1) % 4)) * 8 +: 8]), .y(kb[i]));      // SubWord(RotWord(w3)): w3 = rk[31:0], byte 0 of w3 is rk[31:24]
    end
    function automatic logic [7:0] xt(input logic [7:0] a);
        xt = {a[6:0], 1'b0} ^ (a[7] ? 8'h1B : 8'h00);
    endfunction
    // next round key
    logic [31:0] w0, w1, w2, w3, t, n0, n1, n2, n3;
    logic [127:0] rk_n;
    always_comb begin
        {w0, w1, w2, w3} = rk;
        t = {kb[0] ^ rcon, kb[1], kb[2], kb[3]};
        n0 = w0 ^ t; n1 = w1 ^ n0; n2 = w2 ^ n1; n3 = w3 ^ n2;
        rk_n = {n0, n1, n2, n3};
    end
    // round function
    logic [7:0] sr [0:15];
    logic [7:0] mc [0:15];
    logic [127:0] st_n;
    always_comb begin
        for (int c = 0; c < 4; c++)
            for (int r = 0; r < 4; r++) sr[4*c + r] = sb[4*((c + r) % 4) + r];
        for (int c = 0; c < 4; c++) begin
            mc[4*c + 0] = xt(sr[4*c]) ^ (xt(sr[4*c + 1]) ^ sr[4*c + 1]) ^ sr[4*c + 2] ^ sr[4*c + 3];
            mc[4*c + 1] = sr[4*c] ^ xt(sr[4*c + 1]) ^ (xt(sr[4*c + 2]) ^ sr[4*c + 2]) ^ sr[4*c + 3];
            mc[4*c + 2] = sr[4*c] ^ sr[4*c + 1] ^ xt(sr[4*c + 2]) ^ (xt(sr[4*c + 3]) ^ sr[4*c + 3]);
            mc[4*c + 3] = (xt(sr[4*c]) ^ sr[4*c]) ^ sr[4*c + 1] ^ sr[4*c + 2] ^ xt(sr[4*c + 3]);
        end
        for (int i = 0; i < 16; i++) st_n[127 - 8*i -: 8] = (rnd == 4'd10) ? sr[i] : mc[i];
        st_n = st_n ^ rk_n;
    end
    always_comb begin
        case (rnd)
            4'd1: rcon = 8'h01; 4'd2: rcon = 8'h02; 4'd3: rcon = 8'h04; 4'd4: rcon = 8'h08; 4'd5: rcon = 8'h10;
            4'd6: rcon = 8'h20; 4'd7: rcon = 8'h40; 4'd8: rcon = 8'h80; 4'd9: rcon = 8'h1B; default: rcon = 8'h36;
        endcase
    end
    always_ff @(posedge clk) begin
        done <= 1'b0;
        if (!rst_n) busy <= 1'b0;
        else if (!busy) begin
            if (start) begin st <= pt ^ key; rk <= key; rnd <= 4'd1; busy <= 1'b1; end
        end else begin
            st <= st_n; rk <= rk_n; rnd <= rnd + 1'b1;
            if (rnd == 4'd10) begin busy <= 1'b0; done <= 1'b1; ct <= st_n; end
        end
    end
endmodule
