// E2E 가 실행한 JS 의 커버리지를 합쳐 site_src 부분(lib/app/search/highlight)별로 보고한다.
// 사용: npm run coverage   (JS_COVERAGE=1 로 E2E 를 돌리고 이 스크립트를 실행)
// V8 의 블록 커버리지: 범위는 바깥에서 안쪽으로 겹치며 가장 안쪽 범위의 실행 횟수가 이긴다. 주석·공백은 세지 않는다.
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..", "..");
const DIR = path.join(__dirname, "test-results", "js-coverage");
const minArg = process.argv.find((a) => a.startsWith("--min="));
const MIN = minArg ? Number(minArg.slice(6)) : null;

// 사이트의 nav.js 는 site_src 의 JS 부분을 이 순서로 "\n" 으로 이어 붙인 것이다 (docs_site.JS_PARTS 와 같은 순서)
const siteModule = fs.readFileSync(path.join(ROOT, "docs_site.py"), "utf8");
const names = [...siteModule.match(/JS_PARTS = \(([^)]*)\)/)[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
const texts = names.map((n) => fs.readFileSync(path.join(ROOT, "site_src", n), "utf8").replace(/\r\n/g, "\n"));
const joined = texts.join("\n");

const covered = new Uint8Array(joined.length);
let runs = 0;
for (const file of fs.existsSync(DIR) ? fs.readdirSync(DIR) : []) {
  for (const entry of JSON.parse(fs.readFileSync(path.join(DIR, file), "utf8"))) {
    if (entry.length !== joined.length) {
      console.error(`경고: ${file} 의 nav.js(${entry.length}자)가 site_src 를 이은 것(${joined.length}자)과 다릅니다. 사이트를 다시 만드세요.`);
      continue;
    }
    const ranges = entry.functions.flatMap((f) => f.ranges).sort((a, b) => a.startOffset - b.startOffset || b.endOffset - a.endOffset);
    const cov = new Uint8Array(joined.length);
    for (const r of ranges) cov.fill(r.count > 0 ? 1 : 0, r.startOffset, r.endOffset);
    for (let i = 0; i < cov.length; i++) if (cov[i]) covered[i] = 1;
    runs++;
  }
}
if (!runs) {
  console.error("커버리지 데이터가 없습니다. npm run coverage 로 실행하세요.");
  process.exit(1);
}

// 주석(/* ... */)과 공백은 코드가 아니므로 센 대상에서 뺀다
const skip = new Uint8Array(joined.length);
for (const m of joined.matchAll(/\/\*[\s\S]*?\*\/|\s+/g)) skip.fill(1, m.index, m.index + m[0].length);

let offset = 0, totalCode = 0, totalCov = 0;
const lineOf = (text, pos) => text.slice(0, pos).split("\n").length;
console.log(`E2E ${runs}개 실행의 JS 커버리지 (site_src 기준, 주석·공백 제외)`);
for (let k = 0; k < names.length; k++) {
  const text = texts[k];
  let code = 0, cov = 0;
  const gaps = [];
  let gapStart = -1;
  for (let i = 0; i < text.length; i++) {
    const g = offset + i;
    if (skip[g]) continue;
    code++;
    if (covered[g]) {
      cov++;
      if (gapStart >= 0) { gaps.push([gapStart, i]); gapStart = -1; }
    } else if (gapStart < 0) gapStart = i;
  }
  if (gapStart >= 0) gaps.push([gapStart, text.length]);
  totalCode += code; totalCov += cov;
  console.log(`  ${names[k].padEnd(14)} ${((100 * cov) / code).toFixed(1).padStart(5)}%  (${cov}/${code}자)`);
  const big = gaps.filter(([a, b]) => text.slice(a, b).replace(/\s+/g, "").length >= 30).slice(0, 12);
  for (const [a, b] of big) {
    console.log(`      안 실행: ${names[k]}:${lineOf(text, a)}  ${text.slice(a, b).replace(/\s+/g, " ").slice(0, 90)}`);
  }
  offset += text.length + 1;
}
const pct = (100 * totalCov) / totalCode;
console.log(`  합계           ${pct.toFixed(1).padStart(5)}%`);
if (MIN !== null && pct < MIN) {
  console.error(`하한 ${MIN}% 미만입니다.`);
  process.exit(1);
}
