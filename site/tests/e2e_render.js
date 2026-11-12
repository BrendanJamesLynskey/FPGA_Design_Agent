// Browser check for the site's graphics (brief 61). A heavy job: run under a heavy slot, memory-capped.
//   NODE_PATH=<dir with puppeteer> node site/tests/e2e_render.js <built site dir> <page,page,...>
// Each page at 390 and 1280 px, light and dark, with and without reduced motion: no page or console error, no horizontal
// overflow, every showcase hero and every player has drawn something, and under reduced motion nothing is playing.
const puppeteer = require('puppeteer');
const path = require('path');
const [pub, pagesArg] = process.argv.slice(2);
(async () => {
  const b = await puppeteer.launch({headless: 'new', executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--disable-gpu']});
  const fails = [], record = [];
  for (const page of pagesArg.split(',')) for (const w of [390, 1280]) for (const dark of [false, true]) for (const rm of [false, true]) {
    const p = await b.newPage();
    const errs = [];
    p.on('pageerror', e => errs.push(String(e)));
    p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    await p.setRequestInterception(true);
    p.on('request', r => (r.url().startsWith('file:') || r.url().startsWith('data:')) ? r.continue() : r.abort());
    await p.setViewport({width: w, height: 900});
    await p.emulateMediaFeatures([{name: 'prefers-color-scheme', value: dark ? 'dark' : 'light'}, {name: 'prefers-reduced-motion', value: rm ? 'reduce' : 'no-preference'}]);
    await p.goto('file://' + path.resolve(pub, page), {waitUntil: 'load'});
    await new Promise(r => setTimeout(r, 400));
    const r = await p.evaluate(() => {
      const ov = document.documentElement.scrollWidth - window.innerWidth;
      const kits = [...document.querySelectorAll('.kit[data-kit]')].map(k => ({kind: k.dataset.kit, shapes: k.querySelectorAll('.kitart svg rect, .kitart svg path, .kitart svg circle').length, ctl: !!k.querySelector('.ctl')}));
      const runs = document.querySelector('#home-runs') ? document.querySelectorAll('#home-runs .m').length : -1;
      const bare = [...document.querySelectorAll('.player')].filter(x => !x.querySelector('.ctl')).length;
      const playing = [...document.querySelectorAll('.player button')].filter(x => x.textContent === 'Pause').length;
      return {ov, kits, runs, bare, playing};
    });
    // every replay step of every hero: no two visible SVG text boxes may overlap; staged-wave text at least 12 px on a phone
    const steps = await p.evaluate(async () => {
      const check = () => {
        const overlap = [];
        let minPx = Infinity;
        for (const svg of document.querySelectorAll('.kitart svg')) {
          const ts = [...svg.querySelectorAll('text')].filter(t => t.textContent.trim() && getComputedStyle(t).visibility !== 'hidden')
            .map(t => ({t: t.textContent.trim(), r: t.getBoundingClientRect(), px: parseFloat(getComputedStyle(t).fontSize) * (t.getScreenCTM() ? t.getScreenCTM().a : 1)}))
            .filter(x => x.r.width > 0);
          if (svg.classList.contains('stagedwave')) ts.forEach(x => { minPx = Math.min(minPx, x.px); });
          for (let i = 0; i < ts.length; i++) for (let j = i + 1; j < ts.length; j++) {
            const a = ts[i].r, b = ts[j].r;
            const ix = Math.min(a.right, b.right) - Math.max(a.left, b.left), iy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
            if (ix > 1 && iy > 1) overlap.push(ts[i].t + ' / ' + ts[j].t);
          }
        }
        return {overlap, minPx};
      };
      const out = {steps: 0, overlap: [], minPx: Infinity, titles: []};
      for (const k of document.querySelectorAll('.kit[data-kit]')) {
        const svg = k.querySelector('.kitart svg');
        const title = svg && svg.querySelector('title');
        out.titles.push(title ? title.textContent : '');
        const reset = k.querySelector('button[aria-label="Reset"]'), next = k.querySelector('button[aria-label="Next step"]');
        const rng = k.querySelector('input[type=range]');
        if (!next || !rng) continue;
        if (reset) reset.click();
        const n = +rng.max + 1;
        for (let i = 0; i < n && i < 80; i++) {
          const c = check(); out.steps++;
          c.overlap.forEach(o => out.overlap.push(`step ${i + 1}: ${o}`));
          out.minPx = Math.min(out.minPx, c.minPx);
          next.click();
          await new Promise(r => setTimeout(r, 15));
        }
      }
      return out;
    });
    r.overlap = steps.overlap; r.steps = steps.steps; r.minPx = steps.minPx === Infinity ? null : +steps.minPx.toFixed(1);
    r.titles = steps.titles;
    const tag = `${page} ${w} ${dark ? 'dark' : 'light'}${rm ? ' reduced' : ''}`;
    record.push({page, width: w, dark, reduced: rm, playing_at_load: r.playing, steps: r.steps, overlaps: r.overlap.length,
                 min_wave_text_px: r.minPx, svg_titles: r.titles});
    if (errs.length) fails.push(`${tag}: errors ${errs.join(' | ')}`);
    if (r.ov > 0) fails.push(`${tag}: horizontal overflow ${r.ov}px`);
    for (const k of r.kits) if (!k.shapes || !k.ctl) fails.push(`${tag}: ${k.kind} hero drew nothing`);
    if (r.runs === 0) fails.push(`${tag}: runs chart empty`);
    if (r.bare) fails.push(`${tag}: ${r.bare} player(s) without controls`);
    if (rm && r.playing) fails.push(`${tag}: ${r.playing} player(s) playing under reduced motion`);
    if (r.overlap.length) fails.push(`${tag}: overlapping SVG text: ${r.overlap.slice(0, 3).join('; ')}`);
    if (w <= 400 && r.minPx !== null && r.minPx < 11.95) fails.push(`${tag}: staged-wave text ${r.minPx} px, below 12 px`);
    console.log(tag, JSON.stringify(r));
    await p.close();
  }
  await b.close();
  if (process.env.E2E_RECORD) require('fs').writeFileSync(process.env.E2E_RECORD, JSON.stringify({checks: record, failures: fails}, null, 1) + '\n');
  if (fails.length) { console.log('FAIL\n' + fails.join('\n')); process.exit(1); }
  console.log('ok');
})();
