// APB slave: 5 RW CSRs, RO result, 1 KB SRAM, add/multiply of two SRAM operands.
module apb_dsp_unit #(
    parameter int ADDR_WIDTH = 10,
    parameter int DATA_WIDTH = 8,
    parameter int MEM_DEPTH  = 1024
) (
    input  wire                  pclk,
    input  wire                  presetn,
    input  wire [ADDR_WIDTH-1:0] paddr,
    input  wire                  pselx,
    input  wire                  penable,
    input  wire                  pwrite,
    input  wire [DATA_WIDTH-1:0] pwdata,
    output wire                  pready,
    output wire [DATA_WIDTH-1:0] prdata,
    output wire                  pslverr,
    input  wire                  sram_valid
);
  // Active-high internal reset, inverted once at entry; used synchronously.
  wire rst = ~presetn;

  localparam logic [1:0] S_IDLE = 2'd0, S_READ = 2'd1, S_WRITE = 2'd2;
  localparam int MA = $clog2(MEM_DEPTH);

  logic [1:0]            state;
  logic                  pready_q, pslverr_q;
  logic [DATA_WIDTH-1:0] prdata_q;
  logic [DATA_WIDTH-1:0] r_operand_1, r_operand_2, r_enable, r_write_address, r_write_data;
  logic [DATA_WIDTH-1:0] result;
  logic                  prev_valid;

  // Outputs read 0 while presetn is low (also before the first clock edge in reset).
  assign pready  = pready_q & presetn;
  assign pslverr = pslverr_q & presetn;
  assign prdata  = prdata_q & {DATA_WIDTH{presetn}};

  // ---------------- APB FSM and CSRs ----------------
  always_ff @(posedge pclk) begin
    if (rst) begin
      state           <= S_IDLE;
      pready_q        <= 1'b0;
      pslverr_q       <= 1'b0;
      prdata_q        <= '0;
      r_operand_1     <= '0;
      r_operand_2     <= '0;
      r_enable        <= '0;
      r_write_address <= '0;
      r_write_data    <= '0;
    end else begin
      if (state == S_IDLE) begin
        pready_q <= 1'b0;
        if (pselx && !penable) begin
          state    <= pwrite ? S_WRITE : S_READ;
          pready_q <= 1'b1;
        end
      end else begin
        if (pselx && penable) begin
          if (state == S_WRITE) begin
            pslverr_q <= 1'b1;
            if (paddr <= 10'd4) begin
              pslverr_q <= 1'b0;
              case (paddr[2:0])
                3'd0: r_operand_1 <= pwdata;
                3'd1: r_operand_2 <= pwdata;
                3'd2: r_enable <= pwdata;
                3'd3: r_write_address <= pwdata;
                default: r_write_data <= pwdata;
              endcase
            end
          end else begin
            pslverr_q <= 1'b0;
            prdata_q  <= '0;
            if (paddr <= 10'd5) begin
              case (paddr[2:0])
                3'd0: prdata_q <= r_operand_1;
                3'd1: prdata_q <= r_operand_2;
                3'd2: prdata_q <= r_enable;
                3'd3: prdata_q <= r_write_address;
                3'd4: prdata_q <= r_write_data;
                default: prdata_q <= result;
              endcase
            end else begin
              pslverr_q <= 1'b1;
            end
          end
        end
        state    <= S_IDLE;
        pready_q <= 1'b0;
      end
    end
  end

  // ---------------- SRAM (two copies so both operands read each cycle) ----------------
  (* ram_style = "block" *) logic [DATA_WIDTH-1:0] mem_a[MEM_DEPTH];
  (* ram_style = "block" *) logic [DATA_WIDTH-1:0] mem_b[MEM_DEPTH];
  logic [DATA_WIDTH-1:0] rd1, rd2;
  wire                   sram_we = (r_enable == 8'd3) && sram_valid && !prev_valid;
  wire  [MA-1:0]         waddr = MA'(r_write_address);

  always_ff @(posedge pclk) begin
    if (sram_we) begin
      mem_a[waddr] <= r_write_data;
      mem_b[waddr] <= r_write_data;
    end
    rd1 <= mem_a[MA'(r_operand_1)];
    rd2 <= mem_b[MA'(r_operand_2)];
  end

  // ---------------- compute ----------------
  wire [DATA_WIDTH-1:0] prod = DATA_WIDTH'(rd1 * rd2);

  always_ff @(posedge pclk) begin
    if (rst) begin
      prev_valid <= 1'b0;
      result     <= '0;
    end else begin
      prev_valid <= sram_valid;
      if (r_enable == 8'd1) result <= rd1 + rd2;
      else if (r_enable == 8'd2) result <= prod;
    end
  end
endmodule
