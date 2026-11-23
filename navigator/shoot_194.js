// Headless check of the brief 194 additions to the Start and Live pages against navigator/tests/demo_stage2.py (fake spawner): the profile picker, the switch drawer,
// and the profile line on the Live page; at 1280 and 390 px, zero page errors, no horizontal overflow at 390 px,
// no request to any host but the navigator's own. Usage:
//   NODE_PATH=/home/brendan/Claude_sandbox/node_modules node navigator/shoot_194.js http://127.0.0.1:8793/?t=<token> <out dir>
const puppeteer = require('puppeteer');
const fs = require('fs');
const [url, out] = [process.argv[2], process.argv[3]];
const origin = new URL(url).origin;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await puppeteer.launch({ headless: 'new', executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--use-gl=swiftshader', '--mute-audio'] });
  const report = { errors: [], blocked: [], overflow: [], shots: [], checks: {} };
  for (const [w, h, tag] of [[1280, 900, 'wide'], [390, 844, 'phone']]) {
    const page = await browser.newPage();
    await page.setViewport({ width: w, height: h });
    await page.setRequestInterception(true);
    page.on('request', (r) => { if (r.url().startsWith(origin) || r.url().startsWith('data:') || r.url().startsWith('about:')) r.continue(); else { report.blocked.push(r.url()); r.abort(); } });
    page.on('pageerror', (e) => report.errors.push(tag + ' pageerror: ' + e.message));
    page.on('console', (m) => { if (m.type() === 'error') report.errors.push(tag + ' console: ' + m.text()); });
    page.on('dialog', async (d) => { await d.accept(); });
    await page.goto(url, { waitUntil: 'networkidle0' });
    const shot = async (name) => {
      const f = `${out}/${name}_${tag}.png`;
      await page.screenshot({ path: f, fullPage: true });
      const sw = await page.evaluate(() => document.documentElement.scrollWidth);
      if (tag === 'phone' && sw > w + 1) report.overflow.push(`${name}: scrollWidth ${sw} > ${w}`);
      report.shots.push(f);
    };
    await page.evaluate(() => { location.hash = '#/start'; }); await sleep(1500);
    const startBtn = () => page.evaluate(() => { const b = [...document.querySelectorAll('button')].find((e) => e.textContent.includes('Start the run')); return b ? b.disabled : null; });
    await shot('start_picker');
    await page.evaluate(() => { document.querySelector('details.drawer summary').click(); }); await sleep(300);
    await page.evaluate(() => { const s = [...document.querySelectorAll('fieldset select')].find((e) => [...e.options].some((o) => o.value === 'high_reliability')); s.value = 'high_reliability'; s.dispatchEvent(new Event('change')); }); await sleep(600);
    await page.evaluate(() => { document.querySelector('details.drawer summary').click(); }); await sleep(300);
    await shot('start_profile_drawer');
    report.checks[tag + '_start_enabled'] = !(await startBtn());
    if (tag === 'wide') {
      await page.evaluate(() => { [...document.querySelectorAll('button')].find((e) => e.textContent.includes('Start the run')).click(); }); await sleep(2000);
      await shot('start_started');
    }
    await page.evaluate(() => { location.hash = '#/live'; }); await sleep(1500);
    await shot('live');
    await page.close();
  }
  await browser.close();
  fs.writeFileSync(`${out}/report.json`, JSON.stringify(report, null, 1));
  console.log(JSON.stringify(report, null, 1));
  process.exit(report.errors.length || report.blocked.length || report.overflow.length ? 1 : 0);
})();
