// Headless check of the stage 2 views (brief 103S2) against navigator/tests/demo_stage2.py (fake spawner, fake board transport): Start, Live, Board at 1280 and 390 px,
// zero page errors, no horizontal overflow at 390 px, no request to any host but the navigator's own. Usage:
//   NODE_PATH=/home/brendan/Claude_sandbox/node_modules node navigator/shoot_stage2.js http://127.0.0.1:8793/?t=<token> <out dir> <handoff dir>
const puppeteer = require('puppeteer');
const fs = require('fs');
const [url, out, handoff] = [process.argv[2], process.argv[3], process.argv[4]];
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
    page.on('dialog', async (d) => { report.dialogs.push(d.message().slice(0, 80)); await d.accept(); });
    await page.goto(url, { waitUntil: 'networkidle0' });
    const shot = async (name) => {
      const f = `${out}/${name}_${tag}.png`;
      await page.screenshot({ path: f, fullPage: true });
      const sw = await page.evaluate(() => document.documentElement.scrollWidth);
      if (tag === 'phone' && sw > w + 1) report.overflow.push(`${name}: scrollWidth ${sw} > ${w}`);
      report.shots.push(f);
    };
    const go = async (hash) => { await page.evaluate((x) => { location.hash = x; }, hash); await sleep(1500); };
    const clickText = async (sel, text) => { await page.evaluate((s, t) => { const b = [...document.querySelectorAll(s)].find((e) => e.textContent.includes(t)); if (!b) throw new Error('no ' + t); b.click(); }, sel, text); };
    if (tag === 'wide') { try { fs.unlinkSync(`${handoff}/board.lock`); } catch (e) {} }
    await go('#/start'); await shot('start_task');
    await page.select('.formgrid select', 'project'); await sleep(500); await shot('start_project');
    await page.select('.formgrid select', 'task'); await sleep(300);
    if (tag === 'wide') {
      await clickText('button', 'Start the run'); await sleep(1500); await shot('start_started');
      await clickText('button', 'Start the run'); await sleep(1500); await shot('start_refused_one_at_a_time');
    }
    await go('#/live'); await shot('live');
    await page.evaluate(() => { const r = [...document.querySelectorAll('tr.click')].find((x) => x.textContent.includes('demo') || x.textContent.includes('des')); if (r) r.click(); }); await sleep(1500); await shot('live_detail');
    await go('#/board'); await shot('board');
    await clickText('button', 'All four reads'); await sleep(2000); await shot('board_result');
    fs.writeFileSync(`${handoff}/board.lock`, '96F: board soak, 2026-11-20 17:00, expected end 19:00\n');
    await go('#/board'); await clickText('button', 'List JTAG targets'); await sleep(1500); await shot('board_refused_locked');
    fs.unlinkSync(`${handoff}/board.lock`);
    await go('#/timing'); await shot('timing_chains');
    await go('#/measure'); await sleep(1500); await shot('measure_table');
    await page.close();
  }
  await browser.close();
  fs.writeFileSync(`${out}/check.json`, JSON.stringify(report, null, 1));
  console.log(JSON.stringify({ shots: report.shots.length, errors: report.errors, blocked: report.blocked, overflow: report.overflow, dialogs: report.dialogs.length }, null, 1));
})();
