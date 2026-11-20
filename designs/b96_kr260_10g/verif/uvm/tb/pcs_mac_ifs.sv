`timescale 1ns/1ps
// pcs_mac_ifs.sv: the interfaces of the b96 PCS and MAC UVM bench (brief 112). One clock for both halves (the 161.13 MHz user clock, 6.206 ns).
//   sys_if   clock, resets, the mode switch (loopback through the TX chain, or the line agent drives the receiver's input) and the initial bit offset
//   usr_if   the user side of mac64_tx: a frame source offering 64-bit words (s_*), plus the MAC's own strobes
//   xg_if    the XGMII-style word streams: MAC output, PCS input (with the direct-injection mux), the PCS pause strobe adv
//   line_if  the GT side: the transmit PCS's TXDATA, the channel's input and output (RXDATA), the fault-injection controls of the channel
//   rx_if    the receive PCS outputs (lock, decoded words, event pulses) and the receive MAC outputs (words, end-of-frame verdict, abort)

interface sys_if (input logic clk);
  logic        rst_tx = 1'b1;
  logic        rst_rx_sys = 1'b1;
  logic        line_mode = 1'b0;
  int unsigned init_off = 0;
  // assert both resets for `cycles` clocks with the chosen mode and initial bit offset, then release them one nanosecond after an edge
  task automatic apply_reset(input bit lmode, input int unsigned off, input int cycles = 6);
    line_mode = lmode; init_off = off;
    rst_tx = 1'b1; rst_rx_sys = 1'b1;
    repeat (cycles) @(posedge clk);
    #1;
    rst_tx = 1'b0; rst_rx_sys = 1'b0;
  endtask
endinterface

interface usr_if (input logic clk);
  logic        s_valid = 0, s_last = 0, s_poison = 0;
  logic [63:0] s_data = '0;
  logic [2:0]  s_nb1 = '0;
  logic        s_ready, sop, eop, underrun, adv;
  clocking cb @(posedge clk);
    default input #1step output #1;
    inout  s_valid, s_data, s_last, s_nb1, s_poison;     // driven by the source driver, sampled by the monitor
    input  s_ready, sop, eop, underrun, adv;
  endclocking
endinterface

interface xg_if (input logic clk);
  logic        direct = 0;
  logic [63:0] dx_d = '0;
  logic [7:0]  dx_c = '0;
  logic [63:0] xm_d, p_d;        // MAC output; PCS input (after the mux)
  logic [7:0]  xm_c, p_c;
  logic        adv, rst_tx;
  clocking cb @(posedge clk);
    default input #1step output #1;
    output direct, dx_d, dx_c;
    input  xm_d, xm_c, p_d, p_c, adv, rst_tx;
  endclocking
endinterface

interface line_if (input logic clk);
  logic [63:0] gt_tx_d;                 // transmit PCS output
  logic [63:0] gt_rx_d;                 // the channel's output: the receive PCS's input
  logic [63:0] drv_word = '0;           // the line agent's own stream (line mode)
  logic        drv_valid = 0, drv_first = 0;
  logic [63:0] flip_mask = '0;          // XORed onto the next word entering the channel
  logic        hdr_load = 0;            // load hdr_cnt blocks of corrupted sync header (both bits forced to 0)
  logic [15:0] hdr_cnt = '0;
  logic [7:0]  hdr_skip = '0;          // good blocks between corrupted ones
  logic        slip_ins = 0, slip_del = 0;   // insert / delete one bit in the stream
  logic        rst_rx_req = 0;
  logic        rst_rx;                  // the receive-side reset as seen by the receiver
  clocking cb @(posedge clk);
    default input #1step output #1;
    output drv_word, drv_valid, drv_first, flip_mask, hdr_load, hdr_cnt, hdr_skip, slip_ins, slip_del, rst_rx_req;
    input  gt_tx_d, gt_rx_d, rst_rx;
  endclocking
endinterface

interface rx_if (input logic clk);
  logic        rst_rx;
  logic        lock, x_v, x_os, ev_sh_err, ev_type_err, ev_os, ev_slip, ev_loss, ev_lock;
  logic [63:0] x_d;
  logic [7:0]  x_c;
  logic        m_v, m_sof, m_end, m_fcs_ok, m_err, rx_sop;
  logic [63:0] m_d;
  logic [3:0]  m_nb;
  logic [15:0] m_len;
  clocking cb @(posedge clk);
    default input #1step;
    input rst_rx, lock, x_v, x_os, ev_sh_err, ev_type_err, ev_os, ev_slip, ev_loss, ev_lock, x_d, x_c,
          m_v, m_sof, m_end, m_fcs_ok, m_err, rx_sop, m_d, m_nb, m_len;
  endclocking
endinterface
