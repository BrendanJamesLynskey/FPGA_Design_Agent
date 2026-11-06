"""P13-5 reference model: the Hough accumulator of the reference picture (numpy; bit-exact with the course exercise p13l08_hough)."""
import numpy as np


def line_image(w, h, lines):
    """Edge pixels (0/1) of lines given as (theta_deg, rho): points with x cos t + y sin t = rho, drawn by rounding along the longer axis."""
    img = np.zeros((h, w), np.uint8)
    for th, rho in lines:
        c, s = np.cos(np.radians(th)), np.sin(np.radians(th))
        if abs(s) >= abs(c):
            for x in range(w):
                y = int(round((rho - x * c) / s))
                if 0 <= y < h:
                    img[y, x] = 1
        else:
            for y in range(h):
                x = int(round((rho - y * s) / c))
                if 0 <= x < w:
                    img[y, x] = 1
    return img

NT, NR, ROFF = 16, 96, 48
CT = [int(round(128 * np.cos(k * np.pi / NT))) for k in range(NT)]
ST = [int(round(128 * np.sin(k * np.pi / NT))) for k in range(NT)]
LINES = [(0, 10), (90, 20), (45, 28), (135, 4)]


def points():
    img = line_image(32, 32, LINES)
    return [(int(x), int(y)) for y, x in np.argwhere(img)]


def accumulate(pts):
    acc = np.zeros((NT, NR), np.int64)
    for x, y in pts:
        for k in range(NT):
            rho = ((x * CT[k] + y * ST[k] + 64) >> 7) + ROFF
            if 0 <= rho < NR:
                acc[k, rho] += 1
    return acc


def reference_output():
    return {"acc": accumulate(points()).tolist()}


if __name__ == "__main__":
    print("cos", CT, "sin", ST)


# ---- benchmark wrapper: the shell register map (from spec.yaml) ----
DESIGN_ID = 0x484F5547          # "HOUG"
PT, CLEAR, RD_SEL, RD_CNT, STATUS = 0x00, 0x01, 0x02, 0x03, 0x04


def pts_of(lines):
    img = line_image(32, 32, lines)
    return [(int(x), int(y)) for y, x in np.argwhere(img)]


def bench_pictures():
    """(name, points): one diagonal line, one vertical line, and the four-line picture of the course."""
    return [("diagonal", pts_of([(45, 28)])), ("vertical", pts_of([(0, 20)])), ("four_lines", points())]


def read_bins(acc):
    """The bins the bench reads back: every bin with a count of at least 5 (the peaks), and a fixed sample of 40 other bins."""
    peaks = [(k, r) for k in range(NT) for r in range(NR) if acc[k][r] >= 5]
    other = [(k, r) for k in range(NT) for r in range(NR) if acc[k][r] < 5][::37][:40]
    return peaks + other
