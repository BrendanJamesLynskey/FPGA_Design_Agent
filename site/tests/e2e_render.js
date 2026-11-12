// Browser check for the site's graphics (brief 61). A heavy job: run under a heavy slot, memory-capped.
//   NODE_PATH=<dir with puppeteer> node site/tests/e2e_render.js <built site dir> <page,page,...>
// Each page at 390 and 1280 px, light and dark, with and without reduced motion: no page or console error, no horizontal
// overflow, every showcase hero and every player has drawn something, and under reduced motion nothing is playing.
const puppeteer = require('puppeteer');
const path = require('path');
const [pub, pagesArg] = process.argv.slice(2);
(async () => {
  const b = await puppeteer.launch({headless: 'new', executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--disable-gpu']});
  const fails = [];
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
      const players = document.querySelectorAll('.player').length, ctls = document.querySelectorAll('.player .ctl').length;
      const playing = [...document.querySelectorAll('.player button')].filter(x => x.textContent === 'Pause').length;
      return {ov, kits, runs, players, ctls, playing};
    });
    const tag = `${page} ${w} ${dark ? 'dark' : 'light'}${rm ? ' reduced' : ''}`;
    if (errs.length) fails.push(`${tag}: errors ${errs.join(' | ')}`);
    if (r.ov > 0) fails.push(`${tag}: horizontal overflow ${r.ov}px`);
    for (const k of r.kits) if (!k.shapes || !k.ctl) fails.push(`${tag}: ${k.kind} hero drew nothing`);
    if (r.runs === 0) fails.push(`${tag}: runs chart empty`);
    if (r.players !== r.ctls) fails.push(`${tag}: ${r.players - r.ctls} player(s) without controls`);
    if (rm && r.playing) fails.push(`${tag}: ${r.playing} player(s) playing under reduced motion`);
    console.log(tag, JSON.stringify(r));
    await p.close();
  }
  await b.close();
  if (fails.length) { console.log('FAIL\n' + fails.join('\n')); process.exit(1); }
  console.log('ok');
})();
