"""VGA sprite: the model's frame-by-frame bounce, then the sprite placed partly and fully off the screen."""

START = (620, 455)
FRAMES_A = 14
START_B = (3, 2)
FRAMES_B = 12
PLACE = [632, 636, 640, 1000]
SPRITE_COLOR, BG_COLOR = 0xF80, 0x004


def lit(m, md):
    """Sprite-coloured pixels of the 16 x 16 area that fall on the visible screen."""
    return sum(1 for r in range(16) for c in range(16) if md.pixel(md.x + c, md.y + r) == md.sprite_color)


def trace(m):
    md = m.Model()
    for r in range(16):
        md.write(m.ROW0 + r, 0xFFFF)                    # a solid 16 x 16 block
    md.write(m.SPRITE_COLOR, SPRITE_COLOR)
    md.write(m.BG_COLOR, BG_COLOR)
    md.write(m.X, START[0]); md.write(m.Y, START[1])
    md.write(m.CTRL, m.EN | m.BOUNCE)
    x, fr, px, py, dx, dy, vis, cap = [], [], [], [], [], [], [], []

    def snap(note):
        i = len(x)
        x.append(i); fr.append(md.read(m.FRAME)); px.append(md.read(m.X)); py.append(md.read(m.Y))
        c = md.read(m.CTRL)
        dx.append(c >> 2 & 1); dy.append(c >> 3 & 1); vis.append(lit(m, md))
        cap.append(f"Step {i}: {note} Position ({px[-1]}, {py[-1]}), {vis[-1]} sprite pixels on screen.")

    snap(f"Start with the sprite at ({START[0]}, {START[1]}), bounce on, moving right and down.")
    for _ in range(FRAMES_A):
        ox, oy, c0 = md.x, md.y, md.ctrl
        md.frame_wrap()
        turned = [n for n, b in (("right edge", (md.ctrl ^ c0) & m.DX_NEG and md.x < ox), ("left edge", (md.ctrl ^ c0) & m.DX_NEG and md.x > ox),
                                 ("bottom edge", (md.ctrl ^ c0) & m.DY_NEG and md.y < oy), ("top edge", (md.ctrl ^ c0) & m.DY_NEG and md.y > oy)) if b]
        snap(f"Frame {md.read(m.FRAME)} ends and the sprite moves one pixel each way." + (" It turns round at the " + " and the ".join(turned) + "." if turned else ""))
    md.write(m.X, START_B[0]); md.write(m.Y, START_B[1])
    md.write(m.CTRL, m.EN | m.BOUNCE | m.DX_NEG | m.DY_NEG)
    snap(f"The sprite is placed at ({START_B[0]}, {START_B[1]}), moving left and up.")
    for _ in range(FRAMES_B):
        ox, oy, c0 = md.x, md.y, md.ctrl
        md.frame_wrap()
        turned = [n for n, b in (("right edge", (md.ctrl ^ c0) & m.DX_NEG and md.x < ox), ("left edge", (md.ctrl ^ c0) & m.DX_NEG and md.x > ox),
                                 ("bottom edge", (md.ctrl ^ c0) & m.DY_NEG and md.y < oy), ("top edge", (md.ctrl ^ c0) & m.DY_NEG and md.y > oy)) if b]
        snap(f"Frame {md.read(m.FRAME)} ends and the sprite moves one pixel each way." + (" It turns round at the " + " and the ".join(turned) + "." if turned else ""))
    md.write(m.CTRL, m.EN)
    for v in PLACE:
        md.write(m.X, v)
        snap(f"Bounce is off and X is set to {v}" + ("; only part of the block is inside the 640 columns, the rest is clipped." if lit(m, md) else "; none of the block is inside the screen."))
    return {
        "stimulus": f"A solid 16 x 16 block is placed at ({START[0]}, {START[1]}) with bounce on and followed for {FRAMES_A} frames, then restarted at ({START_B[0]}, {START_B[1]}) "
                    f"moving up and left for {FRAMES_B} frames. Finally bounce is turned off and X is set to {', '.join(str(v) for v in PLACE)}.",
        "unit": "step", "x": x,
        "signals": [
            {"name": "FRAME", "kind": "bus", "radix": "dec", "v": fr},
            {"name": "X", "kind": "wave", "v": px, "lo": 0, "hi": 1023},
            {"name": "Y", "kind": "wave", "v": py, "lo": 0, "hi": 479},
            {"name": "DX_NEG (1 = left)", "kind": "bit", "v": dx},
            {"name": "DY_NEG (1 = up)", "kind": "bit", "v": dy},
            {"name": "sprite pixels on screen", "kind": "wave", "v": vis, "lo": 0, "hi": 256},
        ],
        "captions": cap,
    }
