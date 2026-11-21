// pcs_mac_items.sv: sequence items and monitor transactions of the b96 PCS and MAC UVM bench (brief 112).

typedef enum { PAT_RANDOM, PAT_ZEROS, PAT_ONES, PAT_COUNT, PAT_ALT } pat_e;

// one Ethernet frame offered to mac64_tx: payload bytes (the MAC adds preamble, FCS, terminate and the gap), the poison flag (a deliberately bad
// FCS), and the idle clocks the driver leaves before the first word
class frame_item extends uvm_sequence_item;
  `uvm_object_utils(frame_item)
  rand int unsigned len;            // bytes before the FCS; the MAC needs at least 60
  rand pat_e        pat;
  rand bit          poison;
  rand bit          noise_poison;   // drive s_poison randomly on the words that are not the last (the MAC must ignore it)
  rand int unsigned gap;            // idle clocks before the frame
  bit [7:0]         payload [];
  constraint c_len  { soft len inside {[60:1514]}; }
  constraint c_gap  { soft gap inside {[0:40]}; }
  constraint c_pat  { soft pat dist { PAT_RANDOM := 8, PAT_ZEROS := 1, PAT_ONES := 1, PAT_COUNT := 1, PAT_ALT := 1 }; }
  constraint c_pois { soft poison dist { 0 := 9, 1 := 1 }; }
  function new(string name = "frame_item"); super.new(name); endfunction
  function void post_randomize();
    fill();
  endfunction
  function void fill();
    payload = new[len];
    foreach (payload[i]) begin
      case (pat)
        PAT_ZEROS: payload[i] = 8'h00;
        PAT_ONES:  payload[i] = 8'hFF;
        PAT_COUNT: payload[i] = 8'(i);
        PAT_ALT:   payload[i] = (i % 2) ? 8'h55 : 8'hAA;
        default:   payload[i] = 8'($urandom());
      endcase
    end
  endfunction
  function pcs_ref_pkg::bq_t as_queue();
    pcs_ref_pkg::bq_t q; foreach (payload[i]) q.push_back(payload[i]); return q;
  endfunction
  function string convert2string();
    return $sformatf("frame len=%0d pat=%s poison=%0b gap=%0d", len, pat.name(), poison, gap);
  endfunction
endclass

// XGMII words offered directly to pcs_tx (the MAC is bypassed by the mux): lane-4 frames, error characters, ordered sets, malformed words
class xg_item extends uvm_sequence_item;
  `uvm_object_utils(xg_item)
  pcs_ref_pkg::xwq_t words;
  string             tag;
  function new(string name = "xg_item"); super.new(name); endfunction
  function string convert2string(); return $sformatf("xg %s: %0d words", tag, words.size()); endfunction
endclass

// the line agent's work items
typedef enum { L_BLOCKS, L_FLIP, L_HDR, L_SLIP_INS, L_SLIP_DEL, L_WAIT, L_RXRESET, L_BER } line_kind_e;

class line_item extends uvm_sequence_item;
  `uvm_object_utils(line_item)
  line_kind_e          kind;
  pcs_ref_pkg::blk_t   blks [$];   // L_BLOCKS: raw 66-bit blocks (line mode only)
  bit [63:0]           mask;       // L_FLIP: XOR onto the next word
  int unsigned         n;          // L_HDR blocks, L_WAIT / L_RXRESET clocks, L_BER ppm per bit
  int unsigned         skip;       // L_HDR: good blocks between corrupted ones
  function new(string name = "line_item"); super.new(name); endfunction
  function string convert2string(); return $sformatf("line %s n=%0d blks=%0d", kind.name(), n, blks.size()); endfunction
endclass

// monitor transactions
class smp_txn extends uvm_object;                 // one clock's sample of a word stream
  longint unsigned cyc;
  bit              rst, adv;
  bit [63:0]       d;
  bit [7:0]        c;
  function new(string name = "smp_txn"); super.new(name); endfunction
endclass

class rxo_txn extends uvm_object;                 // one clock's sample of the receive PCS's outputs
  longint unsigned cyc;
  bit              rst, lock, x_v, x_os, ev_sh_err, ev_type_err, ev_os, ev_slip, ev_loss, ev_lock;
  bit [63:0]       x_d;
  bit [7:0]        x_c;
  function new(string name = "rxo_txn"); super.new(name); endfunction
  function bit [5:0] events(); return {ev_sh_err, ev_type_err, ev_os, ev_slip, ev_loss, ev_lock}; endfunction
endclass

class rxf_txn extends uvm_object;                 // one frame outcome of mac64_rx, assembled by the receive monitor
  longint unsigned cyc;
  bit [7:0]        bytes [$];
  bit              fcs_ok, aborted;
  int              len;
  function new(string name = "rxf_txn"); super.new(name); endfunction
endclass
