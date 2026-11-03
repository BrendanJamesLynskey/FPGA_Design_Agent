from model import Model, seg_pins


def score(m, seq):
    for p in seq:
        m.point(p)


def test_plain_game_and_games_count():
    m = Model()
    score(m, [0, 0, 0])
    assert m.read(0) == 3 and m.player_text(0) == "40"
    m.point(0)
    assert m.read(0) == 5 and m.read(2) == 1 and m.winner == 0 and m.leds() == 0x1001
    m.point(1)
    assert m.pts == [3, 0]


def test_deuce_advantage_and_back():
    m = Model()
    score(m, [0, 0, 0, 1, 1, 1])
    assert m.pts == [3, 3] and m.adv is None
    m.point(1)
    assert m.read(1) == 4 and m.player_text(1) == "Ad" and m.player_text(0) == "40"
    m.point(0)
    assert m.adv is None and m.pts == [3, 3]
    score(m, [0, 0])
    assert m.winner == 0 and m.read(0) == 5


def test_new_game_keeps_games_and_display():
    m = Model()
    score(m, [1, 1, 1, 1])
    m.new_game()
    assert m.games == [0, 1] and m.winner is None and m.leds() == 0x0100
    d = m.display()
    assert d == {7: seg_pins("0"), 6: seg_pins("0"), 1: seg_pins("0"), 0: seg_pins("0")}
    score(m, [0, 0, 0, 1, 1, 1, 0])
    d = m.display()
    assert d[7] == seg_pins("A") and d[6] == seg_pins("d") and d[1] == seg_pins("4") and d[0] == seg_pins("0")
    m.write(2, 1)
    assert m.games == [0, 0]
