"""P13-2 reference model: the biggest-blob list (numpy, flood fill; equal to the course exercise on every frame) and the bench pictures. Standalone copy of the course model."""
import numpy as np

W, H, N = 40, 30, 8
NPIX = W * H


def label_ref(m):
    """Golden 4-connected blob list by flood fill: (area, sum_x, sum_y, xmin, xmax, ymin, ymax), sorted."""
    h, w = m.shape
    seen = np.zeros_like(m, bool)
    out = []
    for y0 in range(h):
        for x0 in range(w):
            if m[y0, x0] and not seen[y0, x0]:
                st, pts = [(x0, y0)], []
                seen[y0, x0] = True
                while st:
                    x, y = st.pop()
                    pts.append((x, y))
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        a, b = x + dx, y + dy
                        if 0 <= a < w and 0 <= b < h and m[b, a] and not seen[b, a]:
                            seen[b, a] = True
                            st.append((a, b))
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                out.append((len(pts), sum(xs), sum(ys), min(xs), max(xs), min(ys), max(ys)))
    return sorted(out)


def frames():
    out = []
    for t in range(N):
        m = np.zeros((H, W), np.uint8)
        m[4:7 + t, 3 + 2 * t:11 + 2 * t] = 1                    # a rectangle, 8 wide, that grows downward and moves right (area 24, 32, 40, ... 80)
        m[18:24, 22:24] = 1; m[18:24, 28:30] = 1; m[24:26, 22:30] = 1    # a U of area 40: two arms that join only at the bottom
        m[8 + t:11 + t, 24:27] = 1                              # a 3 x 3 block moving down toward the U
        m[14 + t // 2, 33 + t // 4] = 1                         # a stray pixel
        m[7 + t:9 + t, 11 + 2 * t:13 + 2 * t] = 1               # touches the rectangle's bottom right corner diagonally only (not 4-connected)
        out.append(m)
    return out


def biggest(m):
    blobs = label_ref(m)
    best = max(blobs, key=lambda b: (b[0], -b[5], -b[3]))        # area; ties: the blob with the smaller top row, then the smaller left edge
    area, sx, sy = best[0], best[1], best[2]
    return {"area": area, "cx": sx // area, "cy": sy // area}


def extra_pictures():
    """Pictures the bench adds to the eight of the course: a single pixel in the last corner, a comb and a ring that need several merges, and three equal blobs (the top-left one wins)."""
    empty = np.zeros((H, W), np.uint8)
    empty[29, 39] = 1
    merge = np.zeros((H, W), np.uint8)
    merge[2:12, 2] = 1; merge[2:12, 6] = 1; merge[2:12, 10] = 1; merge[11, 2:11] = 1      # a comb: three teeth joined at the bottom (several equivalences)
    merge[16:28, 20] = 1; merge[16, 20:36] = 1; merge[16:28, 35] = 1; merge[27, 20:36] = 1  # a ring (a closed loop)
    tie = np.zeros((H, W), np.uint8)
    tie[5:8, 5:11] = 1; tie[5:8, 25:31] = 1; tie[20:23, 15:21] = 1                          # three blobs of 18 pixels: the top-left one (smaller top row, smaller left edge) wins
    return [empty, merge, tie]


def bench_pictures():
    return [(f"animation picture {i}", f) for i, f in enumerate(frames())] + [(n, p) for n, p in zip(("single pixel in the corner", "comb and ring", "three-way tie"), extra_pictures())]


def pack_words(m):
    flat = [int(v) for v in m.flatten()] + [0] * 16
    return [sum(flat[32 * i + k] << k for k in range(32)) for i in range(38)]


# ---- benchmark wrapper: the shell register map (from spec.yaml) ----
DESIGN_ID = 0x424C4F42          # "BLOB"
PTR, DATA, GO, STATUS, AREA, CX, CY = range(7)
