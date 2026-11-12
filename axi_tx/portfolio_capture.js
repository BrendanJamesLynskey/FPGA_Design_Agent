// Portfolio media for the AXI transactor card, recorded from the showcase page's own hero (puppeteer and Chrome).
//   NODE_PATH=<dir with puppeteer> node axi_tx/portfolio_capture.js <built site dir> <out dir>
// Writes frames/fNNN.png (one per step of the replay, dark theme) for ffmpeg, and screenshots of the whole page at 390,
// 768 and 1280 px, light and dark, for review.
const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');
const [pub, out] = process.argv.slice(2);
(async () => {
  fs.mkdirSync(path.join(out, 'frames'), {recursive: true});
  fs.mkdirSync(path.join(out, 'review'), {recursive: true});
  const b = await puppeteer.launch({headless: 'new', executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--disable-gpu']});
  const url = 'file://' + path.resolve(pub, 'showcase/axi_transactor.html');
  const block = async p => { await p.setRequestInterception(true); p.on('request', r => (r.url().startsWith('file:') || r.url().startsWith('data:')) ? r.continue() : r.abort()); };
  for (const w of [390, 768, 1280]) for (const dark of [false, true]) {
    const p = await b.newPage(); await block(p);
    await p.setViewport({width: w, height: 900});
    await p.emulateMediaFeatures([{name: 'prefers-color-scheme', value: dark ? 'dark' : 'light'}]);
    await p.goto(url, {waitUntil: 'load'}); await new Promise(r => setTimeout(r, 300));
    await p.screenshot({path: path.join(out, 'review', `page_${w}_${dark ? 'dark' : 'light'}.png`), fullPage: true});
    await p.close();
  }
  const p = await b.newPage(); await block(p);
  await p.setViewport({width: 1200, height: 1400, deviceScaleFactor: 1});
  await p.emulateMediaFeatures([{name: 'prefers-color-scheme', value: 'dark'}, {name: 'prefers-reduced-motion', value: 'no-preference'}]);
  await p.goto(url, {waitUntil: 'load'}); await new Promise(r => setTimeout(r, 300));
  const kit = await p.$('.kit[data-kit="wave"]');
  const n = await p.evaluate(() => +document.querySelector('.kit[data-kit="wave"] input[type=range]').max + 1);
  await p.evaluate(() => document.querySelector('.kit[data-kit="wave"] button[aria-label="Reset"]').click());
  for (let i = 0; i < n; i++) {
    await kit.screenshot({path: path.join(out, 'frames', `f${String(i).padStart(3, '0')}.png`)});
    await p.evaluate(() => document.querySelector('.kit[data-kit="wave"] button[aria-label="Next step"]').click());
    await new Promise(r => setTimeout(r, 60));
  }
  console.log('frames', n);
  await b.close();
})();
