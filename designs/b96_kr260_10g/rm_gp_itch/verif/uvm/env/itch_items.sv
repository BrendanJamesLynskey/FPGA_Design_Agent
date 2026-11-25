// itch_items.sv: sequence items and the observation records of the ITCH/OUCH UVM bench (brief 170).
import itch_ref_pkg::*;

typedef enum int { IN_FRAME = 0, IN_IDLE = 1 } in_kind_e;
typedef enum int { CF_SET = 0, CF_CMD = 1, CF_RESET = 2, CF_STATS = 3, CF_READY = 4 } cf_kind_e;

// a frame to send (or a number of idle clocks) on the receive side
class in_item extends uvm_sequence_item;
  `uvm_object_utils(in_item)
  in_kind_e kind = IN_FRAME;
  bq_t      data;                 // destination MAC ... payload; the driver adds the 4-byte FCS (wrong when bad_fcs)
  bit       bad_fcs = 0;
  bit       lane4 = 0;            // the start block is in lane 4 of its word
  int       gap_after = 3;        // idle words after the frame
  int       bubble_pct = 0;       // probability, per data word, of a clock with x_v low (the PCS gearbox pause) before it
  int       idle_n = 0;
  function new(string name = "in_item"); super.new(name); endfunction
endclass

class cfg_item extends uvm_sequence_item;
  `uvm_object_utils(cfg_item)
  cf_kind_e kind = CF_SET;
  itch_cfg  c;
  int       cmd_bits = 0;
  function new(string name = "cfg_item"); super.new(name); endfunction
endclass

// observation records
class out_frame_t;
  bq_t data;                      // frame bytes, FCS removed
  bit  fcs_ok;
  int  term_lane, nwords;
  bit  malformed;
  longint unsigned c_start, c_end;
endclass
class cfg_evt_t;
  longint unsigned cyc;
  int   kind;                     // 0 configuration, 1 command, 2 reset
  itch_cfg c;
  int   cmd_bits;
endclass
class stat_evt_t;
  longint unsigned cyc;
  bit [31:0] w [96];
endclass

// XGMII byte-stream parser shared by the input and output monitors: preamble, SFD, data bytes up to the terminate; the CRC verdict is the bench's own (crc32 of itch_ref_pkg)
class xgmii_parser;
  int st = 0;                     // 0 idle, 1 preamble, 2 data
  int pre_left;
  bq_t d;
  bit lane4;
  bit bad;
  longint unsigned c_start;
  int nwords;
  in_frame_t last;
  int term_lane;
  bit last_malformed;
  function void start_frame(int lane, longint unsigned cyc);
    st = 1; pre_left = 7; d.delete(); lane4 = (lane == 4); bad = 0; c_start = cyc; nwords = 0;
  endfunction
  // one byte of the stream; returns 1 when a frame has completed (then `last` holds it)
  function bit push(bit c, byte unsigned b, int lane, longint unsigned cyc);
    case (st)
      0: begin if (c && b == 8'hFB) start_frame(lane, cyc); end
      1: begin
        if (c) begin st = 0; end
        else begin
          pre_left--;
          if (pre_left == 0) begin st = 2; if (b != 8'hD5) bad = 1; end
          else if (b != 8'h55) bad = 1;
        end
      end
      2: begin
        if (!c) d.push_back(b);
        else begin
          st = 0; term_lane = lane;
          last = new();
          last_malformed = bad || (b != 8'hFD) || d.size() < 5;
          if (d.size() >= 5) begin
            bq_t body; bit [31:0] f;
            for (int i = 0; i < d.size() - 4; i++) body.push_back(d[i]);
            f = {d[d.size()-1], d[d.size()-2], d[d.size()-3], d[d.size()-4]};
            last.fcs_ok = (crc32(body) == f);
            last.data = body;
          end
          last.lane4 = lane4; last.c_start = c_start; last.c_end = cyc;
          return 1;
        end
      end
    endcase
    return 0;
  endfunction
endclass
