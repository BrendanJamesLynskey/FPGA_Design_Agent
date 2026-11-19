"""On-chip RX eye scan for a GTH link (brief 96D): the host side of designs/b96_kr260_10g's eye-scan registers, the capture format, the derived numbers
(eye width and height at a BER depth, bathtub curves), the SVG and interactive displays, and a small JSON API over captures.

    python -m flow.eyescan run    --serial <cable serial> --lock-text "96D: ..." --out <dir> [--eq lpm|dfe] [--target-ber 1e-9] ...   (board; the owner runs it)
    python -m flow.eyescan run    --fake --out <dir>                    (offline: the SYNTHETIC statistical eye of flow/eyescan/fake.py, labelled as such)
    python -m flow.eyescan probe  --serial <cable serial>               (READ-ONLY: build features and the DRP words; no writes, no laser)
    python -m flow.eyescan plot   <capture.json> [-o dir] [--ber 1e-9]  (static heat map and bathtub SVG)
    python -m flow.eyescan page   <capture.json> [<capture2.json>] -o page.html
    python -m flow.eyescan compare <a.json> <b.json> [--ber 1e-9]
    python -m flow.eyescan api    <capture.json> [--ber 1e-9] [--what summary|eye|bathtub|surface]

READ flow/eyescan/README.md before trusting a number: the eye is measured AFTER the receiver's equaliser, a point's BER is limited by the bits it examined, and a
synthetic capture is not a measurement.
"""
