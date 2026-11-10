"""P13-1 reference model: the Harris corner list (numpy, bit-exact with the course exercise) and the bench pictures. Standalone copy of the course model."""
import numpy as np

W, H, THRESH = 80, 60, 50_000_000
BOXES = ((12, 10, 30, 26), (50, 32, 68, 50))


def squares(w, h, boxes):
    """Bright rectangles (x0, y0, x1, y1 inclusive, value 220) on a dark background (30)."""
    img = np.full((h, w), 30, np.uint8)
    for x0, y0, x1, y1 in boxes:
        img[y0:y1 + 1, x0:x1 + 1] = 220
    return img


def scene():
    return squares(W, H, BOXES)


def _grad(p, r, c):
    gx = (p[r - 1, c + 1] + 2 * p[r, c + 1] + p[r + 1, c + 1]) - (p[r - 1, c - 1] + 2 * p[r, c - 1] + p[r + 1, c - 1])
    gy = (p[r + 1, c - 1] + 2 * p[r + 1, c] + p[r + 1, c + 1]) - (p[r - 1, c - 1] + 2 * p[r - 1, c] + p[r - 1, c + 1])
    return gx >> 2, gy >> 2


def response_map(img):
    p = np.pad(img.astype(np.int64), 3, mode="edge")
    ix = np.zeros(p.shape, np.int64)
    iy = np.zeros(p.shape, np.int64)
    for r in range(1, p.shape[0] - 1):
        for c in range(1, p.shape[1] - 1):
            ix[r, c], iy[r, c] = _grad(p, r, c)
    R = np.zeros(p.shape, np.int64)
    for r in range(2, p.shape[0] - 2):
        for c in range(2, p.shape[1] - 2):
            a, b = ix[r - 1:r + 2, c - 1:c + 2], iy[r - 1:r + 2, c - 1:c + 2]
            sxx, syy, sxy = int((a * a).sum()), int((b * b).sum()), int((a * b).sum())
            R[r, c] = sxx * syy - sxy * sxy - (((sxx + syy) ** 2) >> 4)
    return R


def corners(img=None):
    img = scene() if img is None else img
    R = response_map(img)
    out = []
    for y in range(H):
        for x in range(W):
            r, c = y + 3, x + 3
            rc = R[r, c]
            strict = all(rc > R[r + dy, c + dx] for dy, dx in ((-1, -1), (-1, 0), (-1, 1), (0, -1)))
            loose = all(rc >= R[r + dy, c + dx] for dy, dx in ((0, 1), (1, -1), (1, 0), (1, 1)))
            if rc > THRESH and strict and loose:
                out.append([x, y])
    return out


def mixed_picture():
    """Strong, weak and border-touching rectangles: a strong box inside, a weak one (contrast 45, below the threshold: no corners), a medium one on the right and bottom edges
    and a strong one on the left and bottom edges (their corners at the picture edge are replicated, not mirrored or zero-padded)."""
    img = np.full((H, W), 30, np.uint8)
    img[4:19, 4:21] = 220
    img[6:23, 30:56] = 75
    img[30:60, 60:80] = 100
    img[36:60, 0:15] = 220
    return img


def bench_pictures():
    return [("the course picture", scene()), ("strong, weak and border rectangles", mixed_picture())]


def pack_words(img):
    flat = [int(v) for v in img.flatten()]
    return [sum(flat[4 * i + k] << (8 * k) for k in range(4)) for i in range(len(flat) // 4)]


def check_corners(got, exp):
    """The course check.py rule: every true corner has a detection within one pixel, no detection is away from every true corner, and no more detections than corners."""
    why = []
    for ex, ey in exp:
        if not any(abs(x - ex) <= 1 and abs(y - ey) <= 1 for x, y in got):
            why.append(f"corner ({ex}, {ey}) not found")
    extra = [(x, y) for x, y in got if all(abs(x - ex) > 1 or abs(y - ey) > 1 for ex, ey in exp)]
    if extra:
        why.append(f"{len(extra)} detections away from every true corner: {extra[:6]}")
    if len(got) > len(exp):
        why.append(f"{len(got)} detections for {len(exp)} corners (one cross per corner expected)")
    return why


# ---- benchmark wrapper: the shell register map (from spec.yaml) ----
DESIGN_ID = 0x48415252          # "HARR"
PTR, DATA, GO, STATUS, COUNT, SEL, CORNER = range(7)
