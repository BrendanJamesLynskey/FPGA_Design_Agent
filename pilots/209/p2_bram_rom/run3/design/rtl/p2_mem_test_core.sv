// p2_mem_test_core: register map, ROM, RAM and March C- engine (single clock domain, active-high sync reset).
module p2_mem_test_core (
    input  logic        clk,
    input  logic        rst,
    input  logic        h_we,
    input  logic        h_re,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [11:0] h_addr,
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    localparam logic [31:0] DESIGN_ID = 32'h20920001;

    assign sfp_tx_disable = 1'b1;

    // ---------------- build stamp ----------------
    logic [31:0] build_word;
    /* verilator lint_off PINCONNECTEMPTY */
    USR_ACCESSE2 u_usr (.CFGCLK(), .DATA(build_word), .DATAVALID());
    /* verilator lint_on PINCONNECTEMPTY */

    // ---------------- memories ----------------
    (* rom_style = "block" *) logic [31:0] rom [0:1023];
    (* ram_style = "block" *) logic [31:0] ram [0:1023];
    initial $readmemh("data/rom_init.hex", rom);
    initial begin
        for (int i = 0; i < 1024; i++) ram[i] = 32'hC0DE0000 + 32'(i);
    end

    logic [9:0]  mem_addr;
    logic        autoinc, inject, busy, done;
    logic [15:0] passes, done_passes;
    logic [31:0] scratch, errs, first_err;

    // engine state
    logic [2:0] elem;
    logic       bgi, clr;
    logic [9:0] cnt;

    // check pipeline
    logic       chk_v, chk_exp, chk_f;
    logic [9:0] chk_addr;

    logic [16:0] dp_next;
    logic [15:0] tgt;
    logic        last_pass;
    assign dp_next   = {1'b0, done_passes} + 17'd1;
    assign tgt       = (passes == 16'd0) ? 16'd1 : passes;
    assign last_pass = (dp_next >= {1'b0, tgt});

    // engine combinational op
    logic        eng_we;
    logic [9:0]  eng_addr;
    logic [31:0] eng_wd;
    logic        eng_rd, eng_ebit;
    logic        down;
    always_comb begin
        down     = (elem == 3'd3) || (elem == 3'd4) || (elem == 3'd5);
        eng_addr = down ? ~cnt : cnt;
        eng_we   = 1'b0;
        eng_wd   = '0;
        eng_rd   = 1'b0;
        eng_ebit = 1'b0;
        if (!clr) begin
            // read-first RAM: read and write of one word share a clock
            eng_we = (elem != 3'd5);
            eng_rd = (elem != 3'd0);
            eng_wd = {32{(elem == 3'd1 || elem == 3'd3) ^ bgi}};
            if (elem == 3'd0) eng_wd = {32{bgi}};
            eng_ebit = (elem == 3'd2 || elem == 3'd4) ^ bgi;
            // last read of the last pass also writes zero (read-first RAM)
            if (elem == 3'd5 && bgi && last_pass) begin
                eng_we = 1'b1;
                eng_wd = '0;
            end
        end
    end

    // host decode
    logic [9:0] hidx;
    assign hidx = h_addr[11:2];
    logic hw_ram, hr_ram, hr_rom;
    assign hw_ram = h_we && (hidx == 10'd6) && !busy;
    assign hr_ram = h_re && (hidx == 10'd6) && !busy;
    assign hr_rom = h_re && (hidx == 10'd5);

    // ---------------- block RAM / ROM ----------------
    logic [9:0]  ram_a;
    logic        ram_we;
    logic [31:0] ram_d, ram_q, rom_q;
    assign ram_a  = busy ? eng_addr : mem_addr;
    assign ram_we = busy ? eng_we : hw_ram;
    assign ram_d  = busy ? eng_wd : h_wdata;

    always_ff @(posedge clk) begin
        if (ram_we) ram[ram_a] <= ram_d;
`ifndef SYNTHESIS
        // simulation only: model configuration (power-on) re-initialisation of the RAM
        if (rst) for (int i = 0; i < 1024; i++) ram[i] <= 32'hC0DE0000 + 32'(i);
`endif
        ram_q <= ram[ram_a];
        rom_q <= rom[mem_addr];
    end

    // ---------------- registers and engine ----------------
    logic wrong;
    assign wrong = chk_v && ((ram_q ^ {32{chk_exp}} ^ {32{inject & chk_f}}) != 32'd0);

    always_ff @(posedge clk) begin
        chk_v    <= busy && !clr && eng_rd;
        chk_exp  <= eng_ebit;
        chk_addr <= eng_addr;
        chk_f    <= (elem == 3'd1) && (cnt == 10'd0);
        if (rst) begin
            scratch <= '0; mem_addr <= '0; autoinc <= 1'b0; inject <= 1'b0;
            passes <= 16'd1; busy <= 1'b0; done <= 1'b0; done_passes <= '0;
            errs <= '0; first_err <= 32'hFFFFFFFF;
            elem <= '0; bgi <= 1'b0; clr <= 1'b0; cnt <= '0;
            chk_v <= 1'b0;
        end else begin
            // check results
            if (wrong) begin
                errs <= errs + 32'd1;
                if (first_err == 32'hFFFFFFFF) first_err <= {22'd0, chk_addr};
            end
            // engine
            if (busy) begin
                if (clr) begin
                    clr <= 1'b0; busy <= 1'b0; done <= 1'b1;
                end else begin
                    cnt <= cnt + 10'd1;
                    if (cnt == 10'd1023) begin
                        if (elem == 3'd5) begin
                            elem <= 3'd0;
                            bgi  <= !bgi;
                            if (bgi) begin
                                done_passes <= dp_next[15:0];
                                if (dp_next >= {1'b0, tgt}) clr <= 1'b1;
                            end
                        end else begin
                            elem <= elem + 3'd1;
                        end
                    end
                end
            end
            // host writes
            if (h_we) begin
                case (hidx)
                    10'd2: scratch <= h_wdata;
                    10'd4: mem_addr <= h_wdata[9:0];
                    10'd6: if (!busy && autoinc) mem_addr <= mem_addr + 10'd1;
                    10'd7: autoinc <= h_wdata[0];
                    10'd8: begin
                        inject <= h_wdata[1];
                        if (h_wdata[0] && !busy) begin
                            errs <= '0; first_err <= 32'hFFFFFFFF; done_passes <= '0;
                            done <= 1'b0; busy <= 1'b1;
                            elem <= '0; bgi <= 1'b0; clr <= 1'b0; cnt <= '0;
                        end
                    end
                    10'd9: passes <= h_wdata[15:0];
                    default: ;
                endcase
            end
            // host reads with auto-increment
            if ((hr_rom || hr_ram) && autoinc) mem_addr <= mem_addr + 10'd1;
        end
    end

    // ---------------- host read path (2 clocks) ----------------
    logic [31:0] pre;
    logic        sel_rom, sel_ram, pend;
    always_ff @(posedge clk) begin
        if (rst) begin
            h_rdata <= '0; pre <= '0; sel_rom <= 1'b0; sel_ram <= 1'b0; pend <= 1'b0;
        end else begin
            pend <= h_re;
            if (h_re) begin
                sel_rom <= (hidx == 10'd5);
                sel_ram <= hr_ram;
                case (hidx)
                    10'd0:  pre <= DESIGN_ID;
                    10'd1:  pre <= build_word;
                    10'd2:  pre <= scratch;
                    10'd4:  pre <= {22'd0, mem_addr};
                    10'd7:  pre <= {31'd0, autoinc};
                    10'd8:  pre <= {30'd0, inject, 1'b0};
                    10'd9:  pre <= {16'd0, passes};
                    10'd10: pre <= {done_passes, 14'd0, done, busy};
                    10'd11: pre <= errs;
                    10'd12: pre <= first_err;
                    default: pre <= '0;
                endcase
            end
            if (pend) h_rdata <= sel_rom ? rom_q : (sel_ram ? ram_q : pre);
        end
    end

    assign led = {done, busy};
endmodule
