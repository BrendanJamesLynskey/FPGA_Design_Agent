// AXI-Stream 24-bit to 32-bit upscaler with data format selection.
// The spec names (s_axis_valid/_data/_ready, m_axis_*) are the functional ports;
// the AMBA-named t* ports are aliases: outputs mirror them, inputs are unused.
module axis_upscale (
    input  logic        clk,
    input  logic        resetn,
    input  logic        dfmt_enable,
    input  logic        dfmt_type,
    input  logic        dfmt_se,
    input  logic        s_axis_valid,
    input  logic [23:0] s_axis_data,
    output logic        s_axis_ready,
    input  logic        m_axis_ready,
    output logic        m_axis_valid,
    output logic [31:0] m_axis_data,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic        s_axis_tvalid,
    input  logic [23:0] s_axis_tdata,
    input  logic        m_axis_tready,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic        s_axis_tready,
    output logic        m_axis_tvalid,
    output logic [31:0] m_axis_tdata
);

  logic bit23;
  logic [7:0] ext;

  assign s_axis_ready = ~m_axis_valid | m_axis_ready;
  assign s_axis_tready = s_axis_ready;
  assign m_axis_tvalid = m_axis_valid;
  assign m_axis_tdata  = m_axis_data;
  assign bit23 = s_axis_data[23] ^ (dfmt_enable & dfmt_type);
  assign ext   = {8{dfmt_enable & dfmt_se & bit23}};

  always_ff @(posedge clk) begin
    if (!resetn) begin
      m_axis_valid <= 1'b0;
      m_axis_data  <= 32'h0;
    end else if (s_axis_ready) begin
      m_axis_valid <= s_axis_valid;
      m_axis_data  <= {ext, bit23, s_axis_data[22:0]};
    end
  end

endmodule
