"""Reference model for P12-3 (PWM audio output stage with the hearing-safety gain register). Standalone: python only."""
GAIN_DEFAULT, GAIN_MAX = 2068, 8192


def steps():
    """Each step: reset first? / gain write (or None) / the sample held afterwards."""
    return [
        {"reset": True, "write": None, "sample": 0},
        {"reset": False, "write": None, "sample": 32767},
        {"reset": False, "write": None, "sample": -32768},
        {"reset": False, "write": 65535, "sample": 32767},
        {"reset": False, "write": None, "sample": -32768},
        {"reset": False, "write": 4000, "sample": 20000},
        {"reset": False, "write": 8192, "sample": 12345},
        {"reset": False, "write": 8193, "sample": 10000},
        {"reset": True, "write": None, "sample": 32767},
    ]


def expected(steps_):
    gain, out = GAIN_DEFAULT, []
    for s in steps_:
        if s["reset"]:
            gain = GAIN_DEFAULT
        if s["write"] is not None:
            gain = min(s["write"], GAIN_MAX)
        so = (s["sample"] * gain) >> 15
        out.append({"sample_out": so, "low_per_period": 1024 - (512 + (so >> 7))})
    return out


# ---- benchmark wrapper: the shell register map (from spec.yaml) ----
DESIGN_ID = 0x5057_4D41          # "PWMA"
SAMPLE, GAIN, SOUT = 0x00, 0x01, 0x02
