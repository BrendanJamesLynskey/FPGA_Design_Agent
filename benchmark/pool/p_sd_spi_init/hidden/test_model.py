from model import Model, expect, leds, ocr_word


def test_v2_sdhc_needs_three_tries():
    e = expect({"v2": True, "sdhc": True, "tries_needed": 3}, 6)
    assert e["cmds"] == [(0, 0), (8, 0x1AA), (55, 0), (41, 0x40000000), (55, 0), (41, 0x40000000), (55, 0), (41, 0x40000000), (58, 0)]
    assert e["state"] == 5 and e["type"] == 3 and e["tries"] == 3 and e["ocr"] == 0xC0FF8000 and leds(e) == 0x135


def test_v1_and_standard_capacity():
    e = expect({"v2": False, "tries_needed": 2}, 6)
    assert e["type"] == 1 and e["ocr"] == 0 and e["tries"] == 2 and (58, 0) not in e["cmds"] and e["cmds"][-1] == (41, 0)
    e = expect({"v2": True, "sdhc": False, "tries_needed": 1}, 6)
    assert e["type"] == 2 and e["ocr"] == ocr_word({"sdhc": False}) == 0x80FF8000


def test_failures():
    assert expect({"present": False}, 6)["err"] == 1 and expect({"cmd0_r1": 0x00}, 6)["state"] == 6
    e = expect({"v2": True, "tries_needed": 99}, 6)
    assert e["err"] == 3 and e["tries"] == 6 and e["state"] == 6 and leds(e) == 0x206
    m = Model(6)
    assert m.read(0) == 0
    m.run({"v2": True})
    assert m.read(0) == 5 and m.read(1) == 3
