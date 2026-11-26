module matrix_multiplier #(
  parameter ROW_A             = 4,
  parameter COL_A             = 4,
  parameter ROW_B             = 4,
  parameter COL_B             = 4,
  parameter INPUT_DATA_WIDTH  = 8,
  parameter OUTPUT_DATA_WIDTH = (INPUT_DATA_WIDTH * 2) + $clog2(COL_A)
) (
  input  logic                                       clk,
  input  logic                                       srst,
  input  logic                                       valid_in,
  input  logic [ (ROW_A*COL_A*INPUT_DATA_WIDTH)-1:0] matrix_a,
  input  logic [ (ROW_B*COL_B*INPUT_DATA_WIDTH)-1:0] matrix_b,
  output logic                                       valid_out,
  output logic [(ROW_A*COL_B*OUTPUT_DATA_WIDTH)-1:0] matrix_c
);
  localparam int LEVELS            = $clog2(COL_A);
  localparam int MODIFIED_COL_A    = (COL_A <= 1) ? 1 : (1 << LEVELS);
  localparam int HALF_MODIFIED_COL_A = MODIFIED_COL_A / 2;
  localparam int OW                = OUTPUT_DATA_WIDTH;
  localparam int IW                = INPUT_DATA_WIDTH;

  // valid pipeline: stage 0 = multiply, stages 1..LEVELS = tree, LEVELS+1 = output
  logic [LEVELS+1:0] valid_pipe;

  always_ff @(posedge clk)
    if (srst) valid_pipe <= '0;
    else      valid_pipe <= {valid_pipe[LEVELS:0], valid_in};

  assign valid_out = valid_pipe[LEVELS+1];

  genvar i, j, k, l;
  generate
    for (i = 0; i < ROW_A; i++) begin : row_a_gb
      for (j = 0; j < COL_B; j++) begin : col_b_gb
        logic [OW-1:0] mult_stage [MODIFIED_COL_A];
        logic [OW-1:0] final_sum;

        for (k = 0; k < MODIFIED_COL_A; k++) begin : mult_gb
          if (k < COL_A) begin : real_col
            always_ff @(posedge clk)
              if (srst) mult_stage[k] <= '0;
              else      mult_stage[k] <= OW'(matrix_a[((i*COL_A)+k)*IW +: IW]
                                           * matrix_b[((k*COL_B)+j)*IW +: IW]);
          end else begin : pad_col
            always_ff @(posedge clk)
              if (srst) mult_stage[k] <= '0;
              else      mult_stage[k] <= '0;
          end
        end

        if (LEVELS == 0) begin : no_tree
          assign final_sum = mult_stage[0];
        end else begin : tree
          logic [OW-1:0] add_stage [LEVELS][HALF_MODIFIED_COL_A];
          for (l = 0; l < LEVELS; l++) begin : lvl
            for (k = 0; k < HALF_MODIFIED_COL_A; k++) begin : node
              if (k < (MODIFIED_COL_A >> (l + 1))) begin : active
                if (l == 0) begin : first
                  always_ff @(posedge clk)
                    if (srst) add_stage[l][k] <= '0;
                    else      add_stage[l][k] <= mult_stage[2*k] + mult_stage[2*k+1];
                end else begin : rest
                  always_ff @(posedge clk)
                    if (srst) add_stage[l][k] <= '0;
                    else      add_stage[l][k] <= add_stage[l-1][2*k] + add_stage[l-1][2*k+1];
                end
              end else begin : idle
                always_ff @(posedge clk)
                  add_stage[l][k] <= '0;
              end
            end
          end
          assign final_sum = add_stage[LEVELS-1][0];
        end

        always_ff @(posedge clk)
          if (srst)                    matrix_c[((i*COL_B)+j)*OW +: OW] <= '0;
          else if (valid_pipe[LEVELS]) matrix_c[((i*COL_B)+j)*OW +: OW] <= final_sum;
      end
    end
  endgenerate
endmodule
