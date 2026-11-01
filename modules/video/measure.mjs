// پهنای واقعی متن با فونت زیرنویس، با شکل‌دهی فارسی (حروف چسبیده) از fontkit.
// ورودی (stdin): {"weight":800,"texts":["سلام", ...]}   خروجی: {"سلام": 2.035, ...}  (بر حسب em)
// fontkit روی نسخه‌ی متغیر WOFF2 خطا می‌دهد (getVariation → cmap)، برای همین از همان فونت نسخه‌های ثابت ۸۰۰ و ۹۰۰ ساخته شده:
//   uvx --from 'fonttools[woff]' fonttools ttLib.woff2 decompress … ; fonttools varLib.instancer … wght=800
// اندازه‌ها با Chrome حداکثر حدود ۵٪ فرق دارند؛ موتور ۶٪ حاشیه می‌گذارد.
import fs from "fs";
import { createRequire } from "module";
import { fileURLToPath } from "url";
const require = createRequire(import.meta.url);
const fontkit = require("fontkit");

const inp = JSON.parse(fs.readFileSync(0, "utf8"));
const weight = inp.weight >= 850 ? 900 : 800;
// fileURLToPath، نه .pathname: مسیر «Content Studio» فاصله دارد و pathname آن را %20 می‌کند
const font = fontkit.openSync(fileURLToPath(new URL(`./fonts/Vazirmatn-${weight}.ttf`, import.meta.url)));
const out = {};
for (const t of inp.texts || []) out[t] = Math.round((font.layout(t).advanceWidth / font.unitsPerEm) * 10000) / 10000;
process.stdout.write(JSON.stringify(out));
