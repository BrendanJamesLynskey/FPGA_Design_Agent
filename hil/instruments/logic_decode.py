"""Protocol decode and edge timing from logic-analyser samples (brief 30): UART, SPI, I2C. Pure Python on 0/1 sample
lists, so any capture source (the M2K's 16-channel logic analyser through libm2k, sigrok, the in-FPGA logic_analyser)
can feed it. Tested on synthetic captures (hil/tests/test_30_instruments.py)."""
from __future__ import annotations


def edges(x: list[int], rising: bool = True) -> list[int]:
    """Sample indices where the signal goes 0->1 (rising) or 1->0."""
    a, b = (0, 1) if rising else (1, 0)
    return [i for i in range(1, len(x)) if x[i - 1] == a and x[i] == b]


def edge_delay_ns(x: list[int], y: list[int], fs: float, rising_x: bool = True, rising_y: bool = True) -> list[float]:
    """Delay in ns from each edge of x to the next edge of y (timing between pins)."""
    ex, ey, out = edges(x, rising_x), edges(y, rising_y), []
    for i in ex:
        nxt = next((j for j in ey if j >= i), None)
        if nxt is not None:
            out.append((nxt - i) / fs * 1e9)
    return out


def uart(x: list[int], fs: float, baud: float, bits: int = 8, stop: int = 1) -> list[int]:
    """8N1 (LSB first) bytes of an idle-high line. Returns the decoded values; a frame with a low stop bit is dropped."""
    bit = fs / baud
    out, i, n = [], 0, len(x)
    while i < n:
        if x[i] == 0 and (i == 0 or x[i - 1] == 1):           # start-bit edge
            mid = i + bit * 1.5
            if mid + bit * (bits - 1) + bit * stop >= n:
                break
            v = sum(x[int(mid + bit * k)] << k for k in range(bits))
            if x[int(i + bit * (1 + bits + 0.5))] == 1:
                out.append(v)
            i = int(i + bit * (1 + bits + stop) - bit / 2)
        i += 1
    return out


def spi(clk: list[int], mosi: list[int], miso: list[int], cs: list[int], mode: int = 0, bits: int = 8) -> list[tuple[int, int]]:
    """(mosi word, miso word) per chip-select-low frame, MSB first. mode = CPOL*2 + CPHA."""
    cpol, cpha = mode >> 1, mode & 1
    sample_rising = (cpol == 0) == (cpha == 0)                 # modes 0 and 3 sample on the rising edge
    words, cur_m, cur_s, cnt = [], 0, 0, 0
    for i in range(1, len(clk)):
        if cs[i] == 1:
            cur_m = cur_s = cnt = 0
            continue
        edge = (clk[i - 1] == 0 and clk[i] == 1) if sample_rising else (clk[i - 1] == 1 and clk[i] == 0)
        if edge:
            cur_m, cur_s, cnt = (cur_m << 1) | mosi[i], (cur_s << 1) | miso[i], cnt + 1
            if cnt == bits:
                words.append((cur_m, cur_s))
                cur_m = cur_s = cnt = 0
    return words


def i2c(scl: list[int], sda: list[int]) -> list[dict]:
    """Transactions: {'addr', 'read', 'data': [bytes], 'acks': [bool...]} between START and STOP."""
    txs, cur, bits, nbits = [], None, [], 0
    for i in range(1, len(scl)):
        if scl[i] == 1 and scl[i - 1] == 1 and sda[i - 1] == 1 and sda[i] == 0:      # START (also a repeated one)
            cur, bits = {"addr": None, "read": None, "data": [], "acks": []}, []
            txs.append(cur)
        elif scl[i] == 1 and scl[i - 1] == 1 and sda[i - 1] == 0 and sda[i] == 1:    # STOP
            cur = None
        elif cur is not None and scl[i - 1] == 0 and scl[i] == 1:                    # SCL rising: sample SDA
            bits.append(sda[i])
            if len(bits) == 9:
                byte = sum(b << (7 - k) for k, b in enumerate(bits[:8]))
                if cur["addr"] is None:
                    cur["addr"], cur["read"] = byte >> 1, bool(byte & 1)
                else:
                    cur["data"].append(byte)
                cur["acks"].append(bits[8] == 0)
                bits = []
    return txs
