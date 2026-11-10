// Render mọi khối ```mermaid trong docs/architecture/*.md thành PNG (cho báo cáo Word / slide).
//   cd tools/slides && npm install && node ../render_mermaid.js [đường_dẫn_trình_duyệt]
// Mặc định dùng Microsoft Edge/Chrome có sẵn trên máy (không tải Chromium).
const fs = require('fs');
const path = require('path');
module.paths.unshift(path.join(__dirname, 'slides', 'node_modules')); // dùng chung node_modules với tools/slides
const puppeteer = require('puppeteer-core');

const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, 'docs', 'report', 'figures', 'diagrams');
const BROWSERS = [
  process.argv[2],
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/usr/bin/chromium', '/usr/bin/google-chrome',
].filter(Boolean);

const slug = s => s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd')
  .replace(/[^a-z0-9]+/g, '_').slice(0, 40).replace(/^_+|_+$/g, '');

function blocks(file) {
  const txt = fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n');
  const out = [];
  const re = /^##\s+(.+)$|```mermaid\n([\s\S]*?)```/gm;
  let title = path.basename(file, '.md'), m;
  while ((m = re.exec(txt))) {
    if (m[1]) title = m[1].trim();
    else out.push({name: slug(title), code: m[2]});
  }
  return out;
}

(async () => {
  fs.mkdirSync(OUT, {recursive: true});
  const mermaidJs = require.resolve('mermaid/dist/mermaid.min.js');
  const exe = BROWSERS.find(p => fs.existsSync(p));
  const browser = await puppeteer.launch({executablePath: exe, headless: true});
  const page = await browser.newPage();
  await page.setViewport({width: 1800, height: 1200, deviceScaleFactor: 2});
  await page.setContent('<html><body style="margin:0;background:#fff"><div id="c"></div></body></html>');
  await page.addScriptTag({path: mermaidJs});
  await page.evaluate(() => mermaid.initialize({startOnLoad: false, theme: 'neutral',
    fontFamily: 'Arial, sans-serif', flowchart: {htmlLabels: true, curve: 'basis'}, sequence: {useMaxWidth: false}}));
  const dir = path.join(ROOT, 'docs', 'architecture');
  for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.md'))) {
    for (const b of blocks(path.join(dir, f))) {
      const svg = await page.evaluate(async (code, id) => (await mermaid.render(id, code)).svg, b.code, 'm' + b.name);
      await page.evaluate(s => { document.getElementById('c').innerHTML = s; }, svg);
      const el = await page.$('#c svg');
      await page.evaluate(e => { e.style.maxWidth = 'none'; e.style.background = '#fff'; }, el);
      const file = path.join(OUT, b.name + '.png');
      await el.screenshot({path: file, omitBackground: false});
      console.log('ok', path.relative(ROOT, file));
    }
  }
  await browser.close();
})().catch(e => { console.error('FAIL', e); process.exit(1); });
