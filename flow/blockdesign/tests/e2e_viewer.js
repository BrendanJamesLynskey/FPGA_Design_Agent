// Browser check for the block-design viewer (brief 65A). A heavy job: run under a heavy slot, memory-capped.
//   NODE_PATH=<dir with puppeteer> node flow/blockdesign/tests/e2e_viewer.js <page.html>[,<page.html>...] [<screenshot dir>]
// Each page at 390 and 1280 px, light and dark: no page or console error, no horizontal overflow, no two visible SVG
// text boxes overlapping (every level of the diagram, both layouts as shown at that width, and the address map), every
// block opens a drawer with its details when clicked, and every level tab shows its diagram.
const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');
const [pagesArg, shots] = process.argv.slice(2);
(async () => {
  const b = await puppeteer.launch({headless: 'new', executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--disable-gpu']});
  const fails = [], record = [];
  for (const page of pagesArg.split(',')) for (const w of [390, 1280]) for (const dark of [false, true]) {
    const p = await b.newPage();
    const errs = [];
    p.on('pageerror', e => errs.push(String(e)));
    p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    await p.setRequestInterception(true);
    p.on('request', r => (r.url().startsWith('file:') || r.url().startsWith('data:')) ? r.continue() : r.abort());
    await p.setViewport({width: w, height: 900});
    await p.emulateMediaFeatures([{name: 'prefers-color-scheme', value: dark ? 'dark' : 'light'}]);
    await p.goto('file://' + path.resolve(page), {waitUntil: 'load'});
    const tag = `${path.basename(page)} ${w}px ${dark ? 'dark' : 'light'}`;
    const r = await p.evaluate(async () => {
      const out = {ov: document.documentElement.scrollWidth - window.innerWidth, overlap: [], levels: 0, blocks: 0, drawn: 0, empty: [], tiny: []};
      const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      const check = (where) => {
        for (const svg of [...document.querySelectorAll('svg.bdsvg, svg.bdaddr')].filter(visible)) {
          const ts = [...svg.querySelectorAll('text')].filter(t => t.textContent.trim()).map(t => ({t: t.textContent.trim(), r: t.getBoundingClientRect(),
            px: parseFloat(getComputedStyle(t).fontSize) * (t.getScreenCTM() ? t.getScreenCTM().a : 1)})).filter(x => x.r.width > 0);
          ts.forEach(x => { if (x.px < 9.5) out.tiny.push(`${where}: ${x.t} ${x.px.toFixed(1)}px`); });
          for (let i = 0; i < ts.length; i++) for (let j = i + 1; j < ts.length; j++) {
            const a = ts[i].r, c = ts[j].r;
            const ix = Math.min(a.right, c.right) - Math.max(a.left, c.left), iy = Math.min(a.bottom, c.bottom) - Math.max(a.top, c.top);
            if (ix > 1 && iy > 1) out.overlap.push(`${where}: ${ts[i].t} / ${ts[j].t}`);
          }
          // text must stay inside its block: a label wider than the box overflows it
          for (const g of svg.querySelectorAll('g.bdblk, g.bdpt')) {
            const box = g.querySelector('rect').getBoundingClientRect();
            for (const t of g.querySelectorAll('text')) { const tr = t.getBoundingClientRect(); if (tr.right > box.right + 0.5) out.overlap.push(`${where}: "${t.textContent}" runs out of its block`); }
          }
        }
      };
      const tabs = [...document.querySelectorAll('.bdtab')];
      for (const t of tabs.length ? tabs : [null]) {
        if (t) t.click();
        await new Promise(r => setTimeout(r, 50));
        out.levels++;
        const where = t ? t.textContent : 'page';
        check(where);
        for (const g of [...document.querySelectorAll('.bdblk')].filter(visible)) {
          out.blocks++;
          g.dispatchEvent(new MouseEvent('click', {bubbles: true}));
          const d = document.querySelector('.bddrawer');
          if (d && d.querySelector('h3') && d.querySelector('h3').textContent.startsWith(g.dataset.id)) out.drawn++; else out.empty.push(g.dataset.id);
        }
        // a drawer full of tables must not widen the page either
        const ov2 = document.documentElement.scrollWidth - window.innerWidth; if (ov2 > out.ov) out.ov = ov2;
      }
      if (tabs.length) tabs[0].click();
      return out;
    });
    if (shots) {
      fs.mkdirSync(shots, {recursive: true});
      await p.screenshot({path: path.join(shots, `${path.basename(page, '.html')}_${w}_${dark ? 'dark' : 'light'}.png`), fullPage: true});
    }
    record.push({tag, ...r, errs});
    if (errs.length) fails.push(`${tag}: errors ${errs.join('; ')}`);
    if (r.ov > 0) fails.push(`${tag}: horizontal overflow ${r.ov}px`);
    if (r.overlap.length) fails.push(`${tag}: overlapping or overflowing text: ${r.overlap.slice(0, 6).join(' | ')}`);
    if (r.tiny.length) fails.push(`${tag}: text under 9.5 px: ${r.tiny.slice(0, 4).join(' | ')}`);
    if (!r.blocks || r.empty.length) fails.push(`${tag}: blocks ${r.blocks}, drawer missing for ${r.empty.join(', ')}`);
    await p.close();
  }
  await b.close();
  console.log(JSON.stringify(record.map(x => ({tag: x.tag, levels: x.levels, blocks: x.blocks, drawn: x.drawn, ov: x.ov})), null, 0));
  if (fails.length) { console.log('FAIL\n' + fails.join('\n')); process.exit(1); }
  console.log('PASS');
})();
