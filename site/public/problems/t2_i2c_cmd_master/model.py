"""Golden model of t2_i2c_cmd_master, written from spec.yaml alone (never from any RTL).

The master's registers, and the bus transactions each command must produce, as the log entries of
benchmark/lib/i2c_devices.I2cBus. The slaves' answers come from reference copies of the same data-sheet device
models the bench attaches to the bus (they are the environment, not the design)."""

from __future__ import annotations

from benchmark.lib.i2c_devices import I2cDevice

DESIGN_ID = 0x4932434D
CMD, STATUS, RXDATA, INFO = 0, 1, 2, 3
OP_START, OP_WRITE, OP_READ, OP_STOP = 1, 2, 3, 4
BUSY, NACK, OWNED = 1, 2, 4


def cmd_word(op: int, data: int = 0, rnack: int = 0) -> int:
    return op | (data & 0xFF) << 8 | (rnack & 1) << 16


class Model:
    def __init__(self, devices: list[I2cDevice], quarter: int) -> None:
        self.devices = devices
        self.quarter = quarter
        self.owned = False
        self.nack = False
        self.rxdata = 0
        self.expect_addr = False
        self.sel: I2cDevice | None = None
        self.reading = False
        self.pending = 0
        self.log: list[tuple] = []

    def command(self, word: int) -> None:
        op, data, rnack = word & 7, (word >> 8) & 0xFF, (word >> 16) & 1
        if op == OP_START:
            self.log.append(("Sr",) if self.owned else ("S",))
            self.owned, self.expect_addr, self.sel = True, True, None
            for d in self.devices:
                d.start()
        elif op == OP_WRITE and self.owned:
            if self.expect_addr:
                a, rw = data >> 1, data & 1
                dev = next((d for d in self.devices if d.addr == a), None)
                ack = dev is not None and dev.address(rw)
                self.log.append(("A", a, rw, ack))
                self.sel = dev if ack else None
                self.reading = bool(rw)
                self.expect_addr = False
                if self.sel is not None and self.reading:
                    self.pending = self.sel.read()
            elif self.sel is not None and not self.reading:
                ack = self.sel.write(data)
                self.log.append(("W", data, ack))
                if not ack:
                    self.sel = None
            else:
                ack = False                       # nobody listening: SDA stays high in the ACK bit
            self.nack = not ack
        elif op == OP_READ and self.owned:
            if self.sel is not None and self.reading:
                byte = self.pending
                mack = not rnack
                self.log.append(("R", byte, mack))
                self.sel.master_ack(mack)
                if mack:
                    self.pending = self.sel.read()
                else:
                    self.sel = None
                self.rxdata = byte
            else:
                self.rxdata = 0xFF                # released SDA reads as ones
        elif op == OP_STOP and self.owned:
            self.log.append(("P",))
            self.owned, self.sel = False, None
            for d in self.devices:
                d.stop()

    def read(self, off: int) -> int:
        if off == STATUS:
            return (NACK if self.nack else 0) | (OWNED if self.owned else 0)
        if off == RXDATA:
            return self.rxdata
        if off == INFO:
            return self.quarter & 0xFFFF
        return 0
