"""The FPGA Force mark (the owner's chosen G2: the flip-flop box with FF and one heavy force arrow).

The drawing is copied unchanged from symbol `g-net` of _handoff/fpga_agent/resources/fpga_force_logo_concepts.html; only the
colour reference changes (`var(--mark)` becomes the colour passed in). One colour, no glow.
"""
INNER = ('<rect x="4" y="12" width="30" height="40" rx="2" fill="none" stroke="{c}" stroke-width="4"/>'
         '<path d="M4 41 L11 46 L4 51" fill="none" stroke="{c}" stroke-width="3"/>'
         '<path d="M11 20 V37 M11 20 H16 M11 28 H15" fill="none" stroke="{c}" stroke-width="3.6" stroke-linecap="square"/>'
         '<path d="M22 20 V37 M22 20 H27 M22 28 H26" fill="none" stroke="{c}" stroke-width="3.6" stroke-linecap="square"/>'
         '<path d="M34 32 H50" stroke="{c}" stroke-width="6"/>'
         '<path d="M49 24 L62 32 L49 40 Z" fill="{c}"/>')


def mark(colour: str = "currentColor") -> str:
    return INNER.format(c=colour)


def inline_svg(cls: str = "mark", size: int = 28) -> str:
    """The mark for the page header: follows the text colour, so it follows the light and dark themes."""
    return f'<svg class="{cls}" viewBox="0 0 64 64" width="{size}" height="{size}" aria-hidden="true" focusable="false">{mark()}</svg>'


def favicon_svg() -> str:
    """Browser-tab icon: one colour that follows the browser's theme (dark mark on light, light mark on dark)."""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><title>FPGA Force</title>'
            '<style>:root{color:#161616}@media (prefers-color-scheme:dark){:root{color:#f2f2f2}}</style>'
            + mark() + '</svg>\n')


def solid_svg(colour: str, bg: str | None = None, pad: int = 0) -> str:
    """A fixed-colour copy (for the PNG icons); `pad` adds a margin so an app icon has room."""
    vb = f"{-pad} {-pad} {64 + 2 * pad} {64 + 2 * pad}"
    back = f'<rect x="{-pad}" y="{-pad}" width="{64 + 2 * pad}" height="{64 + 2 * pad}" fill="{bg}"/>' if bg else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">{back}{mark(colour)}</svg>'


def small_svg(colour: str = "#000", bg: str | None = "#fff") -> str:
    """The simplified 16 px variant: the full mark's FF fills in at 16 px, so this one is drawn on the 16 px pixel grid
    (box, two F glyphs one pixel thick, no clock notch, a heavy arrow). Used for icon-16.png only."""
    back = f'<rect width="16" height="16" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">{back}'
            f'<rect x="0.5" y="2.5" width="10" height="11" fill="none" stroke="{colour}" stroke-width="1"/>'
            f'<path d="M2.5 5 V12 M2 5.5 H5 M2 8.5 H4 M6.5 5 V12 M6 5.5 H9 M6 8.5 H8" fill="none" stroke="{colour}" stroke-width="1"/>'
            f'<path d="M11 7 H13 V9 H11 Z" fill="{colour}"/><path d="M12.5 5 L16 8 L12.5 11 Z" fill="{colour}" shape-rendering="geometricPrecision"/></svg>')
