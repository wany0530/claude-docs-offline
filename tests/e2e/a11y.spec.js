// 접근성: axe-core 의 WCAG 2 A/AA 자동 검사와, 자동 검사로는 알 수 없는 키보드 동작.
const AxeBuilder = require("@axe-core/playwright").default;
const { test, expect, tabTo } = require("./base");

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"];

async function violations(page) {
  const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return r.violations.map((v) => `${v.id} [${v.impact}] ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
}

for (const scheme of ["light", "dark"]) {
  test.describe(`axe (${scheme} 테마)`, () => {
    test.use({ colorScheme: scheme });

    for (const url of ["/en/guide.html", "/ko/guide.html", "/en/reference.html", "/ko/nokorean.html", "/en/api.html", "/en/changes.html", "/ko/changes.html"]) {
      test(`${url}: WCAG 위반 없음`, async ({ page }) => {
        await page.goto(url);
        expect(await violations(page)).toEqual([]);
      });
    }

    for (const lang of ["en", "ko"]) {
      test(`${lang}: 검색 창을 연 상태`, async ({ page }) => {
        await page.goto(`/${lang}/guide.html`);
        await page.keyboard.press("Control+k");
        await page.locator("#searchmodal input").fill(lang === "en" ? "zebra" : "얼룩말");
        await page.locator("#searchmodal a.hit").first().waitFor();
        expect(await violations(page)).toEqual([]);
      });
    }

    test("좁은 화면(390px): 닫힌 상태와 메뉴를 연 상태", async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 800 });
      await page.goto("/en/guide.html");
      expect(await violations(page), "메뉴 닫힘").toEqual([]);
      await page.locator("#navtoggle").click();
      await expect(page.locator("body")).toHaveClass(/navopen/);
      await page.waitForTimeout(300); // 슬라이드 전환이 끝난 뒤 측정
      expect(await violations(page), "메뉴 열림").toEqual([]);
    });
  });
}

test.describe("키보드", () => {
  test.beforeEach(async ({ page }) => { await page.goto("/en/guide.html"); });

  test("첫 Tab 은 '본문으로 건너뛰기'이고, Enter 로 본문에 포커스가 옮겨진다", async ({ page }) => {
    await page.keyboard.press("Tab");
    await expect(page.locator(".skip")).toBeFocused();
    expect(await page.locator(".skip").boundingBox().then((b) => b.y)).toBeGreaterThanOrEqual(0); // 포커스되면 화면 안에 보인다
    await page.keyboard.press("Enter");
    await expect(page.locator("main#content")).toBeFocused();
    await expect(page).toHaveURL(/#content$/);
  });

  test("키보드로 닿은 요소에는 포커스 표시(윤곽선)가 있다", async ({ page }) => {
    for (const sel of [".skip", "#navtoggle, #searchbtn", ".tab-btn", "#nav a.leaf"]) {
      await page.evaluate(() => document.activeElement && document.activeElement.blur());
      await page.goto("/en/guide.html");
      await tabTo(page, sel);
      const outline = await page.evaluate(() => { const s = getComputedStyle(document.activeElement); return [s.outlineStyle, parseFloat(s.outlineWidth)]; });
      expect(outline[0], `${sel} 의 outline-style`).not.toBe("none");
      expect(outline[1], `${sel} 의 outline-width`).toBeGreaterThan(0);
    }
  });

  test("본문 탭: 선택된 탭만 Tab 으로 들어가고 화살표·Home·End 로 이동하며 선택된다", async ({ page }) => {
    const tabs = page.locator(".tab-btn");
    await tabTo(page, ".tab-btn");
    await expect(tabs.nth(0)).toBeFocused();
    expect(await tabs.evaluateAll((els) => els.map((e) => e.tabIndex))).toEqual([0, -1]); // roving tabindex
    await page.keyboard.press("ArrowRight");
    await expect(tabs.nth(1)).toBeFocused();
    await expect(tabs.nth(1)).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".tab-panel").nth(1)).toHaveClass(/active/);
    expect(await tabs.evaluateAll((els) => els.map((e) => e.tabIndex))).toEqual([-1, 0]);
    await page.keyboard.press("ArrowRight"); // 끝에서 처음으로
    await expect(tabs.nth(0)).toBeFocused();
    await page.keyboard.press("End");
    await expect(tabs.nth(1)).toBeFocused();
    await page.keyboard.press("Home");
    await expect(tabs.nth(0)).toBeFocused();
    await page.keyboard.press("ArrowLeft"); // 처음에서 끝으로
    await expect(tabs.nth(1)).toBeFocused();
    await expect(page.locator("#tab1-1")).toHaveAttribute("aria-labelledby", "tab1-1-tab");
  });

  test("검색: 화살표로 결과를 오가고 Tab 은 창 안에서만 돌며 Esc 는 열던 곳으로 되돌린다", async ({ page }) => {
    await page.locator("#searchbtn").focus();
    await page.keyboard.press("Control+k");
    const modal = page.locator("#searchmodal");
    await expect(modal.locator("input")).toBeFocused();
    await expect(modal.locator("[role=dialog]")).toHaveAttribute("aria-modal", "true");
    await modal.locator("input").fill("the");
    await modal.locator("a.hit").first().waitFor();
    const hits = modal.locator("a.hit");
    const n = await hits.count();
    expect(n).toBeGreaterThan(1);

    await page.keyboard.press("ArrowDown");
    await expect(hits.nth(0)).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(hits.nth(1)).toBeFocused();
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("ArrowUp");
    await expect(modal.locator("input")).toBeFocused(); // 첫 결과에서 위로 가면 입력창

    for (let i = 0; i < n + 3; i++) { // Tab 을 계속 눌러도 창 밖으로 나가지 않는다
      await page.keyboard.press("Tab");
      expect(await page.evaluate(() => !!document.activeElement.closest("#searchmodal")), `Tab ${i + 1}번째`).toBe(true);
    }
    await page.keyboard.press("Shift+Tab");
    expect(await page.evaluate(() => !!document.activeElement.closest("#searchmodal"))).toBe(true);

    await page.keyboard.press("Escape");
    await expect(modal).toBeHidden();
    await expect(page.locator("#searchbtn")).toBeFocused(); // 열기 전 위치로 복귀
  });

  test("검색 결과에서 Enter 를 누르면 그 페이지로 이동한다", async ({ page }) => {
    await page.keyboard.press("Control+k");
    await page.locator("#searchmodal input").fill("zebra");
    await page.locator("#searchmodal a.hit").first().waitFor();
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/en\/zebra\.html#zebra-stripes$/);
  });
});

test.describe("좁은 화면에서의 메뉴 버튼과 접는 목차", () => {
  test.use({ viewport: { width: 390, height: 800 } });

  test("메뉴 버튼의 aria-expanded 가 열림/닫힘을 따른다", async ({ page }) => {
    await page.goto("/en/guide.html");
    const toggle = page.locator("#navtoggle");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  test("우측 목차가 숨는 대신 본문 위에 접는 목차가 나온다", async ({ page }) => {
    await page.goto("/en/guide.html");
    const inline = page.locator("details.toc-inline");
    await expect(page.locator("#toc")).toBeHidden();
    await expect(inline).toBeVisible();
    await expect(inline.locator("summary")).toHaveText("On this page");
    await expect(inline).not.toHaveJSProperty("open", true); // 처음엔 접혀 있다
    const same = await page.evaluate(() => [document.querySelectorAll("#toc li").length, document.querySelectorAll(".toc-inline li").length]);
    expect(same[1]).toBe(same[0]); // 우측 목차와 같은 항목
    await inline.locator("summary").click();
    await expect(inline).toHaveJSProperty("open", true);
    await inline.locator("a[href='#json-example']").click();
    await expect(page).toHaveURL(/#json-example$/);
    await expect(inline).not.toHaveJSProperty("open", true); // 이동하면 다시 접힌다
  });
});

test("넓은 화면에서는 접는 목차가 보이지 않는다", async ({ page }) => {
  await page.goto("/en/guide.html");
  await expect(page.locator("details.toc-inline")).toBeHidden();
  await expect(page.locator("#toc")).toBeVisible();
});
