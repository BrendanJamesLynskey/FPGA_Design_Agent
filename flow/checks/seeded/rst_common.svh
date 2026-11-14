// rst_common.svh: the shared body of the reset check's seeded designs (brief 71). Each seeded top defines the macros
// that select one fault; with none defined the body follows every reset rule (rst_clean).
//   clk_a domain: a 16x16 multiply with input and output registers (fits a DSP48E1) and a 256x16 RAM with a registered
//                 read (fits a block RAM), reset by rst_a (xpm_cdc_async_rst from the active-low button);
//   clk_b domain: a 16-bit counter reset by rst_b (the shell's reset_sync from the same button).
    logic rst_a_n, rst_a, rst_b;
`ifdef F5_LUT_ASYNC
    // F5: logic (an OR with a soft reset) drives the synchroniser's asynchronous reset input
    xpm_cdc_async_rst #(.DEST_SYNC_FF(2), .RST_ACTIVE_HIGH(0)) u_sync_a (.src_arst(rst_n_btn & ~soft_rst), .dest_clk(clk_a), .dest_arst(rst_a_n));
`else
    xpm_cdc_async_rst #(.DEST_SYNC_FF(2), .RST_ACTIVE_HIGH(0)) u_sync_a (.src_arst(rst_n_btn), .dest_clk(clk_a), .dest_arst(rst_a_n));
`endif
    assign rst_a = ~rst_a_n;
    reset_sync u_sync_b (.clk(clk_b), .rst_n_async(rst_n_btn), .rst(rst_b));

    // DSP: input registers, product register, output register
    logic signed [15:0] ar, br;
    logic signed [31:0] m, pr;
`ifdef F3_DSP_ASYNC
    always_ff @(posedge clk_a or posedge rst_a) begin
`else
    always_ff @(posedge clk_a) begin
`endif
        if (rst_a) begin ar <= '0; br <= '0; m <= '0; pr <= '0; end
        else begin ar <= a; br <= b; m <= ar * br; pr <= m; end
    end
    assign p = pr;

    // RAM: synchronous write, registered read, output register with a reset
    logic [15:0] mem [0:255];
    logic [15:0] rd, rq;
    always_ff @(posedge clk_a) begin
        if (we) mem[waddr] <= wdata;
        rd <= mem[raddr];
    end
    // the synchroniser's output is a register with an asynchronous set or reset: it must not drive a block-RAM control pin
    // (AMD DRC REQP-1840), so the RAM's output register takes its synchronous reset from one plain register after it (brief 70)
    logic rst_ram;
    always_ff @(posedge clk_a) rst_ram <= rst_a;
`ifdef F3B_BRAM_ASYNC
    always_ff @(posedge clk_a or posedge rst_a) begin
        if (rst_a) rq <= '0;
        else       rq <= rd;
    end
`else
    always_ff @(posedge clk_a) begin
        if (rst_ram) rq <= '0;
        else         rq <= rd;
    end
`endif
    assign rdata = rq;

    // clk_b counter
`ifdef F4_CDC_SYNC
    wire rst_cnt = rst_a;          // F4: clk_a's reset used as clk_b's synchronous reset, no synchroniser
`elsif F4B_CDC_ASYNC
    wire rst_cnt = rst_a;          // F4b: the same, as an asynchronous reset
`else
    wire rst_cnt = rst_b;
`endif
    logic [15:0] cnt;
`ifdef F1_ASYNC
    always_ff @(posedge clk_b or posedge rst_cnt) begin   // F1: asynchronous reset in ordinary logic
`elsif F4B_CDC_ASYNC
    always_ff @(posedge clk_b or posedge rst_cnt) begin
`else
    always_ff @(posedge clk_b) begin
`endif
        if (rst_cnt) cnt <= '0;
        else         cnt <= cnt + 16'd1;
    end
    assign cnt_b = cnt;

    // F2: the same reset used active high above and active low here
    logic [15:0] acc;
    always_ff @(posedge clk_a) begin
`ifdef F2_POLARITY
        if (!rst_a) acc <= '0;
`else
        if (rst_a) acc <= '0;
`endif
        else        acc <= acc + a;
    end
    assign acc_o = acc;
