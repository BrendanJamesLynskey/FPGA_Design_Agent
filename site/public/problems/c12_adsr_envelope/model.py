"""Reference model for P12-1 (linear ADSR envelope): the rules of the spec, tick by tick. Standalone: python only."""
import random


def script(seed=12):
    rng = random.Random(seed)
    s = []

    def note(n_on, n_off, atk, dec, sus, rel):
        s.extend([[1, atk, dec, sus, rel]] * n_on)
        s.extend([[0, atk, dec, sus, rel]] * n_off)

    note(60, 80, 1500, 600, 30000, 900)
    note(10, 70, 4000, 1000, 40000, 700)          # early release during the attack
    note(40, 100, 20000, 300, 0, 5000)            # sustain at 0
    note(15, 6, 60000, 65535, 65535, 65535)       # extreme steps
    for _ in range(18):
        note(rng.randrange(1, 25), rng.randrange(1, 25), rng.randrange(1, 9000), rng.randrange(1, 9000), rng.randrange(65536), rng.randrange(1, 9000))
    s.extend([[1, 100, 50, 20000, 400]] * 20)     # slow attack, interrupted by a re-trigger during release
    s.extend([[0, 100, 50, 20000, 400]] * 5)
    s.extend([[1, 100, 50, 20000, 400]] * 30)
    s.extend([[0, 100, 50, 20000, 400]] * 40)
    return s[:900]


def boundary_script():
    """Levels that land exactly on a limit: release at level == rel_dec, decay at level - sus == dec_dec, attack reaching 65535 exactly,
    sustain level raised above the level during the decay, and a re-trigger from the middle of a release."""
    s = [[0, 0, 0, 0, 0]] * 3
    s += [[1, 1000, 50, 20000, 1000]] * 2 + [[0, 1000, 50, 20000, 1000]] * 3       # level 1000, released with rel = 1000 exactly
    s += [[0, 0, 0, 0, 0]] * 2
    s += [[1, 65535, 535, 65000, 100]] * 4 + [[0, 65535, 535, 65000, 100]] * 3     # attack in one step, decay lands on sus with dec = level - sus exactly
    s += [[1, 30000, 100, 65535, 100]] * 3 + [[1, 5535, 100, 65535, 100]] * 2      # 60000 + 5535 = 65535 exactly
    s += [[0, 5535, 100, 65535, 60000]] * 3 + [[0, 5535, 100, 65535, 4000]] * 3
    s += [[1, 100, 3000, 5000, 100]] * 1 + [[1, 65535, 3000, 5000, 100]] * 2        # decay from the top
    s += [[1, 100, 3000, 5000, 100]] * 3 + [[1, 100, 3000, 60000, 100]] * 3         # sustain raised above the falling level
    s += [[0, 100, 3000, 60000, 7000]] * 2 + [[1, 700, 3000, 60000, 7000]] * 3      # re-trigger in the middle of a release
    s += [[0, 700, 3000, 60000, 65535]] * 3
    return s


def run(sc):
    level, state, gate_d, out = 0, 0, 0, []
    for gate, atk, dec, sus, rel in sc:
        if gate and not gate_d:
            state = 1
        elif not gate and gate_d and state != 0:
            state = 4
        elif state == 1:
            if level + atk >= 65535:
                level, state = 65535, 2
            else:
                level += atk
        elif state == 2:
            if level <= sus:
                state = 3
            elif level - sus <= dec:
                level, state = sus, 3
            else:
                level -= dec
        elif state == 4:
            if level <= rel:
                level, state = 0, 0
            else:
                level -= rel
        gate_d = gate
        out.append([level, state])
    return out


# ---- benchmark wrapper: the shell register map (from spec.yaml) ----
DESIGN_ID = 0x41445352          # "ADSR"
GATE, ATK, DEC, SUS, REL, TICK, LEVEL, STATE, SNAP = range(9)
