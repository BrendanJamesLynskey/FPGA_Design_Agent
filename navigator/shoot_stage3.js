// Headless check of the stage 3 views (brief 182): on the Live page the plain-words status, the request and question panels and the console drawer, at 1280 and 390 px.
// Zero page errors, no horizontal overflow at 390 px, no request to any host but the navigator's own. Usage:
//   NODE_PATH=/home/brendan/Claude_sandbox/node_modules node navigator/shoot_stage3.js http://127.0.0.1:8793/?t=<token> <out dir> <run id>
// Serve it with: python3 -m navigator.tests.demo_stage2 --port 8793 --workdir <tmp> --runs <the runs directory holding the run>  (fakes for spawner and board; nothing starts)
const puppeteer = require('puppeteer');
const fs = require('fs');
const [url, out, runId] = [process.argv[2], process.argv[3], process.argv[4]];
const origin = new URL(url).origin;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await puppeteer.launch({ headless: 'new', executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--use-gl=swiftshader', '--mute-audio'] });
  const report = { errors: [], blocked: [], overflow: [], shots: [], dialogs: [], requests: [] };
  for (const [w, h, tag] of [[1280, 900, 'wide'], [390, 844, 'phone']]) {
    const page = await browser.newPage();
    await page.setViewport({ width: w, height: h });
    await page.setRequestInterception(true);
    page.on('request', (r) => { if (r.url().startsWith(origin) || r.url().startsWith('data:') || r.url().startsWith('about:')) { if (r.url().includes('/api/console/')) report.requests.push(r.url().replace(origin, '').slice(0, 120)); r.continue(); } else { report.blocked.push(r.url()); r.abort(); } });
    page.on('pageerror', (e) => report.errors.push(tag + ' pageerror: ' + e.message));
    page.on('console', (m) => { if (m.type() === 'error') report.errors.push(tag + ' console: ' + m.text()); });
    page.on('dialog', async (d) => { report.dialogs.push(d.message().slice(0, 80)); await d.dismiss(); });
    report.requestsBefore = report.requests.length;                              // console requests are counted per viewport
    await page.goto(url, { waitUntil: 'networkidle0' });
    const shot = async (name) => {
      const f = `${out}/${name}_${tag}.png`;
      await page.screenshot({ path: f, fullPage: true });
      const sw = await page.evaluate(() => document.documentElement.scrollWidth);
      if (tag === 'phone' && sw > w + 1) report.overflow.push(`${name}: scrollWidth ${sw} > ${w}`);
      report.shots.push(f);
    };
    await page.evaluate(() => { location.hash = '#/live'; }); await sleep(1500);
    await page.evaluate((id) => { const r = [...document.querySelectorAll('tr.click')].find((x) => x.textContent.includes(id)); if (!r) throw new Error('no run ' + id); r.click(); }, runId); await sleep(2500);
    const before = report.requests.length - (report.requestsBefore || 0);
    await shot('live_status_panels');                                            // the console drawer is closed: no console request may have been made yet
    report.consoleRequestsWhileClosed = (report.consoleRequestsWhileClosed || 0) + before;
    await page.evaluate(() => { document.querySelector('details.console summary').click(); }); await sleep(3500);
    await shot('live_console_open');
    await page.evaluate(() => { document.querySelector('details.console summary').click(); }); await sleep(300);
    const n1 = report.requests.length; await sleep(5000); report.consoleRequestsAfterClose = report.requests.length - n1;     // closed again: no polling
    await page.close();
  }
  await browser.close();
  fs.writeFileSync(`${out}/shoot_report.json`, JSON.stringify(report, null, 1));
  console.log(JSON.stringify(report, null, 1));
  process.exit(report.errors.length || report.blocked.length || report.overflow.length || report.consoleRequestsWhileClosed || report.consoleRequestsAfterClose ? 1 : 0);
})();
