"""Reference model for P9-2 (1280x720@60 colour bars): the geometry and the colours the pins must show. Standalone: python only."""
BARS = [0xFFF, 0xFF0, 0x0FF, 0x0F0, 0xF0F, 0xF00, 0x00F, 0x000]
H_ACT, H_FP, H_SYNC, H_BP = 1280, 110, 40, 220
V_ACT, V_FP, V_SYNC, V_BP = 720, 5, 5, 20
LINE = H_ACT + H_FP + H_SYNC + H_BP          # 1650 pixel clocks
FRAME_LINES = V_ACT + V_FP + V_SYNC + V_BP   # 750 lines
BAR_W = 160


def colour_at(x: int, y: int) -> int:
    """12-bit colour (R in [11:8]) of picture position (x, y); anything outside the 1280 x 720 area is black."""
    if 0 <= x < H_ACT and 0 <= y < V_ACT:
        return BARS[x // BAR_W]
    return 0


# ---- benchmark wrapper: the shell register map (from spec.yaml) ----
DESIGN_ID = 0x56373230          # "V720"
STATUS = 0x00
