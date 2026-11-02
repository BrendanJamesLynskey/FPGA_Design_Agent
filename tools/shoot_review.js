// Screenshot a review page in both themes at desktop and phone width (brief 05d); reports page errors and overflow.
//   NODE_PATH=/home/brendan/Claude_sandbox/node_modules node tools/shoot_review.js page.html out_prefix
const puppeteer = require('puppeteer');
(async () => {
  const [page_, prefix] = process.argv.slice(2);
  const b = await puppeteer.launch({headless: 'new', args: ['--no-sandbox']});
  const out = [];
  for (const scheme of ['light', 'dark']) for (const [w, h, tag] of [[1100, 900, 'desktop'], [390, 800, 'phone']]) {
    const p = await b.newPage();
    const errs = [];
    p.on('pageerror', e => errs.push(String(e)));
    await p.setViewport({width: w, height: h});
    await p.emulateMediaFeatures([{name: 'prefers-color-scheme', value: scheme}]);
    await p.setRequestInterception(true);
    p.on('request', r => (r.url().startsWith('file:') || r.url().startsWith('data:')) ? r.continue() : r.abort());
    await p.goto('file://' + require('path').resolve(page_), {waitUntil: 'domcontentloaded'});
    const over = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    await p.screenshot({path: `${prefix}_${scheme}_${tag}.png`, fullPage: true});
    out.push({scheme, tag, pageErrors: errs.length, horizontalOverflowPx: over});
    await p.close();
  }
  await b.close();
  console.log(JSON.stringify(out));
})();
