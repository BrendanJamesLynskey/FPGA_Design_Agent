#!/usr/bin/env python3
"""Make the FPGA Force icons into site/src/icons/ (run by hand; the PNGs are committed, so the site build needs no browser).

    NODE_PATH=<dir with puppeteer> python3 site/make_icons.py

Writes favicon.svg (the full mark), icon-16.png is the simplified 16 px variant (logo.small_svg), plus (follows the browser theme), icon-16.png, icon-32.png, apple-touch-icon.png (180 px; the app icon: black
mark on white), and og-card.png (1200 x 630: mark and name). The mark is site/logo.py (the owner's G2, copied unchanged).
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import logo

HERE = Path(__file__).resolve().parent
OUT = HERE / "src" / "icons"
OUT.mkdir(parents=True, exist_ok=True)
(HERE / "src" / "favicon.svg").write_text(logo.favicon_svg())

og = ('<!doctype html><meta charset="utf-8"><style>html,body{margin:0}body{width:1200px;height:630px;background:#f6f6f4;color:#161616;'
      'font-family:system-ui,"Segoe UI",Roboto,Arial,sans-serif;display:flex;align-items:center;padding:0 110px;box-sizing:border-box;gap:56px}'
      'h1{font-size:104px;margin:0;line-height:1;letter-spacing:-.02em}p{font-size:34px;margin:22px 0 0;color:#4a4a4a;max-width:640px;line-height:1.3}</style>'
      f'<svg viewBox="0 0 64 64" width="300" height="300">{logo.mark("#161616")}</svg>'
      '<div><h1>FPGA Force</h1><p>A force multiplier: from your spec to a checked bitstream.</p></div>')
jobs = [
    {"html": logo.small_svg(), "w": 16, "h": 16, "scale": 16, "out": "icon-16.png"},
    {"html": logo.solid_svg("#000", "#fff", 2), "w": 32, "h": 32, "scale": 32, "out": "icon-32.png"},
    {"html": logo.solid_svg("#000", "#fff", 14), "w": 180, "h": 180, "scale": 180, "out": "apple-touch-icon.png"},
    {"html": og, "w": 1200, "h": 630, "raw": True, "out": "og-card.png"},
]
js = r"""
const puppeteer=require('puppeteer');const fs=require('fs');
(async()=>{const jobs=JSON.parse(fs.readFileSync(process.argv[2]));const out=process.argv[3];
const b=await puppeteer.launch({headless:'new',executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
for(const j of jobs){const p=await b.newPage();await p.setViewport({width:j.w,height:j.h});
 const html=j.raw?j.html:`<!doctype html><style>html,body{margin:0}svg{display:block;width:${j.scale}px;height:${j.scale}px}</style>${j.html}`;
 await p.setContent(html);await p.screenshot({path:out+'/'+j.out});await p.close();}
await b.close();})();
"""
with tempfile.TemporaryDirectory() as t:
    (Path(t) / "jobs.json").write_text(json.dumps(jobs))
    (Path(t) / "r.js").write_text(js)
    sys.exit(subprocess.call(["node", str(Path(t) / "r.js"), str(Path(t) / "jobs.json"), str(OUT)]))
