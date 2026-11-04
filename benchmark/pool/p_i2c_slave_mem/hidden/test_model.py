from model import Model


def write(m, addr, data):
    m.start()
    acks = [m.addr(addr << 1)]
    acks += [m.wbyte(d) for d in data]
    return acks


def read(m, addr, n):
    m.start()
    m.addr(addr << 1 | 1)
    return [m.rbyte() for _ in range(n)]


def test_id_pointer_kept_and_autoincrement():
    m = Model()
    assert read(m, 0x2A, 2) == [0x5C, 0]
    assert write(m, 0x2A, [1, 0x11, 0x22]) == [True, True, True, True]
    assert m.ptr == 3 and m.reg[1:3] == [0x11, 0x22] and m.wrcount == 2
    assert read(m, 0x2A, 3) == [0, 0, 0] and m.ptr == 6
    write(m, 0x2A, [0])
    assert read(m, 0x2A, 10)[1:3] == [0x11, 0x22] and m.view(9) == 0x11 ^ 0x22 and m.view(8) == 2


def test_ro_writes_acked_and_wrap():
    m = Model()
    assert write(m, 0x2A, [0, 1, 2, 3]) == [True] * 5
    assert m.reg[1] == 2 and m.reg[2] == 3 and m.wrcount == 2 and m.view(0) == 0x5C
    write(m, 0x2A, [15])
    assert read(m, 0x2A, 2) == [0, 0x5C] and m.ptr == 1


def test_bad_pointer_and_wrong_address():
    m = Model()
    write(m, 0x2A, [5])
    assert write(m, 0x2A, [16, 7, 7]) == [True, False, False, False] and m.ptr == 5 and m.badptr == 1 and m.reg[5] == 0
    assert write(m, 0x29, [1, 2]) == [False, False, False] and m.matches == 2
    assert read(m, 0x29, 2) == [0xFF, 0xFF]
