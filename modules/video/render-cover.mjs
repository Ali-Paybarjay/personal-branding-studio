// عکس کاور ریلز (فاز ۶ تدوین ویدیو): cover/cover.html → JPEG با Chrome خود مک (playwright-core).
// ورودی (stdin، JSON): {html: "<مسیر cover.html>", out: "<مسیر jpg>", w: 1080, h: 1920, chrome?}
// صفحه خودش فونت و عکس را بار می‌کند و اندازه‌ی تیتر را جا می‌اندازد، بعد body[data-ready=1] می‌گذارد.
// هیچ درخواست شبکه‌ای جز فایل‌های محلی رد نمی‌شود. خروجی: {ok:true} یا {ok:false, error}
import fs from "fs";
import { pathToFileURL } from "url";
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");

const inp = JSON.parse(fs.readFileSync(0, "utf8"));
const CHROME = inp.chrome || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const out = o => process.stdout.write(JSON.stringify(o));

let browser;
try {
  browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ["--force-color-profile=srgb", "--hide-scrollbars"] });
  const page = await browser.newPage({ viewport: { width: inp.w, height: inp.h }, deviceScaleFactor: 1 });
  await page.route(/^https?:/, r => r.abort());
  await page.goto(pathToFileURL(inp.html).href, { waitUntil: "load" });
  await page.waitForFunction(() => document.body && document.body.dataset.ready === "1", null, { timeout: 20000 });
  await page.screenshot({ path: inp.out, type: "jpeg", quality: 92, clip: { x: 0, y: 0, width: inp.w, height: inp.h } });
  out({ ok: true });
} catch (e) {
  out({ ok: false, error: String(e && e.message || e).slice(0, 300) });
} finally {
  if (browser) await browser.close().catch(() => {});
}
