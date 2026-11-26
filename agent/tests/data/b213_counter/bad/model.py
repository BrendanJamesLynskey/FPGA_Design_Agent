"""Reference model of rg_counter (brief 213 fixture): cycle exact, the model API contract."""


class Model:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.q, self.wrap, self.i = 0, 0, {"en": 0, "load": 0, "d": 0}

    def step(self, inputs=None) -> dict:
        self.i.update(inputs or {})
        en, load, d = self.i["en"], self.i["load"], self.i["d"]
        self.wrap = int(bool(en) and not load and self.q == 0xFF)
        if load:
            self.q = d & 0xFF
        elif en:
            self.q = (self.q + 1) & 0xFF
        return {"q": self.q, "wrap": self.wrap}
