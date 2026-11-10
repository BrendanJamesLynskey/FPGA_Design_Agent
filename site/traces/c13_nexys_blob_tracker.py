"""Blob finder: the model's eleven bench pictures, one step each; the biggest object's area and middle point."""


def trace(m):
    pics = m.bench_pictures()
    x, nb, area, cx, cy, cap = [], [], [], [], [], []
    for i, (name, img) in enumerate(pics):
        n = len(m.label_ref(img))
        b = m.biggest(img)
        x.append(i); nb.append(n); area.append(b["area"]); cx.append(b["cx"]); cy.append(b["cy"])
        cap.append(f"Picture {i} ({name}): {n} object{'s' if n != 1 else ''} found. The biggest has {b['area']} pixel{'s' if b['area'] != 1 else ''} and its middle point is x = {b['cx']}, y = {b['cy']}.")
    return {
        "stimulus": f"{len(pics)} pictures of {m.W} by {m.H} pixels (rectangles, a U-shape, stray pixels, a comb, a ring and a three-way tie), each given to the model's flood-fill labeller.",
        "unit": "picture", "x": x,
        "signals": [
            {"name": "objects found", "kind": "bus", "radix": "dec", "v": nb},
            {"name": "AREA", "kind": "bus", "radix": "dec", "v": area},
            {"name": "CX", "kind": "bus", "radix": "dec", "v": cx},
            {"name": "CY", "kind": "bus", "radix": "dec", "v": cy},
        ],
        "captions": cap,
    }
