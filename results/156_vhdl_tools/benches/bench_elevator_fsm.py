"""t1_elevator_fsm (entity elevator_fsm, FLOOR_CYCLES=6, DOOR_CYCLES=10): one call at a time; after each call the car must be on that floor,
idle, with nothing pending, and MOVES must have grown by the floors travelled (state-level check of the golden model's rules; the
model's cycle-exact call scheduling is not used because the call synchroniser delay is not part of the spec)."""
import cocotb
from common import Trace, Window, ops, rng, start_clock
from loadmodel import load_model

M = load_model("t1_elevator_fsm")


@cocotb.test()
async def elevator_calls(dut):
    await start_clock(dut)
    w = Window(dut)
    w.idle()
    dut.sw_async.value = 0
    tr = Trace("elevator_fsm", dut.clk, {"led": dut.led, "rdata": dut.win_rdata})
    await w.reset()
    tr.enabled = True
    r = rng()
    floor, moves = 0, 0
    got = await w.read(M.FLOOR)
    assert got == 0, f"floor after reset {got}"
    for i in range(ops()):
        f = r.randrange(4)
        dut.sw_async.value = 1 << f
        await w.cycles(4)
        dut.sw_async.value = 0
        await w.cycles(4 * 6 + 10 + 40)
        assert await w.read(M.FLOOR) == f, f"call {i}: car not on floor {f}"
        assert await w.read(M.PENDING) == 0, f"call {i}: pending not empty"
        assert await w.read(M.STATE) == M.IDLE, f"call {i}: not idle"
        moves = (moves + abs(f - floor)) & 0xFFFF
        assert await w.read(M.MOVES) == moves, f"call {i}: moves"
        floor = f
    tr.finish()
