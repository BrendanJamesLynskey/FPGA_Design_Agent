"""The block diagram of a chain (brief 19, section 7), drawn from the committed result JSON. Sober monochrome, one file,
light and dark through CSS variables. Blocks: key settings and resources. Links: rate, width, and the measured (and
predicted) SINAD / ENOB at that point. Every number printed comes from `chain_results.json`."""
from __future__ import annotations

from html import escape

W_BLOCK, H_BLOCK = 214, 214
GAP = 92
MARGIN = 28
TOP = 150

CSS = """
:root{--bg:#ffffff;--fg:#111111;--mut:#555555;--line:#111111;--fill:#f4f4f4;--acc:#111111}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0d0d0d;--fg:#eeeeee;--mut:#a5a5a5;--line:#eeeeee;--fill:#1a1a1a;--acc:#eeeeee}}
:root[data-theme="dark"]{--bg:#0d0d0d;--fg:#eeeeee;--mut:#a5a5a5;--line:#eeeeee;--fill:#1a1a1a;--acc:#eeeeee}
svg{background:var(--bg)} text{fill:var(--fg);font-family:Georgia,'Times New Roman',serif}
.t{font-size:13px;font-weight:bold} .s{font-size:11px} .m{font-size:10.5px;fill:var(--mut)} .n{font-size:12px;font-weight:bold}
.mono{font-family:'DejaVu Sans Mono',Menlo,monospace}
.blk{fill:var(--fill);stroke:var(--line);stroke-width:1.2} .lnk{stroke:var(--line);stroke-width:1.4;fill:none}
.ext{stroke-dasharray:5 3} .rule{stroke:var(--mut);stroke-width:.6}
"""


def _f(x, d=1):
    return "n/a" if x is None else f"{x:.{d}f}"


def render(title, blocks, links, strip, foot):
    """blocks: list of dicts {title, sub, lines:[...], external:bool}; links: list of dicts {rate, width, lines:[...]}
    with len(links) == len(blocks) - 1 plus an optional final link; strip: dict for the quality strip."""
    n = len(blocks)
    width = MARGIN * 2 + n * W_BLOCK + (n - 1) * GAP
    height = TOP + H_BLOCK + 225
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{escape(title)}">',
         f"<style>{CSS}</style>", f'<text x="{MARGIN}" y="26" class="t" style="font-size:16px">{escape(title)}</text>',
         f'<text x="{MARGIN}" y="44" class="m">{escape(foot[0])}</text>']
    xs = [MARGIN + i * (W_BLOCK + GAP) for i in range(n)]
    for b, x in zip(blocks, xs):
        cls = "blk ext" if b.get("external") else "blk"
        o.append(f'<rect x="{x}" y="{TOP}" width="{W_BLOCK}" height="{H_BLOCK}" rx="2" class="{cls}"/>')
        o.append(f'<text x="{x + 10}" y="{TOP + 20}" class="t">{escape(b["title"])}</text>')
        o.append(f'<text x="{x + 10}" y="{TOP + 35}" class="m">{escape(b["sub"])}</text>')
        o.append(f'<line x1="{x}" x2="{x + W_BLOCK}" y1="{TOP + 43}" y2="{TOP + 43}" class="rule"/>')
        y = TOP + 59
        for ln in b["lines"]:
            if ln == "-":
                o.append(f'<line x1="{x + 8}" x2="{x + W_BLOCK - 8}" y1="{y - 9}" y2="{y - 9}" class="rule"/>')
                y += 4
                continue
            o.append(f'<text x="{x + 10}" y="{y}" class="s">{escape(ln)}</text>')
            y += 15
    for i, lk in enumerate(links):
        x0 = xs[i] + W_BLOCK
        x1 = xs[i + 1] if i + 1 < n else x0 + GAP
        ym = TOP + H_BLOCK // 2
        o.append(f'<line x1="{x0}" x2="{x1 - 6}" y1="{ym}" y2="{ym}" class="lnk"/>')
        o.append(f'<path d="M{x1 - 6} {ym - 4} L{x1} {ym} L{x1 - 6} {ym + 4}" class="lnk"/>')
        cx = (x0 + x1) / 2
        ty = TOP - 8 - 14 * (len(lk["lines"]) - 1)
        for j, ln in enumerate(lk["lines"]):
            cls = "n mono" if j == 0 else ("s mono" if j <= 1 else "m mono")
            o.append(f'<text x="{cx}" y="{ty + 14 * j}" text-anchor="middle" class="{cls}" style="font-size:10.5px">{escape(ln)}</text>')
        o.append(f'<line x1="{cx}" x2="{cx}" y1="{TOP - 6}" y2="{ym - 2}" class="rule" stroke-dasharray="2 2"/>')
    # the quality strip: SINAD along the chain, measured and predicted
    sy = TOP + H_BLOCK + 34
    o.append(f'<text x="{MARGIN}" y="{sy}" class="t">{escape(strip["title"])}</text>')
    o.append(f'<text x="{MARGIN}" y="{sy + 15}" class="m">{escape(strip["sub"])}</text>')
    vals = strip["rows"]
    lo, hi = strip["axis"]
    bar_x0 = MARGIN + 190
    bar_w_max = width - bar_x0 - MARGIN - 150

    def xpos(v):
        return bar_x0 + bar_w_max * (v - lo) / (hi - lo)

    for k, v in enumerate(vals):
        yy = sy + 34 + k * 34
        o.append(f'<text x="{MARGIN}" y="{yy + 11}" class="s">{escape(v["label"])}</text>')
        o.append(f'<rect x="{bar_x0}" y="{yy}" width="{xpos(v["measured"]) - bar_x0:.1f}" height="11" fill="var(--acc)"/>')
        o.append(f'<rect x="{bar_x0}" y="{yy + 14}" width="{xpos(v["predicted"]) - bar_x0:.1f}" height="7" fill="none" stroke="var(--line)" stroke-width="1"/>')
        xe = xpos(hi) + 16
        o.append(f'<text x="{xe}" y="{yy + 10}" class="s mono">{v["measured"]:.1f} dB  ENOB {v["enob"]:.2f} b</text>')
        o.append(f'<text x="{xe}" y="{yy + 22}" class="m mono">predicted {v["predicted"]:.1f} dB</text>')
    yb = sy + 34 + len(vals) * 34
    for t in range(int(lo), int(hi) + 1, 5):
        o.append(f'<line x1="{xpos(t)}" x2="{xpos(t)}" y1="{sy + 28}" y2="{yb - 6}" class="rule" stroke-dasharray="1 3"/>')
        o.append(f'<text x="{xpos(t)}" y="{yb + 6}" text-anchor="middle" class="m mono">{t}</text>')
    o.append(f'<text x="{bar_x0 - 22}" y="{yb + 6}" text-anchor="end" class="m">SINAD, dB (axis starts at {int(lo)})</text>')
    if strip.get("reference"):
        rv, rl = strip["reference"]
        o.append(f'<line x1="{xpos(rv)}" x2="{xpos(rv)}" y1="{sy + 26}" y2="{yb - 4}" class="lnk" stroke-dasharray="4 3"/>')
        o.append(f'<text x="{xpos(rv) + 4}" y="{sy + 24}" class="m">{escape(rl)}</text>')
    o.append(f'<text x="{MARGIN}" y="{height - 12}" class="m">{escape(foot[1])}</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"
