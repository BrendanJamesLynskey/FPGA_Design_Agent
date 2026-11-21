import Cksum.Spec
open Cksum
#print axioms rtl_tcp_correct
def ffs (n : Nat) : List (BitVec 16) := List.replicate n 0xFFFF
def chk (n : Nat) : Bool :=
  rtlTcpCsum 0#32 0#32 0#16 0#16 0#32 0#32 0#16 (ffs n) == ~~~ ocSum (tcpWords 0#32 0#32 0#16 0#16 0#32 0#32 0#16 (ffs n))
#eval (List.range 40).map (fun n => (n, chk n))
#eval (rtlTcpCsum 0#32 0#32 0#16 0#16 0#32 0#32 0#16 (ffs 33), ~~~ ocSum (tcpWords 0#32 0#32 0#16 0#16 0#32 0#32 0#16 (ffs 33)))
