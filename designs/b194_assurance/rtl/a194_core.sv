// a194_core.sv: the development design for brief 194 (assurance switch): a burst sequencer, a 512 x 64 FIFO and an accumulating checksum.
// start with len = N: the core accepts N 64-bit words on the slave stream, passes them through the FIFO to the master stream and adds each
// handed-out word into checksum. done pulses for one clock when all N words have left. Not a held-out task.
// AXI4-Stream handshakes (valid never waits for ready; the payload is stable while valid is high and ready low).
// Parameters: ECC 0/1/2 (a194_fifo), PAR 1 = even parity bit across the output register, SAFE/TMR/WD (a194_ctrl).
// Reset: aresetn, active low at the stream ports (AXI), synchronised inside by the user; used synchronously.
`ifdef A194_FI
`define A194_FIW(name, width) wire [width-1:0] name = '0;
`else
`define A194_FIW(name, width) localparam logic [width-1:0] name = '0;
`endif
module a194_core #(
    parameter int ECC = 0,
    parameter int PAR = 0,
    parameter int SAFE = 0,
    parameter int TMR = 0,
    parameter int WD = 0
) (
    input  logic        aclk,
    input  logic        aresetn,
    input  logic        start,
    input  logic [15:0] len,
    input  logic [63:0] s_axis_tdata,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    output logic [63:0] m_axis_tdata,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic        busy,
    output logic        done,
    output logic [63:0] checksum,
    output logic        err_corr,      // sticky: ECC corrected a bit
    output logic        err_det,       // sticky: uncorrectable ECC error or bus parity error
    output logic        fsm_fault,
    output logic        wd_fault,
    output logic        tmr_fault,
    input  logic        dbg_inj_s,     // test inputs: ECC = 2 error injection at write (UG473)
    input  logic        dbg_inj_d
);
    `A194_FIW(fi_bus, 65)       // simulation hook: XOR into the output register (bit 64 is the parity bit)
    wire rst = !aresetn;

    logic        run, drained, accept, consume, full, empty, rd_vld, sbit, dbit, pop;
    logic [63:0] rd_data, bus_q;
    logic        bus_v, par_q;

    assign accept        = s_axis_tvalid && s_axis_tready;
    assign s_axis_tready = run && !full;

    a194_fifo #(.ECC(ECC)) u_fifo (
        .clk(aclk), .rst(rst), .wr_en(accept), .wr_data(s_axis_tdata), .rd_en(pop), .rd_data(rd_data), .rd_vld(rd_vld),
        .full(full), .empty(empty), .sbit(sbit), .dbit(dbit), .inj_s(dbg_inj_s), .inj_d(dbg_inj_d));

    assign pop     = !empty && !rd_vld && (!bus_v || m_axis_tready);
    assign consume = bus_v && m_axis_tready;
    assign drained = empty && !rd_vld && !bus_v;

    always_ff @(posedge aclk) begin
        if (rst) begin
            bus_v <= 1'b0;
        end else if (rd_vld) begin
            bus_v <= 1'b1;
        end else if (consume) begin
            bus_v <= 1'b0;
        end
        bus_q <= (rd_vld ? rd_data : bus_q) ^ fi_bus[63:0];
        par_q <= (rd_vld ? ^rd_data : par_q) ^ fi_bus[64];
    end
    assign m_axis_tdata  = bus_q;
    assign m_axis_tvalid = bus_v;

    wire par_bad = (PAR != 0) && bus_v && ((^bus_q) != par_q);

    always_ff @(posedge aclk) begin
        if (rst || start) checksum <= '0;
        else if (consume) checksum <= checksum + bus_q;
        if (rst) begin
            err_corr <= 1'b0;
            err_det  <= 1'b0;
        end else begin
            if (sbit) err_corr <= 1'b1;
            if (dbit || par_bad) err_det <= 1'b1;
        end
    end

    a194_ctrl #(.SAFE(SAFE), .TMR(TMR), .WD(WD)) u_ctrl (
        .clk(aclk), .rst(rst), .start(start), .len(len), .progress(accept || consume), .accept(accept), .drained(drained),
        .run(run), .busy(busy), .done(done), .fsm_fault(fsm_fault), .wd_fault(wd_fault), .tmr_fault(tmr_fault), .state_o());
endmodule
