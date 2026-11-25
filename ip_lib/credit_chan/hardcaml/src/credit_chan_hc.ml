(* credit_chan in Hardcaml (brief 171): the credit-based link of ip_lib/credit_chan/rtl/credit_chan.sv: a sender-side credit
   counter, LF forward pipeline stages, a CREDITS-deep receive FIFO (circular buffer, asynchronous read) with write and read
   pointers, and LB backward stages that return a credit when the sink takes a beat. One circuit per
   (W, CREDITS, LF, LB, TLAST_EN, TKEEP_EN, TUSER_W) point; gen.ml adds the parameterised wrapper. *)
open Hardcaml
open Signal

type config =
  { w : int
  ; credits : int
  ; lf : int
  ; lb : int
  ; tlast : bool
  ; tkeep : bool
  ; tuser_w : int
  }

let validate c =
  if c.w < 1 || c.w > 1024 then failwith "W must be in 1..1024";
  if c.credits < 1 || c.credits > 1024 then failwith "CREDITS must be in 1..1024";
  if c.lf < 0 || c.lf > 8 then failwith "LF must be in 0..8";
  if c.lb < 0 || c.lb > 8 then failwith "LB must be in 0..8";
  if c.tkeep && c.w mod 8 <> 0 then failwith "TKEEP_EN needs W a multiple of 8";
  if c.tuser_w < 0 || c.tuser_w > 64 then failwith "TUSER_W must be in 0..64"
;;

let name c =
  Printf.sprintf
    "credit_chan_hc_w%d_c%d_f%d_b%d_%d%d%d"
    c.w c.credits c.lf c.lb (Bool.to_int c.tlast) (Bool.to_int c.tkeep) c.tuser_w
;;

let nm s (v : Always.Variable.t) = ignore (v.value -- s : Signal.t)

(* returns (s_ready, m_valid, m_data, send, pop) of the packed-word core *)
let core c ~spec ~spec_nc ~clock ~s_valid ~s_data ~m_ready =
  let w = width s_data in
  let cw = num_bits_to_represent c.credits in
  let pw = Int.max 1 (num_bits_to_represent (c.credits - 1)) in
  (* sender side: credits left, s_ready a flop that is high while credits_next <> 0 *)
  let credits = Always.Variable.reg (Reg_spec.override spec ~clear_to:(of_int ~width:cw c.credits)) ~width:cw in
  let s_ready = Always.Variable.reg spec ~width:1 in
  let m_valid = Always.Variable.reg spec ~width:1 in
  nm "credits" credits;
  nm "s_ready_q" s_ready;
  nm "m_valid_q" m_valid;
  let send = s_valid &: s_ready.value in
  let pop = m_valid.value &: m_ready in
  (* backward path: LB flops after pop; LB = 0 is the combinational pop itself *)
  let credit_in =
    List.fold_left (fun prev i ->
      let q = Always.Variable.reg spec ~width:1 in
      nm (Printf.sprintf "back%d_credit" (i + 1)) q;
      Always.(compile [ q <-- prev ]);
      q.value) pop (List.init c.lb Fun.id)
  in
  let credits_next =
    mux2
      (send &: ~:credit_in)
      (credits.value -:. 1)
      (mux2 (~:send &: credit_in) (credits.value +:. 1) credits.value)
  in
  Always.(compile [ credits <-- credits_next; s_ready <-- (credits_next <>:. 0) ]);
  (* forward path: LF stages (valid cleared by reset, data not) *)
  let f_valid, f_data =
    List.fold_left (fun (v, d) i ->
      let vq = Always.Variable.reg spec ~width:1 in
      let dq = Always.Variable.reg spec_nc ~width:w in
      nm (Printf.sprintf "fwd%d_valid" (i + 1)) vq;
      nm (Printf.sprintf "fwd%d_data" (i + 1)) dq;
      Always.(compile [ vq <-- v; dq <-- d ]);
      vq.value, dq.value) (send, s_data) (List.init c.lf Fun.id)
  in
  (* receive FIFO: CREDITS entries, circular, asynchronous read at rp *)
  let wp = Always.Variable.reg spec ~width:pw in
  let rp = Always.Variable.reg spec ~width:pw in
  let cnt = Always.Variable.reg spec ~width:cw in
  nm "wp" wp;
  nm "rp" rp;
  nm "cnt" cnt;
  let cnt_next =
    mux2
      (f_valid &: ~:pop)
      (cnt.value +:. 1)
      (mux2 (~:f_valid &: pop) (cnt.value -:. 1) cnt.value)
  in
  let wrap p = mux2 (p ==:. c.credits - 1) (zero pw) (p +:. 1) in
  Always.(
    compile
      [ cnt <-- cnt_next
      ; m_valid <-- (cnt_next <>:. 0)
      ; when_ f_valid [ wp <-- wrap wp.value ]
      ; when_ pop [ rp <-- wrap rp.value ]
      ]);
  let mem =
    multiport_memory
      c.credits
      ~write_ports:
        [| { write_clock = clock
           ; write_enable = f_valid
           ; write_address = wp.value
           ; write_data = f_data
           }
        |]
      ~read_addresses:[| rp.value |]
  in
  s_ready.value, m_valid.value, mem.(0) -- "fifo_head", send, pop
;;

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
  let s_ready, m_valid, m_data, send, pop =
    core c ~spec ~spec_nc ~clock:aclk ~s_valid ~s_data:packed ~m_ready
  in
  let sel lo wd = select m_data (lo + wd - 1) lo in
  let outs =
    [ output "s_axis_tready" s_ready
    ; output "m_axis_tvalid" m_valid
    ; output "m_axis_tdata" (sel 0 c.w)
    ]
  in
  (* formal builds: the ghost counters of the SV's `ifdef FORMAL (beats accepted and delivered, W bits wrapping) *)
  let outs =
    if formal
    then (
      let cnt en = reg_fb spec ~enable:en ~width:c.w ~f:(fun q -> q +:. 1) in
      outs @ [ output "f_in_o" (cnt send -- "f_in"); output "f_out_o" (cnt pop -- "f_out") ])
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
