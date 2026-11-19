// Headless check of every navigator view (brief 103): screenshots at 1280 and 390 px wide, zero page errors, no horizontal overflow at 390 px,
// and no request to any host but the navigator's own. Usage:
//   NODE_PATH=/home/brendan/Claude_sandbox/node_modules node navigator/shoot.js http://127.0.0.1:8791/?t=<token> <out dir>
const puppeteer = require('puppeteer');
const fs = require('fs');
const [url, out] = [process.argv[2], process.argv[3]];
const origin = new URL(url).origin;
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await puppeteer.launch({ headless: 'new', executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--use-gl=swiftshader', '--mute-audio'] });
  const report = { errors: [], blocked: [], overflow: [], shots: [] };
  for (const [w, h, tag] of [[1280, 900, 'wide'], [390, 844, 'phone']]) {
    const page = await browser.newPage();
    await page.setViewport({ width: w, height: h });
    await page.setRequestInterception(true);
    page.on('request', (r) => { if (r.url().startsWith(origin) || r.url().startsWith('data:') || r.url().startsWith('about:')) r.continue(); else { report.blocked.push(r.url()); r.abort(); } });
    page.on('pageerror', (e) => report.errors.push(tag + ' pageerror: ' + e.message));
    page.on('console', (m) => { if (m.type() === 'error') report.errors.push(tag + ' console: ' + m.text()); });
    await page.goto(url, { waitUntil: 'networkidle0' });
    const shot = async (name, fullPage = true) => {
      const f = `${out}/${name}_${tag}.png`;
      await page.screenshot({ path: f, fullPage });
      const sw = await page.evaluate(() => document.documentElement.scrollWidth);
      if (tag === 'phone' && sw > w + 1) report.overflow.push(`${name}: scrollWidth ${sw} > ${w}`);
      report.shots.push(f);
    };
    const go = async (hash) => { await page.evaluate((x) => { location.hash = x; }, hash); await new Promise((r) => setTimeout(r, 1500)); };
    await go('#/project'); await shot('project');
    await page.evaluate(() => document.querySelector('.node .name').click()); await new Promise((r) => setTimeout(r, 400)); await shot('project_drawer', false);
    await page.keyboard.press('Escape');
    await page.evaluate(() => { const c = document.querySelectorAll('.node input[type=checkbox]:not(:disabled)')[1]; if (c) c.click(); }); await new Promise((r) => setTimeout(r, 600)); await shot('project_scope');
    await go('#/timing'); await shot('timing');
    await page.evaluate(() => document.querySelector('table tbody tr.click').click()); await new Promise((r) => setTimeout(r, 400)); await shot('timing_drawer', false);
    await page.keyboard.press('Escape');
    await go('#/runs'); await shot('runs');
    await page.evaluate(() => { const r = document.querySelector('tr.click'); if (r) r.click(); }); await new Promise((r) => setTimeout(r, 800)); await shot('runs_drawer', false);
    await page.keyboard.press('Escape');
    await go('#/measure'); await new Promise((r) => setTimeout(r, 1500)); await shot('measure_eye');
    // the eye viewer: 3-D tab, then compare (needs capture B)
    const frame = page.frames().find((f) => f.url().includes('/measure/page'));
    if (frame) {
      await frame.click('#t-3d'); await new Promise((r) => setTimeout(r, 500)); await shot('measure_3d');
      await page.select('select:nth-of-type(1)', await page.evaluate(() => document.querySelectorAll('select')[0].value));
      await page.evaluate(() => { const s = document.querySelectorAll('select')[1]; s.selectedIndex = 2; s.dispatchEvent(new Event('change')); });
      await new Promise((r) => setTimeout(r, 1500));
      const f2 = page.frames().find((f) => f.url().includes('/measure/page'));
      await f2.click('#t-cmp'); await new Promise((r) => setTimeout(r, 600)); await shot('measure_compare');
    } else report.errors.push(tag + ': no eye frame');
    for (const t of ['board', 'ppm', 'buf', 'cond']) {
      await page.evaluate((k) => document.querySelector(`#mtabs button[data-k=${k}]`).click(), t); await new Promise((r) => setTimeout(r, 500)); await shot('measure_' + t);
    }
    await go('#/health'); await shot('health');
    await go('#/models'); await shot('models');
    await page.close();
  }
  await browser.close();
  fs.writeFileSync(`${out}/check.json`, JSON.stringify(report, null, 1));
  console.log(JSON.stringify({ shots: report.shots.length, errors: report.errors, blocked: report.blocked, overflow: report.overflow }, null, 1));
})();
