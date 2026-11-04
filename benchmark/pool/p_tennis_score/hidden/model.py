"""Golden model of p_tennis_score, written from spec.yaml alone."""

from __future__ import annotations

PTS_A, PTS_B, GAMES_A, GAMES_B = range(4)
DESIGN_ID = 0x54454E4E
TEXT = ("00", "15", "30", "40")
GLYPHS = {"0": "abcdef", "1": "bc", "3": "abcdg", "4": "bcfg", "5": "acdfg", "A": "abcefg", "d": "bcdeg", "-": "g"}


def seg_pins(ch: str) -> int:
    return sum(0 if s in GLYPHS[ch] else 1 << i for i, s in enumerate("abcdefg"))


class Model:
    def __init__(self) -> None:
        self.pts = [0, 0]
        self.adv: int | None = None
        self.winner: int | None = None
        self.games = [0, 0]

    def point(self, p: int) -> None:
        if self.winner is not None:
            return
        q = 1 - p
        if self.adv is not None:
            if self.adv == p:
                self._win(p)
            else:
                self.adv = None
        elif self.pts[p] == 3 and self.pts[q] == 3:
            self.adv = p
        elif self.pts[p] == 3:
            self._win(p)
        else:
            self.pts[p] += 1

    def _win(self, p: int) -> None:
        self.winner = p
        self.games[p] = min(15, self.games[p] + 1)

    def new_game(self) -> None:
        self.pts, self.adv, self.winner = [0, 0], None, None

    def code(self, p: int) -> int:
        if self.winner == p:
            return 5
        if self.adv == p:
            return 4
        return self.pts[p]

    def read(self, off: int) -> int:
        if off == PTS_A:
            return self.code(0)
        if off == PTS_B:
            return self.code(1)
        if off == GAMES_A:
            return self.games[0]
        if off == GAMES_B:
            return self.games[1]
        return 0

    def write(self, off: int, v: int) -> None:
        if off == GAMES_A:
            self.games = [0, 0]

    def leds(self) -> int:
        return self.games[0] << 12 | self.games[1] << 8 | int(self.winner is not None)

    def player_text(self, p: int) -> str:
        if self.winner == p:
            return "--"
        if self.adv == p:
            return "Ad"
        return TEXT[self.pts[p]]

    def display(self) -> dict[int, int]:
        a, b = self.player_text(0), self.player_text(1)
        return {7: seg_pins(a[0]), 6: seg_pins(a[1]), 1: seg_pins(b[0]), 0: seg_pins(b[1])}
