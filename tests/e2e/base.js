// E2E 공용: 콘솔 오류가 있으면 모든 테스트가 실패하는 test 와 도우미
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const base = require("@playwright/test");
const { expect } = base;

// JS_COVERAGE=1 이면 Chromium 의 JS 커버리지를 수집해 test-results/js-coverage/ 에 남긴다 (npm run coverage 가 합쳐서 보고한다)
const COVERAGE = process.env.JS_COVERAGE === "1";
const COVERAGE_DIR = path.join(__dirname, "test-results", "js-coverage");

const test = base.test.extend({
  // 일부러 실패를 일으키는 테스트가 예상하는 콘솔 오류(정규식 목록). 기본은 없음: 모든 콘솔 오류는 실패다.
  allowedConsoleErrors: [[], { option: true }],
  page: async ({ page, allowedConsoleErrors }, use, testInfo) => {
    const errors = [];
    page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text() + " @ " + (m.location().url || "")); });
    if (COVERAGE) await page.coverage.startJSCoverage({ resetOnNavigation: false });
    await use(page);
    if (COVERAGE) {
      const entries = (await page.coverage.stopJSCoverage()).filter((e) => /\/nav\.js$/.test(e.url));
      fs.mkdirSync(COVERAGE_DIR, { recursive: true });
      fs.writeFileSync(path.join(COVERAGE_DIR, testInfo.testId + ".json"),
        JSON.stringify(entries.map((e) => ({ url: e.url, length: e.source.length, functions: e.functions }))));
    }
    // 헤드리스 Chromium 은 파비콘을 요청하지 않아 favicon.ico 404 는 여기서 잡히지 않는다. 파비콘 링크는 tests/test_site.py 가 지킨다.
    expect(errors.filter((e) => !allowedConsoleErrors.some((re) => re.test(e))), "콘솔 오류").toEqual([]);
  },
});

const SITE = path.join(__dirname, ".site");
const fileUrl = (rel) => pathToFileURL(path.join(SITE, rel)).href;

// 클립보드 쓰기를 가로채 복사된 값을 확인한다 (브라우저의 권한 창 없이).
async function stubClipboard(page) {
  await page.addInitScript(() => {
    window.__copied = null;
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: (t) => { window.__copied = t; return Promise.resolve(); } },
    });
  });
}

// Tab 키를 눌러 selector 에 맞는 요소에 포커스가 올 때까지 이동한다 (키보드 사용자와 같은 경로).
async function tabTo(page, selector, max = 120) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    if (await page.evaluate((sel) => document.activeElement && document.activeElement.matches(sel), selector)) return i + 1;
  }
  throw new Error(`Tab ${max}번으로 ${selector} 에 닿지 못함`);
}

module.exports = { test, expect, fileUrl, stubClipboard, tabTo, SITE };
