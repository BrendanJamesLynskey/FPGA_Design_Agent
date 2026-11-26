(* Expect tests for the Hardcaml pipe_reg (brief 171): cyclesim of each slice kind, a directed trace printed beat by beat.
   A line is: clock, then the source's valid/data, the sink's ready, then what the block shows after the clock edge.
   These are not the sign-off: the sign-off is the existing cocotb bench on the generated Verilog (ip_lib/pipe_reg/tb). *)
open! Core
open Hardcaml
open Pipe_reg_hc

let cfg ?(w = 8) ?(n = 1) mode = { w; n; mode; tlast = false; tkeep = false; tuser_w = 0 }

(* drive [stim] (valid, ready) one clock each; print the ports before the edge, as a testbench samples them *)
let trace c stim =
  let circuit = create c in
  let sim = Cyclesim.create circuit in
  let port n = Cyclesim.in_port sim n in
  let out n = Cyclesim.out_port ~clock_edge:Before sim n in
  (port "aresetn") := Bits.gnd;
  (port "s_axis_tvalid") := Bits.gnd;
  Cyclesim.cycle sim;
  (port "aresetn") := Bits.vdd;
  printf "clk  s_valid s_data m_ready | s_ready m_valid m_data\n";
  let next = ref 1 in
  List.iteri stim ~f:(fun i (v, r) ->
    (* the source numbers its beats 1, 2, 3 ... and holds a beat until the block accepts it (AXI4-Stream) *)
    let d = !next in
    (port "s_axis_tvalid") := Bits.of_bool v;
    (port "s_axis_tdata") := Bits.of_int ~width:c.w d;
    (port "m_axis_tready") := Bits.of_bool r;
    Cyclesim.cycle sim;
    printf
      "%3d  %7b %6d %7b | %7b %7b %6d\n"
      i v d r
      (Bits.to_bool !(out "s_axis_tready"))
      (Bits.to_bool !(out "m_axis_tvalid"))
      (Bits.to_int !(out "m_axis_tdata"));
    if v && Bits.to_bool !(out "s_axis_tready") then incr next)
;;

(* a sink that stalls for four clocks while the source keeps offering *)
let stall_stim = List.init 12 ~f:(fun i -> true, not (i >= 4 && i < 8))

let%expect_test "skid, N=1: the sink stalls for four clocks" =
  trace (cfg 1) stall_stim;
  [%expect {|
    clk  s_valid s_data m_ready | s_ready m_valid m_data
      0     true      1    true |   false   false      0
      1     true      1    true |    true   false      0
      2     true      2    true |    true    true      1
      3     true      3    true |    true    true      2
      4     true      4   false |    true    true      3
      5     true      5   false |   false    true      3
      6     true      5   false |   false    true      3
      7     true      5   false |   false    true      3
      8     true      5    true |   false    true      3
      9     true      5    true |    true    true      4
     10     true      6    true |    true    true      5
     11     true      7    true |    true    true      6
    |}]
;;

let%expect_test "full, N=1" =
  trace (cfg 2) stall_stim;
  [%expect {|
    clk  s_valid s_data m_ready | s_ready m_valid m_data
      0     true      1    true |   false   false      0
      1     true      1    true |    true   false      0
      2     true      2    true |    true    true      1
      3     true      3    true |    true    true      2
      4     true      4   false |    true    true      3
      5     true      5   false |   false    true      3
      6     true      5   false |   false    true      3
      7     true      5   false |   false    true      3
      8     true      5    true |   false    true      3
      9     true      5    true |    true    true      4
     10     true      6    true |    true    true      5
     11     true      7    true |    true    true      6
    |}]
;;

let%expect_test "half, N=1: one beat per two clocks" =
  trace (cfg 3) stall_stim;
  [%expect {|
    clk  s_valid s_data m_ready | s_ready m_valid m_data
      0     true      1    true |   false   false      0
      1     true      1    true |    true   false      0
      2     true      2    true |   false    true      1
      3     true      2    true |    true   false      1
      4     true      3   false |   false    true      2
      5     true      3   false |   false    true      2
      6     true      3   false |   false    true      2
      7     true      3   false |   false    true      2
      8     true      3    true |   false    true      2
      9     true      3    true |    true   false      2
     10     true      4    true |   false    true      3
     11     true      4    true |    true   false      3
    |}]
;;

let%expect_test "comb, N=1: ready follows the sink at once" =
  trace (cfg 4) stall_stim;
  [%expect {|
    clk  s_valid s_data m_ready | s_ready m_valid m_data
      0     true      1    true |    true   false      0
      1     true      2    true |    true    true      1
      2     true      3    true |    true    true      2
      3     true      4    true |    true    true      3
      4     true      5   false |   false    true      4
      5     true      5   false |   false    true      4
      6     true      5   false |   false    true      4
      7     true      5   false |   false    true      4
      8     true      5    true |    true    true      4
      9     true      6    true |    true    true      5
     10     true      7    true |    true    true      6
     11     true      8    true |    true    true      7
    |}]
;;

let%expect_test "fwd, N=2: two stages, one shared enable" =
  trace (cfg ~n:2 0) stall_stim;
  [%expect {|
    clk  s_valid s_data m_ready | s_ready m_valid m_data
      0     true      1    true |    true   false      0
      1     true      2    true |    true   false      0
      2     true      3    true |    true    true      1
      3     true      4    true |    true    true      2
      4     true      5   false |   false    true      3
      5     true      5   false |   false    true      3
      6     true      5   false |   false    true      3
      7     true      5   false |   false    true      3
      8     true      5    true |    true    true      3
      9     true      6    true |    true    true      4
     10     true      7    true |    true    true      5
     11     true      8    true |    true    true      6
    |}]
;;

(* Scoreboard: random source and sink for 3000 clocks per point; every beat accepted leaves once, in order, none invented;
   m_valid never drops while the sink has not taken the beat (AXI4-Stream); and the first beat out appears N clocks after
   it went in when the chain is empty (the declared latency). *)
let scoreboard c ~seed =
  let rng = Random.State.make [| seed |] in
  let sim = Cyclesim.create (create c) in
  let port n = Cyclesim.in_port sim n in
  let out n = Cyclesim.out_port ~clock_edge:Before sim n in
  (port "aresetn") := Bits.gnd;
  (port "s_axis_tvalid") := Bits.gnd;
  Cyclesim.cycle sim;
  (port "aresetn") := Bits.vdd;
  Cyclesim.cycle sim;
  let sent = Queue.create () in
  let next = ref 0 in
  let errors = ref 0 in
  let prev_stall = ref None in
  let src_hold = ref None in
  for _ = 1 to 3000 do
    let v, d =
      match !src_hold with
      | Some x -> true, x (* AXI: an offered beat stays offered until accepted *)
      | None ->
        if Random.State.int rng 3 > 0 then true, !next land ((1 lsl c.w) - 1) else false, 0
    in
    let r = Random.State.int rng 4 > 0 in
    (port "s_axis_tvalid") := Bits.of_bool v;
    (port "s_axis_tdata") := Bits.of_int ~width:c.w d;
    (port "m_axis_tready") := Bits.of_bool r;
    Cyclesim.cycle sim;
    let s_ready = Bits.to_bool !(out "s_axis_tready") in
    let m_valid = Bits.to_bool !(out "m_axis_tvalid") in
    let m_data = Bits.to_int !(out "m_axis_tdata") in
    (match !prev_stall with
     | Some (dq : int) -> if not (m_valid && m_data = dq) then incr errors
     | None -> ());
    if m_valid && r
    then (
      match Queue.dequeue sent with
      | Some e -> if e <> m_data then incr errors
      | None -> incr errors);
    prev_stall := if m_valid && not r then Some m_data else None;
    if v && s_ready
    then (
      Queue.enqueue sent d;
      src_hold := None;
      incr next)
    else if v
    then src_hold := Some d
    else src_hold := None
  done;
  !errors, !next
;;

let%expect_test "scoreboard: order, no loss, output holds while stalled" =
  List.iter [ 0; 1; 2; 3; 4 ] ~f:(fun mode ->
    List.iter [ 1; 2; 5 ] ~f:(fun n ->
      let errors, accepted = scoreboard (cfg ~n mode) ~seed:(mode * 10 + n) in
      printf "mode %d N %d: errors %d, beats accepted > 500: %b\n" mode n errors (accepted > 500)));
  [%expect {|
    mode 0 N 1: errors 0, beats accepted > 500: true
    mode 0 N 2: errors 0, beats accepted > 500: true
    mode 0 N 5: errors 0, beats accepted > 500: true
    mode 1 N 1: errors 0, beats accepted > 500: true
    mode 1 N 2: errors 0, beats accepted > 500: true
    mode 1 N 5: errors 0, beats accepted > 500: true
    mode 2 N 1: errors 0, beats accepted > 500: true
    mode 2 N 2: errors 0, beats accepted > 500: true
    mode 2 N 5: errors 0, beats accepted > 500: true
    mode 3 N 1: errors 0, beats accepted > 500: true
    mode 3 N 2: errors 0, beats accepted > 500: true
    mode 3 N 5: errors 0, beats accepted > 500: true
    mode 4 N 1: errors 0, beats accepted > 500: true
    mode 4 N 2: errors 0, beats accepted > 500: true
    mode 4 N 5: errors 0, beats accepted > 500: true
    |}]
;;
