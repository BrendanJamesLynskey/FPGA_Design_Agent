// p2_core: register map, ROM, RAM, March C- engine and LEDs for the JTAG register port.
module p2_core #(
    parameter int unsigned        DESIGN_ID     = 32'h20920001,
    parameter logic [31:0]        RAM_INIT_BASE = 32'hC0DE0000,
    parameter string              ROM_INIT_FILE = "data/rom_init.hex"
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    localparam logic [9:0] FAULT_ADDR = 10'h155;

    assign sfp_tx_disable = 1'b1;

    // ---- BUILD word ----
    logic [31:0] build_word;
`ifdef SYNTHESIS
    USR_ACCESSE2 u_usr (.CFGCLK(), .DATA(build_word), .DATAVALID());
`else
    /* verilator lint_off PINCONNECTEMPTY */
    USR_ACCESSE2 u_usr (.DATA(build_word), .DATAVALID());
    /* verilator lint_on PINCONNECTEMPTY */
`endif

    // ---- registers ----
    logic [31:0] scratch;
    logic [9:0]  mem_addr;
    logic        autoinc;
    logic        inject;
    logic [15:0] passes;
    logic        busy, done;
    logic [15:0] completed;
    logic [31:0] errs, first_err;

    // ---- memories ----
    logic [31:0] rom [0:1023];
    logic [31:0] ram [0:1023];
    initial begin
        $readmemh(ROM_INIT_FILE, rom);
        for (int i = 0; i < 1024; i++) ram[i] = RAM_INIT_BASE + 32'(i);
    end

    logic [31:0] rom_q, ram_q;
    logic [9:0]  ram_a;
    logic [31:0] ram_d;
    logic        ram_we;

    always_ff @(posedge clk) begin
        rom_q <= rom[mem_addr];
        if (ram_we) ram[ram_a] <= ram_d;
        ram_q <= ram[ram_a];
    end

    // ---- host decode ----
    logic sel_scratch, sel_maddr, sel_ramd, sel_mctrl, sel_mpass, sel_mem_ctrl, sel_romd;
    assign sel_scratch  = (h_addr == 12'h008);
    assign sel_maddr    = (h_addr == 12'h010);
    assign sel_romd     = (h_addr == 12'h014);
    assign sel_ramd     = (h_addr == 12'h018);
    assign sel_mem_ctrl = (h_addr == 12'h01C);
    assign sel_mctrl    = (h_addr == 12'h020);
    assign sel_mpass    = (h_addr == 12'h024);

    logic start;
    assign start = h_we && sel_mctrl && h_wdata[0] && !busy;

    logic host_ram_wr, host_ram_rd, host_rom_rd;
    assign host_ram_wr = h_we && sel_ramd && !busy;
    assign host_ram_rd = h_re && sel_ramd && !busy;
    assign host_rom_rd = h_re && sel_romd;

    // ---- march engine ----
    logic        bg_i;          // 0: all-ones background, 1: all-zero background
    logic [2:0]  ph;
    logic [9:0]  ea;
    logic        sub;
    logic [15:0] passes_lat;
    logic [31:0] bg, cbg;
    assign bg  = bg_i ? 32'h0 : 32'hFFFF_FFFF;
    assign cbg = ~bg;

    logic eng_we;
    logic [31:0] eng_d;
    always_comb begin
        eng_we = 1'b0;
        eng_d  = bg;
        if (ph == 3'd0) eng_we = 1'b1;
        else if (ph <= 3'd4 && sub) begin
            eng_we = 1'b1;
            eng_d  = ph[0] ? cbg : bg;
        end
    end

    always_comb begin
        if (busy) begin
            ram_a  = ea;
            ram_we = eng_we;
            ram_d  = eng_d;
        end else begin
            ram_a  = mem_addr;
            ram_we = host_ram_wr;
            ram_d  = h_wdata;
        end
    end

    logic [31:0] exp_w, rd_w;
    logic        cmp_en, inj_now, last_a, down;
    assign cmp_en  = busy && sub && (ph != 3'd0);
    assign exp_w   = (ph == 3'd2 || ph == 3'd4) ? cbg : bg;
    assign inj_now = inject && !bg_i && (ph == 3'd1) && (ea == FAULT_ADDR);
    assign rd_w    = inj_now ? (ram_q ^ 32'h1) : ram_q;
    assign down    = (ph == 3'd3) || (ph == 3'd4);
    assign last_a  = down ? (ea == 10'd0) : (ea == 10'd1023);

    logic step_adv;   // address step completes this clock
    assign step_adv = (ph == 3'd0) || sub;

    // ---- host read pipeline ----
    logic        pend_rom, pend_ram, ram_ok;

    always_ff @(posedge clk) begin
        if (rst) begin
            scratch    <= 32'h0;
            mem_addr   <= 10'h0;
            autoinc    <= 1'b0;
            inject     <= 1'b0;
            passes     <= 16'd1;
            busy       <= 1'b0;
            done       <= 1'b0;
            completed  <= 16'h0;
            errs       <= 32'h0;
            first_err  <= 32'hFFFF_FFFF;
            bg_i       <= 1'b0;
            ph         <= 3'd0;
            ea         <= 10'h0;
            sub        <= 1'b0;
            passes_lat <= 16'd1;
            pend_rom   <= 1'b0;
            pend_ram   <= 1'b0;
            ram_ok     <= 1'b0;
            h_rdata    <= 32'h0;
        end else begin
            // ---- host writes ----
            if (h_we) begin
                if (sel_scratch)  scratch  <= h_wdata;
                if (sel_maddr)    mem_addr <= h_wdata[9:0];
                if (sel_mem_ctrl) autoinc  <= h_wdata[0];
                if (sel_mctrl)    inject   <= h_wdata[1];
                if (sel_mpass)    passes   <= h_wdata[15:0];
            end
            if ((host_ram_wr || host_ram_rd || host_rom_rd) && autoinc) mem_addr <= mem_addr + 10'd1;

            // ---- read pipeline ----
            pend_rom <= host_rom_rd;
            pend_ram <= h_re && sel_ramd;
            ram_ok   <= !busy;
            if (h_re && !(sel_romd || sel_ramd)) begin
                case (h_addr)
                    12'h000: h_rdata <= DESIGN_ID;
                    12'h004: h_rdata <= build_word;
                    12'h008: h_rdata <= scratch;
                    12'h010: h_rdata <= {22'h0, mem_addr};
                    12'h01C: h_rdata <= {31'h0, autoinc};
                    12'h020: h_rdata <= {30'h0, inject, 1'b0};
                    12'h024: h_rdata <= {16'h0, passes};
                    12'h028: h_rdata <= {completed, 14'h0, done, busy};
                    12'h02C: h_rdata <= errs;
                    12'h030: h_rdata <= first_err;
                    default: h_rdata <= 32'h0;
                endcase
            end
            if (pend_rom) h_rdata <= rom_q;
            if (pend_ram) h_rdata <= ram_ok ? ram_q : 32'h0;

            // ---- march control ----
            if (start) begin
                busy       <= 1'b1;
                done       <= 1'b0;
                completed  <= 16'h0;
                errs       <= 32'h0;
                first_err  <= 32'hFFFF_FFFF;
                bg_i       <= 1'b0;
                ph         <= 3'd0;
                ea         <= 10'h0;
                sub        <= 1'b0;
                passes_lat <= (passes == 16'h0) ? 16'd1 : passes;
            end else if (busy) begin
                if (cmp_en && (rd_w != exp_w)) begin
                    errs <= errs + 32'd1;
                    if (first_err == 32'hFFFF_FFFF) first_err <= {22'h0, ea};
                end
                if (ph != 3'd0) sub <= ~sub;
                if (step_adv) begin
                    if (!(ph == 3'd0 ? (ea == 10'd1023) : last_a)) begin
                        ea <= down ? ea - 10'd1 : ea + 10'd1;
                    end else begin
                        // phase complete
                        case (ph)
                            3'd0: begin ph <= 3'd1; ea <= 10'd0; end
                            3'd1: begin ph <= 3'd2; ea <= 10'd0; end
                            3'd2: begin ph <= 3'd3; ea <= 10'd1023; end
                            3'd3: begin ph <= 3'd4; ea <= 10'd1023; end
                            3'd4: begin ph <= 3'd5; ea <= 10'd0; end
                            default: begin
                                ph <= 3'd0; ea <= 10'd0;
                                if (!bg_i) bg_i <= 1'b1;
                                else begin
                                    bg_i      <= 1'b0;
                                    completed <= completed + 16'd1;
                                    if (completed + 16'd1 == passes_lat) begin
                                        busy <= 1'b0;
                                        done <= 1'b1;
                                    end
                                end
                            end
                        endcase
                    end
                end
            end
        end
    end

    assign led = {done, busy};
endmodule
