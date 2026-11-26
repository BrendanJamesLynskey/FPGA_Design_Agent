(* pipe_reg in Hardcaml (brief 171): the same five slice kinds as ip_lib/pipe_reg/rtl/pipe_reg_slice.sv, written with
   the Always DSL so each register's next-state reads like the SystemVerilog's always_ff. A circuit is fixed at one
   (W, N, MODE, TLAST_EN, TKEEP_EN, TUSER_W) point: Hardcaml generates Verilog with no parameters, so gen.ml emits one
   module per point plus a parameterised wrapper named pipe_reg (see gen.ml). *)
open Hardcaml
open Signal

type config =
  { w : int
  ; n : int
  ; mode : int (* 0 FWD, 1 SKID, 2 FULL, 3 HALF, 4 COMB: same numbers as the SV *)
  ; tlast : bool
  ; tkeep : bool
  ; tuser_w : int
  }

let validate c =
  if c.w < 1 || c.w > 1024 then failwith "W must be in 1..1024";
  if c.n < 0 || c.n > 16 then failwith "N must be in 0..16";
  if c.mode < 0 || c.mode > 4 then failwith "MODE must be in 0..4";
  if c.tkeep && c.w mod 8 <> 0 then failwith "TKEEP_EN needs W a multiple of 8";
  if c.tuser_w < 0 || c.tuser_w > 64 then failwith "TUSER_W must be in 0..64"
;;

let name c =
  Printf.sprintf
    "pipe_reg_hc_w%d_n%d_m%d_%d%d%d"
    c.w c.n c.mode (Bool.to_int c.tlast) (Bool.to_int c.tkeep) c.tuser_w
;;

(* A slice: takes the upstream valid and data and the downstream ready; returns upstream ready, downstream valid and
   downstream data. [spec] has the synchronous clear (reset, active high inside, as the SV); [spec_nc] has none (data
   registers are not reset). *)
type slice = { s_ready : Signal.t; m_valid : Signal.t; m_data : Signal.t }

let reg_nc spec_nc ~w = Always.Variable.reg spec_nc ~width:w

(* name a register after the SV signal it mirrors, prefixed with its slice (g0_m_valid, ...), so the generated Verilog
   and the timing reports show readable names *)
let nm pfx s (v : Always.Variable.t) = ignore (v.value -- (pfx ^ s) : Signal.t)

(* MODE 4 COMB: one entry, s_ready = !m_valid || m_ready (combinational from the sink), full throughput. *)
let slice_comb ~pfx ~spec ~spec_nc ~w ~s_valid ~s_data ~m_ready =
  let m_valid = Always.Variable.reg spec ~width:1 in
  let m_data = reg_nc spec_nc ~w in
  let s_ready = ~:(m_valid.value) |: m_ready in
  nm pfx "m_valid" m_valid;
  nm pfx "m_data" m_data;
  Always.(
    compile
      [ when_ s_ready [ m_valid <-- s_valid ]
      ; when_ (s_ready &: s_valid) [ m_data <-- s_data ]
      ]);
  { s_ready; m_valid = m_valid.value; m_data = m_data.value }
;;

(* MODE 3 HALF: one entry, s_ready a flop, one beat per two clocks. *)
let slice_half ~pfx ~spec ~spec_nc ~w ~s_valid ~s_data ~m_ready =
  let m_valid = Always.Variable.reg spec ~width:1 in
  let s_ready = Always.Variable.reg spec ~width:1 in
  let m_data = reg_nc spec_nc ~w in
  let v_next = Always.Variable.wire ~default:m_valid.value in
  nm pfx "m_valid" m_valid;
  nm pfx "s_ready" s_ready;
  nm pfx "m_data" m_data;
  Always.(
    compile
      [ if_
          (s_ready.value &: s_valid)
          [ v_next <--. 1 ]
          [ when_ (m_valid.value &: m_ready) [ v_next <--. 0 ] ]
      ; m_valid <-- v_next.value
      ; s_ready <-- ~:(v_next.value)
      ; when_ (s_ready.value &: s_valid) [ m_data <-- s_data ]
      ]);
  { s_ready = s_ready.value; m_valid = m_valid.value; m_data = m_data.value }
;;

(* MODE 1 SKID: output register plus a side register, s_ready a flop, full throughput. *)
let slice_skid ~pfx ~spec ~spec_nc ~w ~s_valid ~s_data ~m_ready =
  let m_valid = Always.Variable.reg spec ~width:1 in
  let t_valid = Always.Variable.reg spec ~width:1 in
  let s_ready = Always.Variable.reg spec ~width:1 in
  let m_data = reg_nc spec_nc ~w in
  let t_data = reg_nc spec_nc ~w in
  (* s_ready in the next clock: low only when the side register is, or is about to be, occupied *)
  let s_ready_next =
    m_ready |: (~:(t_valid.value) &: (~:(m_valid.value) |: ~:s_valid))
  in
  let straight = m_ready |: ~:(m_valid.value) in
  nm pfx "m_valid" m_valid;
  nm pfx "t_valid" t_valid;
  nm pfx "s_ready" s_ready;
  nm pfx "m_data" m_data;
  nm pfx "t_data" t_data;
  Always.(
    compile
      [ s_ready <-- s_ready_next
      ; if_
          s_ready.value
          [ if_ straight [ m_valid <-- s_valid ] [ t_valid <-- s_valid ] ]
          [ when_ m_ready [ m_valid <-- t_valid.value; t_valid <--. 0 ] ]
      ; if_
          s_ready.value
          [ if_ straight [ m_data <-- s_data ] [ t_data <-- s_data ] ]
          [ when_ m_ready [ m_data <-- t_data.value ] ]
      ]);
  { s_ready = s_ready.value; m_valid = m_valid.value; m_data = m_data.value }
;;

(* MODE 2 FULL: two entries (ping-pong), valid and ready both flops, full throughput. *)
let slice_full ~pfx ~spec ~spec_nc ~w ~s_valid ~s_data ~m_ready =
  let e0 = reg_nc spec_nc ~w in
  let e1 = reg_nc spec_nc ~w in
  let wp = Always.Variable.reg spec ~width:1 in
  let rp = Always.Variable.reg spec ~width:1 in
  let cnt = Always.Variable.reg spec ~width:2 in
  let m_valid = Always.Variable.reg spec ~width:1 in
  let s_ready = Always.Variable.reg spec ~width:1 in
  let push = s_valid &: s_ready.value in
  let pop = m_valid.value &: m_ready in
  let cnt_next =
    mux2 (push &: ~:pop) (cnt.value +:. 1) (mux2 (~:push &: pop) (cnt.value -:. 1) cnt.value)
  in
  nm pfx "e0" e0;
  nm pfx "e1" e1;
  nm pfx "wp" wp;
  nm pfx "rp" rp;
  nm pfx "cnt" cnt;
  nm pfx "m_valid" m_valid;
  nm pfx "s_ready" s_ready;
  Always.(
    compile
      [ cnt <-- cnt_next
      ; m_valid <-- (cnt_next <>:. 0)
      ; s_ready <-- (cnt_next <>:. 2)
      ; when_ push [ wp <-- ~:(wp.value) ]
      ; when_ pop [ rp <-- ~:(rp.value) ]
      ; when_ push [ if_ wp.value [ e1 <-- s_data ] [ e0 <-- s_data ] ]
      ]);
  { s_ready = s_ready.value
  ; m_valid = m_valid.value
  ; m_data = mux2 rp.value e1.value e0.value
  }
;;

(* MODE 0 FWD: NS stages sharing one enable; s_ready combinational from m_ready, no side storage. *)
let chain_fwd ~spec ~spec_nc ~w ~ns ~s_valid ~s_data ~m_ready =
  let v = Array.init ns (fun _ -> Always.Variable.reg spec ~width:1) in
  let d = Array.init ns (fun _ -> reg_nc spec_nc ~w) in
  let en = m_ready |: ~:(v.(ns - 1).value) in
  Array.iteri (fun i v -> nm (Printf.sprintf "g%d_" i) "m_valid" v) v;
  Array.iteri (fun i v -> nm (Printf.sprintf "g%d_" i) "m_data" v) d;
  let steps =
    List.init ns (fun i ->
      let vin = if i = 0 then s_valid else v.(i - 1).value in
      let din = if i = 0 then s_data else d.(i - 1).value in
      Always.[ when_ en [ v.(i) <-- vin; d.(i) <-- din ] ])
  in
  Always.(compile (List.concat steps));
  { s_ready = en; m_valid = v.(ns - 1).value; m_data = d.(ns - 1).value }
;;

(* The N-slice chain. link i is the interface between slice i-1 and slice i; link 0 is the input, link N the output. *)
let chain c ~spec ~spec_nc ~s_valid ~s_data ~m_ready =
  if c.n = 0
  then { s_ready = m_ready; m_valid = s_valid; m_data = s_data } (* a wire *)
  else if c.mode = 0
  then chain_fwd ~spec ~spec_nc ~w:(width s_data) ~ns:c.n ~s_valid ~s_data ~m_ready
  else (
    let w = width s_data in
    let kind =
      match c.mode with
      | 1 -> slice_skid
      | 2 -> slice_full
      | 3 -> slice_half
      | _ -> slice_comb
    in
    (* ready flows right to left: wires break the loop *)
    let lr = Array.init (c.n + 1) (fun i -> if i = c.n then m_ready else wire 1) in
    let rec go i v d =
      if i = c.n
      then v, d
      else (
        let s = kind ~pfx:(Printf.sprintf "g%d_" i) ~spec ~spec_nc ~w ~s_valid:v ~s_data:d ~m_ready:lr.(i + 1) in
        lr.(i) <== s.s_ready;
        go (i + 1) s.m_valid s.m_data)
    in
    let mv, md = go 0 s_valid s_data in
    { s_ready = lr.(0); m_valid = mv; m_data = md })
;;

(* The circuit: the AXI4-Stream ports of pipe_reg (a sideband that is off has no port here: the wrapper ties it).
   The carried signals move as one packed word {tuser, tkeep, tlast, tdata}, as in the SV. *)
let create ?(formal = false) c =
  validate c;
  let aclk = input "aclk" 1 in
  let aresetn = input "aresetn" 1 in
  let s_valid = input "s_axis_tvalid" 1 in
  let m_ready = input "m_axis_tready" 1 in
  let kw = c.w / 8 in
  let ins =
    [ input "s_axis_tdata" c.w ]
    @ (if c.tlast then [ input "s_axis_tlast" 1 ] else [])
    @ (if c.tkeep then [ input "s_axis_tkeep" kw ] else [])
    @ if c.tuser_w > 0 then [ input "s_axis_tuser" c.tuser_w ] else []
  in
  let packed = concat_lsb ins in
  let rst = ~:aresetn -- "rst" in
  let spec = Reg_spec.create ~clock:aclk ~clear:rst () in
  let spec_nc = Reg_spec.create ~clock:aclk () in
  let r = chain c ~spec ~spec_nc ~s_valid ~s_data:packed ~m_ready in
  let sel lo wd = select r.m_data (lo + wd - 1) lo in
  let outs =
    [ output "s_axis_tready" r.s_ready
    ; output "m_axis_tvalid" r.m_valid
    ; output "m_axis_tdata" (sel 0 c.w)
    ]
  in
  (* formal builds add the ghost counters the SV carries under `ifdef FORMAL: beats accepted at the input and delivered at
     the output, W bits wrapping (formal/formal_pipe.sv reads them as f_in_o and f_out_o) *)
  let outs =
    if formal
    then (
      let push = s_valid &: r.s_ready in
      let pop = r.m_valid &: m_ready in
      let cnt en = reg_fb spec ~enable:en ~width:c.w ~f:(fun q -> q +:. 1) in
      outs @ [ output "f_in_o" (cnt push -- "f_in"); output "f_out_o" (cnt pop -- "f_out") ])
    else outs
  in
  let lo = c.w in
  let outs, lo =
    if c.tlast then outs @ [ output "m_axis_tlast" (sel lo 1) ], lo + 1 else outs, lo
  in
  let outs, lo =
    if c.tkeep then outs @ [ output "m_axis_tkeep" (sel lo kw) ], lo + kw else outs, lo
  in
  let outs =
    if c.tuser_w > 0 then outs @ [ output "m_axis_tuser" (sel lo c.tuser_w) ] else outs
  in
  Circuit.create_exn ~name:(name c) outs
;;
