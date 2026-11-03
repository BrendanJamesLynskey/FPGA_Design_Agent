from model import Model


def test_on_time_and_gap():
    m = Model(96)
    m.latch(255)
    assert m.on == 95 and m.read(1) == 95
    m.latch(0)
    assert sum(m.waveform()) == 0
    m.latch(64)
    assert m.on == 24


def test_inphase_and_staggered_waveforms():
    m = Model(96)
    m.latch(128)                                    # on = 48
    w = m.waveform()
    assert all(v in (0, 7) for v in w) and sum(1 for v in w if v) == 48
    m.latch(128 | 0x100)
    w = m.waveform()
    ch = [[(v >> k) & 1 for v in w] for k in range(3)]
    assert ch[0].index(1) == 0 and ch[1].index(1) == 32 and ch[2][63] == 0 and ch[2][64] == 1 and ch[2][0] == 1
    assert all(sum(c) == 48 for c in ch)


def test_wrap_of_a_late_channel():
    m = Model(96)
    m.latch(200 | 0x100)                            # on = 75; channel 2 starts at 64 and wraps
    w = m.waveform()
    assert (w[95] >> 2) & 1 == 1 and (w[0] >> 2) & 1 == 1 and (w[42] >> 2) & 1 == 1 and (w[43] >> 2) & 1 == 0
