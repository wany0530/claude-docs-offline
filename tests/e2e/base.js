// E2E 공용: 콘솔 오류가 있으면 모든 테스트가 실패하는 test 와 도우미
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const base = require("@playwright/test");
const { expect } = base;

const test = base.test.extend({
  page: async ({ page }, use) => {
    const errors = [];
    page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text() + " @ " + (m.location().url || "")); });
    await use(page);
    // 헤드리스 Chromium 은 파비콘을 요청하지 않아 favicon.ico 404 는 여기서 잡히지 않는다. 파비콘 링크는 tests/test_site.py 가 지킨다.
    expect(errors, "콘솔 오류").toEqual([]);
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
