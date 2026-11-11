"""Golden model of d24_registered_outputs, written from spec.yaml alone (never from any RTL). One call to step() is one rising clock edge."""

from __future__ import annotations

DESIGN_ID = 0x52474F55          # "RGOU"
BURSTS, ERRS, CLEAR = 0, 1, 2
IN_PINS = ("JA1", "JA2", "JA3", "JA4", "JA7")                       # cmd_valid gnt ack nack rsp_ready
OUT_PINS = ("JB1", "JB2", "JB3", "JB4", "JB7", "JB8", "JB9", "JB10")   # req addr_v valid last rsp_valid rsp_err cmd_ready cmd_ack
ALLOWED_LAGS = {0, 1}            # clocks by which every output may trail the state table (all outputs the same amount)
CMD_ACK_MEALY = False         # cmd_ack = IDLE and cmd_valid (same clock) instead of "LOAD"

IDLE, LOAD, REQ, ADDR, DATA, TURN, WACK, RETRY, RESP, ERR, COOL = range(11)


class Model:
    def __init__(self) -> None:
        self.st, self.n = IDLE, 0           # n counts clocks spent in DATA / WACK / COOL
        self.bursts = self.errs = 0

    def outputs(self, cmd_valid: int) -> tuple[int, ...]:
        s = self.st
        return (int(s in (REQ, ADDR, DATA)), int(s == ADDR), int(s == DATA), int(s == DATA and self.n == 3),
                int(s in (RESP, ERR)), int(s == ERR), int(s == IDLE),
                int(s == IDLE and cmd_valid) if CMD_ACK_MEALY else int(s == LOAD))

    def step(self, cmd_valid: int, gnt: int, ack: int, nack: int, rsp_ready: int) -> tuple[int, ...]:
        """The outputs seen in this clock (state and inputs before the edge), then the edge."""
        out = self.outputs(cmd_valid)
        s, n = self.st, self.n
        if s == IDLE:
            self.st = LOAD if cmd_valid else IDLE
        elif s == LOAD:
            self.st = REQ
        elif s == REQ:
            if gnt:
                self.st = ADDR
        elif s == ADDR:
            self.st, self.n = DATA, 0
        elif s == DATA:
            if n == 3:
                self.st = TURN
            else:
                self.n += 1
        elif s == TURN:
            self.st, self.n = WACK, 0
        elif s == WACK:
            if ack:
                self.st = RESP
            elif nack:
                self.st = RETRY
            elif n == 7:
                self.st = ERR
            else:
                self.n += 1
        elif s == RETRY:
            self.st = REQ
        elif s in (RESP, ERR):
            if rsp_ready:
                if s == RESP:
                    self.bursts = (self.bursts + 1) & 0xFFFF
                else:
                    self.errs = (self.errs + 1) & 0xFFFF
                self.st, self.n = COOL, 0
        elif s == COOL:
            if n == 2:
                self.st = IDLE
            else:
                self.n += 1
        return out

    def clear(self) -> None:
        self.bursts = self.errs = 0
