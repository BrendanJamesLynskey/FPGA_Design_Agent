"""NCO and mixer: 32 samples of a tone at the oscillator frequency, taken part-way into the model's first run."""

RUN, START, N = 0, 300, 32


def trace(m):
    r = m.stimulus()[RUN]
    fw, xs = r["fw"], r["x"][START:START + N]
    out = m.mix(xs, fw)
    acc = 0
    x, idx, i_o, q_o, cap = [], [], [], [], []
    for n in range(N):
        k = acc >> (m.AW - m.LA)
        s, c = m.LUT[k], m.LUT[(k + 2 ** (m.LA - 2)) % 2 ** m.LA]
        x.append(n); idx.append(k); i_o.append(int(out[n][0])); q_o.append(int(out[n][1]))
        cap.append(f"Sample {n}: x = {xs[n]}, table index {k} (sine {s}, cosine {c}), so i_out = {out[n][0]} and q_out = {out[n][1]}.")
        acc = (acc + fw) % 2 ** m.AW
    return {
        "stimulus": f"Frequency word {fw:#06x}. The {N} samples are the tone part of the model's first run (its samples {START} to {START + N - 1}), "
                    f"fed to the mixer with the oscillator phase starting at 0.",
        "unit": "sample", "x": x,
        "signals": [
            {"name": "x", "kind": "wave", "lo": -2048, "hi": 2047, "v": [int(v) for v in xs]},
            {"name": "table index", "kind": "bus", "radix": "dec", "width": m.LA, "v": idx},
            {"name": "i_out", "kind": "wave", "lo": -2048, "hi": 2047, "v": i_o},
            {"name": "q_out", "kind": "wave", "lo": -2048, "hi": 2047, "v": q_o},
        ],
        "captions": cap,
    }
