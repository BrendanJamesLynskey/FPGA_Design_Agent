// GF(2^8) (poly 0x11B) 4x4 byte matrix encrypt/decrypt, AES MixColumns style, key XOR by row.
// 3-stage pipeline, one operation per clock. Mode bit travels with the data.
module galois_encryption #(
    parameter int NBW_DATA = 128,
    parameter int NBW_KEY  = 32,
    parameter int LATENCY  = 3      // pipeline depth is fixed at 3 stages
) (
    input  logic                clk,
    input  logic                rst_async_n,
    input  logic                i_encrypt,
    input  logic                i_valid,
    input  logic [NBW_DATA-1:0] i_data,
    input  logic                i_update_key,
    input  logic [NBW_KEY-1:0]  i_key,
    output logic                o_valid,
    output logic [NBW_DATA-1:0] o_data
);

  localparam int W = 8;
  localparam int N = 16;

  // reduce by 0x11B only when bit 7 overflows
  function automatic logic [7:0] xt(input logic [7:0] a);
    xt = {a[6:0], 1'b0} ^ (a[7] ? 8'h1B : 8'h00);
  endfunction

  // ---------------- control (synchronous reset) ----------------
  logic [LATENCY-1:0] valid_ff;
  logic [NBW_KEY-1:0] key_ff;
  logic               enc1_ff, enc2_ff, enc3_ff;

  always_ff @(posedge clk) begin : ctrl_regs
    if (!rst_async_n) begin
      valid_ff <= '0;
      key_ff   <= '0;
    end else begin
      valid_ff <= {valid_ff[LATENCY-2:0], i_valid};
      if (i_update_key) key_ff <= i_key;
    end
  end

  // ---------------- data path (no reset) ----------------
  logic [W-1:0] in_ff [N];
  logic [W-1:0] x1_ff [N];
  logic [W-1:0] x2_ff [N];
  logic [W-1:0] x3_ff [N];
  logic [W-1:0] x9_ff [N];
  logic [W-1:0] xb_ff [N];
  logic [W-1:0] xd_ff [N];
  logic [W-1:0] xe_ff [N];
  logic [W-1:0] out_ff[N];

  logic [W-1:0] x2n[N], x4n[N], x8n[N];
  logic [W-1:0] out_nx[N];

  always_comb begin : xtimes
    for (int i = 0; i < N; i++) begin
      x2n[i] = xt(in_ff[i]);
      x4n[i] = xt(x2n[i]);
      x8n[i] = xt(x4n[i]);
    end
  end

  // stage 3 combinational matrix, selected by the mode that travelled with the data
  always_comb begin : matrix
    for (int r = 0; r < 4; r++) begin
      for (int c = 0; c < 4; c++) begin
        if (enc2_ff) begin
          out_nx[r*4+c] = x2_ff[r*4+c] ^ x3_ff[((r+1)%4)*4+c]
                        ^ x1_ff[((r+2)%4)*4+c] ^ x1_ff[((r+3)%4)*4+c];
        end else begin
          out_nx[r*4+c] = xe_ff[r*4+c] ^ xb_ff[((r+1)%4)*4+c]
                        ^ xd_ff[((r+2)%4)*4+c] ^ x9_ff[((r+3)%4)*4+c];
        end
      end
    end
  end

  always_ff @(posedge clk) begin : data_regs
    // stage 1: capture (decrypt: XOR key by row first)
    enc1_ff <= i_encrypt;
    for (int r = 0; r < 4; r++) begin
      for (int c = 0; c < 4; c++) begin
        in_ff[r*4+c] <= i_encrypt ? i_data[NBW_DATA-1-8*(c+4*r)-:W]
                                  : i_data[NBW_DATA-1-8*(c+4*r)-:W] ^ key_ff[NBW_KEY-1-8*r-:W];
      end
    end
    // stage 2: multiples
    enc2_ff <= enc1_ff;
    for (int i = 0; i < N; i++) begin
      x1_ff[i] <= in_ff[i];
      x2_ff[i] <= x2n[i];
      x3_ff[i] <= x2n[i] ^ in_ff[i];
      x9_ff[i] <= x8n[i] ^ in_ff[i];
      xb_ff[i] <= x8n[i] ^ x2n[i] ^ in_ff[i];
      xd_ff[i] <= x8n[i] ^ x4n[i] ^ in_ff[i];
      xe_ff[i] <= x8n[i] ^ x4n[i] ^ x2n[i];
    end
    // stage 3: matrix
    enc3_ff <= enc2_ff;
    for (int i = 0; i < N; i++) out_ff[i] <= out_nx[i];
  end

  // ---------------- outputs ----------------
  // reset also gates the outputs combinationally so o_valid/o_data clear without a clock edge
  logic out_ok;
  assign out_ok  = valid_ff[LATENCY-1] & rst_async_n;
  assign o_valid = out_ok;

  always_comb begin : out_map
    o_data = '0;
    if (out_ok) begin
      for (int r = 0; r < 4; r++) begin
        for (int c = 0; c < 4; c++) begin
          o_data[NBW_DATA-1-8*(c+4*r)-:W] = enc3_ff ? out_ff[r*4+c] ^ key_ff[NBW_KEY-1-8*r-:W]
                                                    : out_ff[r*4+c];
        end
      end
    end
  end

endmodule : galois_encryption
