module ddm_cache (
  input  logic        clk,
  input  logic        rst_n,
  input  logic [31:0] cpu_addr,
  input  logic [31:0] cpu_dout,
  input  logic        cpu_strobe,
  input  logic        cpu_rw,
  input  logic        uncached,
  input  logic [31:0] mem_dout,
  input  logic        mem_ready,
  output logic [31:0] cpu_din,
  output logic [31:0] mem_din,
  output logic        cpu_ready,
  output logic        mem_strobe,
  output logic        mem_rw,
  output logic [31:0] mem_addr,
  output logic        cache_hit,
  output logic        cache_miss,
  output logic [31:0] d_data_dout
);

  logic [63:0]  d_valid;
  logic [63:0]  d_wr;      // entry data written since the last held reset
  /* verilator lint_off PROCASSINIT */
  logic         rst_q = 1'b1;
  /* verilator lint_on PROCASSINIT */
  logic [23:0]  d_tags [0:63];
  logic [31:0]  d_data [0:63];

  logic [23:0] tag;
  logic [5:0]  index;
  logic [31:0] cache_din;
  logic        cache_write;
  logic [23:0] d_tag_out;
  logic        valid;
  logic [31:0] cache_dout;

  assign tag   = cpu_addr[31:8];
  assign index = cpu_addr[7:2];
  assign cache_write = ~uncached & (cpu_rw | (cache_miss & mem_ready));

  always_ff @(posedge clk) rst_q <= rst_n;

  // synchronous clear of the valid bits; the read side is masked by rst_n
  // so the clear is visible at once (as an asynchronous clear would be)
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      d_valid <= 64'd0;
    end else if (cache_write) begin
      d_valid[index] <= 1'b1;
    end
  end

  // data-read mask: cleared when reset is held for two clocks
  always_ff @(posedge clk) begin
    if (!rst_n && !rst_q) begin
      d_wr <= 64'd0;
    end else if (rst_n && cache_write) begin
      d_wr[index] <= 1'b1;
    end
  end

  assign cache_din = cpu_rw ? cpu_dout : mem_dout;

  always_ff @(posedge clk) begin
    if (rst_n && cache_write) begin
      d_tags[index] <= tag;
      d_data[index] <= cache_din;
    end
  end

  assign valid      = d_valid[index] & rst_n;
  assign d_tag_out  = d_tags[index];
  assign cache_dout = d_data[index] & {32{d_wr[index]}};

  assign cache_hit   = cpu_strobe & valid & (d_tag_out == tag);
  assign cache_miss  = cpu_strobe & (~valid | (d_tag_out != tag));
  assign mem_din     = cpu_dout;
  assign mem_addr    = cpu_addr;
  assign mem_rw      = cpu_rw;
  assign mem_strobe  = cpu_strobe | cache_miss;
  assign cpu_ready   = (~cpu_rw & cache_hit) | ((cache_miss | cpu_rw) & mem_ready);
  assign cpu_din     = cache_hit ? cache_dout : mem_dout;
  assign d_data_dout = cache_dout;
endmodule
