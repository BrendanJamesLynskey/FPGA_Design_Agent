// Headless check of the Examples page (brief 195) against navigator/tests/demo_examples.py (fake spawner; a real example result copied in as a "re-run"):
// 1280 and 390 px, zero page errors, no horizontal overflow at 390 px, no request to any host but the navigator's own. Usage:
//   NODE_PATH=/home/brendan/Claude_sandbox/node_modules node navigator/shoot_examples.js http://127.0.0.1:8794/?t=<token> <out dir>
const puppeteer = require('puppeteer');
const fs = require('fs');
const [url, out] = [process.argv[2], process.argv[3]];
const origin = new URL(url).origin;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await puppeteer.launch({ headless: 'new', executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--use-gl=swiftshader', '--mute-audio'] });
  const report = { errors: [], blocked: [], overflow: [], shots: [], dialogs: [] };
  for (const [w, h, tag] of [[1280, 900, 'wide'], [390, 844, 'phone']]) {
    const page = await browser.newPage();
    await page.setViewport({ width: w, height: h });
    await page.setRequestInterception(true);
    page.on('request', (r) => { if (r.url().startsWith(origin) || r.url().startsWith('data:') || r.url().startsWith('about:')) r.continue(); else { report.blocked.push(r.url()); r.abort(); } });
    page.on('pageerror', (e) => report.errors.push(tag + ' pageerror: ' + e.message));
    page.on('console', (m) => { if (m.type() === 'error') report.errors.push(tag + ' console: ' + m.text()); });
    page.on('dialog', async (d) => { report.dialogs.push(d.message().slice(0, 100)); await d.accept(); });
    await page.goto(url, { waitUntil: 'networkidle0' });
    const shot = async (name) => {
      const f = `${out}/${name}_${tag}.png`;
      await page.screenshot({ path: f, fullPage: true });
      const sw = await page.evaluate(() => document.documentElement.scrollWidth);
      if (tag === 'phone' && sw > w + 1) report.overflow.push(`${name}: scrollWidth ${sw} > ${w}`);
      report.shots.push(f);
    };
    await page.evaluate(() => { location.hash = '#/examples'; });
    await sleep(2500);
    await shot('examples');
    // compare the finished run the demo planted, in the first example that has one
    const sel = await page.$$('select');
    for (const s of sel) {
      const opts = await s.evaluate((e) => [...e.options].map((o) => o.value));
      const v = opts.find((x) => x);
      if (v) { await s.select(v); break; }
    }
    await sleep(2500);
    await shot('examples_compare');
    if (tag === 'wide') {
      const btn = await page.evaluateHandle(() => [...document.querySelectorAll('button')].find((b) => b.textContent.includes('Re-run') && !b.disabled));
      if (btn && btn.asElement()) { await btn.asElement().click(); await sleep(2000); await shot('examples_started'); }
    }
    await page.close();
  }
  await browser.close();
  fs.writeFileSync(`${out}/check.json`, JSON.stringify(report, null, 1));
  console.log(JSON.stringify({ shots: report.shots.length, errors: report.errors, blocked: report.blocked, overflow: report.overflow, dialogs: report.dialogs }, null, 1));
})();
