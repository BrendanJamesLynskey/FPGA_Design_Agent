"""Tiny CNN: the model's eight pictures, one step each, with the four scores and the shape picked."""

NAMES = ["horizontal bar", "vertical bar", "box", "cross"]


def trace(m):
    ref = m.reference_output()["images"]
    x, sc, cls, let, cap = [], [[] for _ in range(4)], [], [], []
    for e in ref:
        k = e["image"]
        x.append(k)
        for j in range(4):
            sc[j].append(int(e["logits"][j]))
        cls.append(int(e["digit"])); let.append(e["uart"].strip())
        scores = ", ".join(f"{j}: {e['logits'][j]}" for j in range(4))
        cap.append(f"Picture {k}: the scores are {scores}. The biggest is class {e['digit']} ({NAMES[e['digit']]}), so the board shows {e['digit']} and sends the letter {e['uart'].strip()}.")
    return {
        "stimulus": f"The {len(ref)} pictures of 12 by 12 pixels from the data file, each run through the model's integer network (two convolution layers, a pooling step and a final layer).",
        "unit": "picture", "x": x,
        "signals": [
            {"name": "score 0", "kind": "bus", "radix": "dec", "v": sc[0]},
            {"name": "score 1", "kind": "bus", "radix": "dec", "v": sc[1]},
            {"name": "score 2", "kind": "bus", "radix": "dec", "v": sc[2]},
            {"name": "score 3", "kind": "bus", "radix": "dec", "v": sc[3]},
            {"name": "class (digit)", "kind": "bus", "radix": "dec", "v": cls},
            {"name": "UART letter", "kind": "text", "v": let},
        ],
        "captions": cap,
    }
