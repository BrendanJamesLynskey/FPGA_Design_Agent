// Headless check and evidence for the stage map (brief 238): on the Live page, the map of a finished run (a replay of the 213 run with a route back), of a run that stopped on a
// visit limit, and of a run that is working now (trace mode, a tool step open), light and dark, at 1280 and 390 px; a screen recording (WebM) of a replay; the reduced-motion
// setting (no token, state changes only); zero page errors, no horizontal overflow at 390 px, no request to any host but the navigator's own. Usage:
//   NODE_PATH=/home/brendan/Claude_sandbox/node_modules node navigator/shoot_238.js http://127.0.0.1:8794/?t=<token> <out dir>
// Serve it with: python3 -m navigator.tests.demo_238 --port 8794 --workdir <tmp> [--append]
const puppeteer = require('puppeteer');
const fs = require('fs');
const [url, out] = [process.argv[2], process.argv[3]];
const origin = new URL(url).origin;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PASS = '10_p2_bram_rom_k3_control', LIMIT = '2_p1_clkmeter_k3_treatment', LIVE = '20261126-120000-live';
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await puppeteer.launch({ headless: 'new', executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--use-gl=swiftshader', '--mute-audio'] });
  const report = { errors: [], blocked: [], overflow: [], shots: [], checks: {} };
  async function open(w, h, theme, reduced) {
    const page = await browser.newPage();
    await page.setViewport({ width: w, height: h });
    if (reduced) await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);
    await page.setRequestInterception(true);
    page.on('request', (r) => { if (r.url().startsWith(origin) || r.url().startsWith('data:') || r.url().startsWith('about:')) r.continue(); else { report.blocked.push(r.url()); r.abort(); } });
    page.on('pageerror', (e) => report.errors.push('pageerror: ' + e.message));
    page.on('console', (m) => { if (m.type() === 'error') report.errors.push('console: ' + m.text()); });
    page.on('dialog', async (d) => { await d.dismiss(); });
    await page.goto(url, { waitUntil: 'networkidle0' });
    if (theme === 'light') await page.evaluate(() => document.getElementById('theme').click());
    await page.evaluate(() => { location.hash = '#/live'; }); await sleep(1200);
    return page;
  }
  async function pick(page, id) {
    await page.evaluate((id) => { const r = [...document.querySelectorAll('tr.click')].find((x) => x.textContent.includes(id)); if (!r) throw new Error('no run ' + id); r.click(); }, id);
    await sleep(2200);
  }
  async function shot(page, name, w, h) {
    const f = `${out}/${name}.png`;
    if (w < 700) await page.screenshot({ path: f, fullPage: true });
    else await (await page.$('.stagemap')).screenshot({ path: f });
    const sw = await page.evaluate(() => document.documentElement.scrollWidth);
    if (w < 700 && sw > w + 1) report.overflow.push(`${name}: scrollWidth ${sw} > ${w}`);
    report.shots.push(f);
  }
  const LIVE_ONLY = process.argv[4] === 'live-only';
  if (!LIVE_ONLY) for (const [w, h] of [[1280, 900], [390, 844]]) for (const theme of ['dark', 'light']) {
    const page = await open(w, h, theme, false);
    await pick(page, LIVE); await shot(page, `working_${theme}_${w}`, w, h);
    if (w === 1280 && theme === 'dark') {
      report.checks.live = await page.evaluate(() => ({ working: document.querySelectorAll('.stagemap .node.working').length, spinner: [...document.querySelectorAll('.stagemap .spin')].filter((e) => !e.hasAttribute('hidden')).length,
        routes: [...document.querySelectorAll('.stagemap .map-routes li')].map((x) => x.textContent), live: document.querySelector('.stagemap [aria-live]').textContent, state: document.querySelector('.stagemap .map-state').textContent }));
    }
    await pick(page, LIMIT); await shot(page, `visit_limit_${theme}_${w}`, w, h);
    await pick(page, PASS); await shot(page, `route_back_${theme}_${w}`, w, h);
    await page.close();
  }
  // the recording: a replay of the run with a route back, at 2x
  if (!LIVE_ONLY) {
    const page = await open(1100, 900, 'dark', false);
    await pick(page, PASS);
    await page.evaluate(() => document.querySelector('.stagemap').scrollIntoView());
    const box = await (await page.$('.stagemap')).boundingBox();
    const rec = await page.screencast({ path: `${out}/replay_${PASS}.webm`, crop: { x: Math.max(0, box.x - 8), y: Math.max(0, box.y - 8), width: Math.min(1100, box.width + 16), height: Math.min(880, box.height + 16) } });
    await sleep(500);
    await page.evaluate(() => { const b = [...document.querySelectorAll('.stagemap button')].find((x) => x.textContent === 'Replay'); b.click(); const sel = document.querySelector('.stagemap select'); sel.value = '2'; sel.dispatchEvent(new Event('change')); });
    let tokens = 0, flashes = 0, maxProgress = '';
    for (let i = 0; i < 120; i++) {
      await sleep(250);
      const s = await page.evaluate(() => ({ tok: !document.querySelector('.stagemap .token').hasAttribute('hidden'), fl: document.querySelectorAll('.stagemap [class*=flash-]').length, prog: document.querySelector('.stagemap .toolbar span').textContent, btn: [...document.querySelectorAll('.stagemap button')][0].textContent }));
      if (s.tok) tokens++; if (s.fl) flashes++; maxProgress = s.prog || maxProgress;
      if (s.btn === 'Replay' && i > 4) break;
    }
    await sleep(600);
    await rec.stop();
    report.checks.replay = { tokenSamples: tokens, flashSamples: flashes, lastProgress: maxProgress, final: await page.evaluate(() => document.querySelector('.stagemap .map-state').textContent) };
    await page.close();
  }
  if (!LIVE_ONLY) {
    const page = await open(1280, 900, 'dark', false);
    await pick(page, LIMIT);
    await page.evaluate(() => { const b = [...document.querySelectorAll('.stagemap button')].find((x) => x.textContent === 'Replay'); b.click(); const sel = document.querySelector('.stagemap select'); sel.value = '4'; sel.dispatchEvent(new Event('change')); });
    for (let i = 0; i < 200; i++) { await sleep(250); if (await page.evaluate(() => [...document.querySelectorAll('.stagemap button')][0].textContent === 'Replay')) break; }
    report.checks.limitFinal = await page.evaluate(() => document.querySelector('.stagemap .map-state').textContent);
    await page.close();
  }
  if (!LIVE_ONLY) {
    const page = await open(1280, 900, 'dark', true);
    await pick(page, PASS);
    await page.evaluate(() => { const b = [...document.querySelectorAll('.stagemap button')].find((x) => x.textContent === 'Replay'); b.click(); const sel = document.querySelector('.stagemap select'); sel.value = '4'; sel.dispatchEvent(new Event('change')); });
    let tok = 0, anim = new Set();
    for (let i = 0; i < 100; i++) {
      await sleep(200);
      const s = await page.evaluate(() => ({ tok: !document.querySelector('.stagemap .token').hasAttribute('hidden'), a: [...document.querySelectorAll('.stagemap .node-rect')].map((e) => getComputedStyle(e).animationName), btn: [...document.querySelectorAll('.stagemap button')][0].textContent }));
      if (s.tok) tok++; s.a.forEach((x) => anim.add(x));
      if (s.btn === 'Replay' && i > 3) break;
    }
    report.checks.reduced = { tokenSamples: tok, nodeAnimations: [...anim] };
    await shot(page, 'reduced_motion_1280', 1280, 900);
    await page.close();
  }
  // a live stage change (the demo appends events): a token travels while the page watches
  if (process.argv[4] === 'live' || LIVE_ONLY) {
    const page = await open(1280, 900, 'dark', false);
    await pick(page, LIVE);
    let tok = 0, seen = new Set();
    for (let i = 0; i < 160; i++) { await sleep(250); const s = await page.evaluate(() => ({ t: !document.querySelector('.stagemap .token').hasAttribute('hidden'), c: document.querySelector('.stagemap .node.working text')?.textContent })); if (s.t) tok++; if (s.c) seen.add(s.c); }
    report.checks.liveChange = { tokenSamples: tok, workingStages: [...seen] };
    await page.close();
  }
  await browser.close();
  fs.writeFileSync(`${out}/shoot_report.json`, JSON.stringify(report, null, 1));
  console.log(JSON.stringify(report, null, 1));
  process.exit(report.errors.length || report.blocked.length || report.overflow.length ? 1 : 0);
})();
