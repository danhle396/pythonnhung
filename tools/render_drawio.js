// Xuất file .drawio thành PNG bằng thư viện viewer của diagrams.net chạy trong Edge/Chrome headless
// (không cần cài draw.io desktop; cần Internet để tải viewer-static.min.js).
//   cd tools/slides && npm install && node ../render_drawio.js ../../docs/hardware/wiring.drawio [out.png]
// File nhiều trang → out-1.png, out-2.png, …
const fs = require('fs');
const path = require('path');
module.paths.unshift(path.join(__dirname, 'slides', 'node_modules'));
const puppeteer = require('puppeteer-core');

const src = path.resolve(process.argv[2]);
const out = path.resolve(process.argv[3] || src.replace(/\.drawio$/, '.png'));
const BROWSERS = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe', '/usr/bin/chromium', '/usr/bin/google-chrome'];

(async () => {
  const xml = fs.readFileSync(src, 'utf8');
  const pages = Math.max(1, (xml.match(/<diagram[\s>]/g) || []).length);
  let browser, lastErr;
  for (const exe of BROWSERS.filter(p => fs.existsSync(p))) {  // thử lần lượt (Edge có thể lỗi khi đang tự cập nhật)
    try { browser = await puppeteer.launch({executablePath: exe, headless: true}); break; } catch (e) { lastErr = e; }
  }
  if (!browser) throw lastErr || new Error('Không tìm thấy Edge/Chrome');
  for (let i = 0; i < pages; i++) {
    const page = await browser.newPage();  // mỗi trang một tab mới
    await page.setViewport({width: 2000, height: 1500, deviceScaleFactor: 2});
    const cfg = JSON.stringify({highlight: '#0000ff', nav: false, resize: true, toolbar: '', edit: null, page: i, xml});
    const html = `<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0;background:#fff">
      <div class="mxgraph" style="max-width:100%;" data-mxgraph="${cfg.replace(/&/g, '&amp;').replace(/"/g, '&quot;')}"></div>
      <script src="https://viewer.diagrams.net/js/viewer-static.min.js"></script></body></html>`;
    await page.setContent(html, {waitUntil: 'networkidle0', timeout: 60000});
    await page.waitForSelector('.mxgraph svg', {timeout: 30000});
    await new Promise(r => setTimeout(r, 1000));
    const file = pages > 1 ? out.replace(/\.png$/, `-${i + 1}.png`) : out;
    await (await page.$('.mxgraph svg')).screenshot({path: file});
    console.log('Đã ghi', file);
    await page.close();
  }
  await browser.close().catch(() => {});  // Windows đôi khi khoá profile tạm (EBUSY) — không ảnh hưởng ảnh đã ghi
  process.exit(0);
})().catch(e => { console.error('FAIL', e.message); process.exit(1); });
