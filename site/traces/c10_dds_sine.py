"""DDS: the model's sample list for one frequency word, with the phase accumulator and table address beside it."""

FW_INDEX = 0          # which of the model's test frequency words
N = 48


def trace(m):
    fw = m.FWS[FW_INDEX]
    out = m.samples(fw, N)
    lut = m.lut()
    mask = (1 << m.AW) - 1
    acc = [(k * fw) & mask for k in range(N)]
    addr = [a >> (m.AW - m.LA) for a in acc]
    assert [lut[a] for a in addr] == out, "phase and address must reproduce the model's samples"
    amp = 2 ** (m.OW - 1) - 1
    cap = [f"Sample {k}: phase {acc[k]:#08x}, top {m.LA} bits address table entry {addr[k]}, output {out[k]}."
           for k in range(N)]
    return {
        "stimulus": f"Frequency word {fw:#08x} added to a {m.AW}-bit phase every clock; the top {m.LA} bits pick one of "
                    f"{2 ** m.LA} sine-table entries, {m.OW}-bit output. The first {N} samples.",
        "unit": "sample", "x": list(range(N)),
        "signals": [
            {"name": "phase", "kind": "bus", "radix": "hex", "width": m.AW, "v": acc},
            {"name": "table address", "kind": "bus", "radix": "dec", "v": addr},
            {"name": "out", "kind": "wave", "lo": -amp, "hi": amp, "v": out},
        ],
        "captions": cap,
        "hero": {"aw": m.AW, "la": m.LA, "amp": amp, "fw": fw},
    }
