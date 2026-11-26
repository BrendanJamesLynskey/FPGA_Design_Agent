// p2_core: register core. Common map, ROM, RAM, AUTOINC address logic, March C- engine, LEDs.
// Single clock domain. Host port: h_we/h_re pulses; h_rdata valid 1 clk after the h_re edge and held.
module p2_core #(
    parameter int unsigned DESIGN_ID    = 32'h20920001,
    parameter int unsigned FAULT_ADDR   = 0,
    parameter string       ROM_FILE     = "data/rom_init.hex"
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
    assign sfp_tx_disable = 1'b1;

    localparam logic [11:0] A_ID = 12'h000, A_BUILD = 12'h004, A_SCR = 12'h008, A_MADDR = 12'h010,
                            A_ROM = 12'h014, A_RAM = 12'h018, A_MCTL = 12'h01C, A_CTRL = 12'h020,
                            A_PASS = 12'h024, A_STAT = 12'h028, A_ERRS = 12'h02C, A_FIRST = 12'h030;

    // ---------------- BUILD stamp ----------------
    logic [31:0] usr_access;
    /* verilator lint_off PINMISSING */
    USR_ACCESSE2 u_usr (.DATA(usr_access));
    /* verilator lint_on PINMISSING */

    // ---------------- control registers ----------------
    logic [31:0] scratch;
    logic [9:0]  mem_addr;
    logic        autoinc, inject;
    logic [15:0] passes_cfg;
    logic        busy, done;
    logic [15:0] completed;
    logic [31:0] errs, first_err;

    // ---------------- memories ----------------
    (* rom_style = "block" *) logic [31:0] rom [0:1023];
    (* ram_style = "block" *) logic [31:0] ram [0:1023];
    initial $readmemh(ROM_FILE, rom);
    initial begin
        for (int i = 0; i < 1024; i++) ram[i] = 32'hC0DE0000 + 32'(i);
    end

    logic [31:0] rom_q, ram_q;
    logic [9:0]  m_addr;
    logic        m_we;
    logic [31:0] m_wdata;

    logic        host_ram_we;
    assign host_ram_we = h_we && (h_addr == A_RAM) && !busy;

    logic [9:0]  ram_a;
    logic        ram_we;
    logic [31:0] ram_d;
    assign ram_a  = busy ? m_addr  : mem_addr;
    assign ram_we = busy ? m_we    : host_ram_we;
    assign ram_d  = busy ? m_wdata : h_wdata;

    always_ff @(posedge clk) begin
        rom_q <= rom[mem_addr];
        if (ram_we) ram[ram_a] <= ram_d;
        ram_q <= ram[ram_a];
    end

    // ---------------- host read pipeline ----------------
    logic        re1;
    logic [11:0] ra1;
    logic        start;
    assign start = h_we && (h_addr == A_CTRL) && h_wdata[0] && !busy;

    always_ff @(posedge clk) begin
        if (rst) begin
            re1 <= 1'b0; ra1 <= '0; h_rdata <= '0;
            scratch <= '0; mem_addr <= '0; autoinc <= 1'b0; inject <= 1'b0; passes_cfg <= 16'd1;
        end else begin
            re1 <= h_re;
            if (h_re) ra1 <= h_addr;
            if (re1) begin
                case (ra1)
                    A_ID:    h_rdata <= DESIGN_ID;
                    A_BUILD: h_rdata <= usr_access;
                    A_SCR:   h_rdata <= scratch;
                    A_MADDR: h_rdata <= {22'd0, mem_addr};
                    A_ROM:   h_rdata <= rom_q;
                    A_RAM:   h_rdata <= busy ? 32'd0 : ram_q;
                    A_MCTL:  h_rdata <= {31'd0, autoinc};
                    A_CTRL:  h_rdata <= {30'd0, inject, 1'b0};
                    A_PASS:  h_rdata <= {16'd0, passes_cfg};
                    A_STAT:  h_rdata <= {completed, 14'd0, done, busy};
                    A_ERRS:  h_rdata <= errs;
                    A_FIRST: h_rdata <= first_err;
                    default: h_rdata <= 32'd0;
                endcase
                if (autoinc && (ra1 == A_ROM || (ra1 == A_RAM && !busy))) mem_addr <= mem_addr + 10'd1;
            end
            if (h_we) begin
                case (h_addr)
                    A_SCR:   scratch    <= h_wdata;
                    A_MADDR: mem_addr   <= h_wdata[9:0];
                    A_MCTL:  autoinc    <= h_wdata[0];
                    A_CTRL:  inject     <= h_wdata[1];
                    A_PASS:  passes_cfg <= h_wdata[15:0];
                    A_RAM:   if (!busy && autoinc) mem_addr <= mem_addr + 10'd1;
                    default: ;
                endcase
            end
        end
    end

    // ---------------- March C- engine ----------------
    typedef enum logic [1:0] {S_IDLE, S_ACT, S_CHK} state_t;
    state_t      st;
    logic        bgsel;        // 0: all-ones background, 1: all-zeros background
    logic [2:0]  elem;
    logic [15:0] total;
    logic        fault_used;

    logic        down, rd_exp_inv, wr_inv, has_rd, has_wr, last_addr;
    logic [31:0] bg, inv;
    assign bg  = bgsel ? 32'd0 : 32'hFFFFFFFF;
    assign inv = ~bg;
    assign down       = (elem >= 3'd3);
    assign has_rd     = (elem != 3'd0);
    assign has_wr     = (elem != 3'd5);
    assign rd_exp_inv = (elem == 3'd2) || (elem == 3'd4);
    assign wr_inv     = (elem == 3'd1) || (elem == 3'd3);
    assign m_we    = (st == S_ACT && elem == 3'd0) || (st == S_CHK && has_rd && has_wr);
    assign m_wdata = (elem == 3'd0) ? bg : (wr_inv ? inv : bg);
    assign last_addr  = down ? (m_addr == 10'd0) : (m_addr == 10'd1023);

    logic        flip, mism;
    logic [31:0] q_eff, exp_v;
    assign flip  = inject && !fault_used && (m_addr == 10'(FAULT_ADDR));
    assign q_eff = ram_q ^ {31'd0, flip};
    assign exp_v = rd_exp_inv ? inv : bg;
    assign mism  = (q_eff != exp_v);

    // next element / background / pass bookkeeping at the end of an element
    logic [2:0]  n_elem;
    logic        n_bg, n_end, pass_end;
    always_comb begin
        n_elem = elem + 3'd1;
        n_bg = bgsel;
        pass_end = 1'b0;
        if (elem == 3'd5) begin
            n_elem = 3'd0;
            n_bg = !bgsel;
            pass_end = bgsel;
        end
    end
    assign n_end = pass_end && (completed + 16'd1 == total);

    always_ff @(posedge clk) begin
        if (rst) begin
            st <= S_IDLE; busy <= 1'b0; done <= 1'b0; completed <= '0;
            errs <= '0; first_err <= 32'hFFFFFFFF;
            bgsel <= 1'b0; elem <= '0; m_addr <= '0; fault_used <= 1'b0;
            total <= 16'd1;
        end else begin
            if (start) begin
                busy <= 1'b1; done <= 1'b0; completed <= '0;
                errs <= '0; first_err <= 32'hFFFFFFFF;
                bgsel <= 1'b0; elem <= '0; m_addr <= '0; fault_used <= 1'b0;
                total <= (passes_cfg == 16'd0) ? 16'd1 : passes_cfg;
                st <= S_ACT;
            end else begin
                case (st)
                    S_IDLE: ;
                    S_ACT: st <= S_CHK;   // element 0 writes in this state; reads latch ram_q
                    S_CHK: begin
                        // ram_q holds RAM[m_addr]; a write (if any) is issued combinationally now
                        if (has_rd) begin
                            if (flip) fault_used <= 1'b1;
                            if (mism) begin
                                errs <= errs + 32'd1;
                                if (first_err == 32'hFFFFFFFF) first_err <= {22'd0, m_addr};
                            end
                        end
                        if (last_addr) begin
                            elem <= n_elem; bgsel <= n_bg;
                            if (pass_end) begin
                                completed <= completed + 16'd1;
                                fault_used <= 1'b0;
                            end
                            if (n_end) begin
                                busy <= 1'b0; done <= 1'b1; st <= S_IDLE;
                            end else begin
                                m_addr <= (n_elem >= 3'd3) ? 10'd1023 : 10'd0;
                                st <= S_ACT;
                            end
                        end else begin
                            m_addr <= down ? m_addr - 10'd1 : m_addr + 10'd1;
                            st <= S_ACT;
                        end
                    end
                    default: st <= S_IDLE;
                endcase
            end
        end
    end

    assign led = {done, busy};
endmodule
