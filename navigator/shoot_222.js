// Headless check of the permission views (brief 222): the Permissions page (modes, the per-action table, the fixed never-list), the Start page's mode picker, and the Live
// page's permission question, at 1280 and 390 px. Zero page errors, no horizontal overflow at 390 px, no request to any host but the navigator's own. Usage:
//   NODE_PATH=/home/brendan/Claude_sandbox/node_modules node navigator/shoot_222.js http://127.0.0.1:8795/?t=<token> <out dir> <run id>
// Serve it with: python3 -m navigator.tests.demo_222 --port 8795 --workdir <tmp>  (fakes for spawner and board; the settings are saved in <tmp>, nothing starts)
const puppeteer = require('puppeteer');
const fs = require('fs');
const [url, out, runId] = [process.argv[2], process.argv[3], process.argv[4]];
const origin = new URL(url).origin;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await puppeteer.launch({ headless: 'new', executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--use-gl=swiftshader', '--mute-audio'] });
  const report = { errors: [], blocked: [], overflow: [], shots: [], dialogs: [], checks: [] };
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
    // 1. the Permissions page, default settings (Ask)
    await page.evaluate(() => { location.hash = '#/permissions'; }); await sleep(1500);
    await shot('permissions_default');
    // 2. pick Auto, override run_vivado to deny, save for a project, and read it back
    await page.evaluate(() => { const s = document.querySelector('select[aria-label="Project"]'); s.value = 'c10_dds_sine'; s.dispatchEvent(new Event('change')); }); await sleep(1200);
    await page.evaluate(() => { [...document.querySelectorAll('button[aria-pressed]')].find((b) => b.textContent === 'Auto within limits').click(); }); await sleep(400);
    await page.evaluate(() => { const s = document.querySelector('select[aria-label="Override for Run Vivado synthesis and implementation"]'); s.value = 'deny'; s.dispatchEvent(new Event('change')); }); await sleep(400);
    await shot('permissions_auto_with_deny');
    await page.evaluate(() => { [...document.querySelectorAll('button')].find((b) => b.textContent.startsWith('Save for')).click(); }); await sleep(1500);
    report.checks.push({ saved_text: await page.evaluate(() => (document.querySelector('[role=status]') || {}).textContent || null) });
    // 3. the Start page shows the saved mode for that task
    await page.evaluate(() => { location.hash = '#/start'; }); await sleep(1500);
    await page.evaluate(() => { const s = document.querySelector('select'); });
    report.checks.push({ start_picker: await page.evaluate(() => { const s = document.querySelector('select[aria-label="Permission mode"]'); return s ? s.options[0].textContent : null; }) });
    await shot('start_with_mode_picker');
    // 4. the Live page: the run waiting for a permission
    await page.evaluate(() => { location.hash = '#/live'; }); await sleep(1500);
    await page.evaluate((id) => { const r = [...document.querySelectorAll('tr.click')].find((x) => x.textContent.includes(id)); if (!r) throw new Error('no run ' + id); r.click(); }, runId); await sleep(2500);
    report.checks.push({ live_question: await page.evaluate(() => { const q = document.getElementById('perm-question'); return q ? q.textContent.slice(0, 160) : null; }) });
    await shot('live_permission_question');
    await page.close();
  }
  await browser.close();
  fs.writeFileSync(`${out}/shoot_report.json`, JSON.stringify(report, null, 1));
  console.log(JSON.stringify(report, null, 1));
  process.exit(report.errors.length || report.blocked.length || report.overflow.length || report.checks.some((c) => Object.values(c).some((v) => v === null)) ? 1 : 0);
})();
