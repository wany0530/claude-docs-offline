// 오프라인 사이트의 브라우저 동작 E2E. 고정 사이트(build_fixture.py)를 Chromium 으로 연다.
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const base = require("@playwright/test");
const { expect } = base;

// 모든 테스트에서 콘솔 오류와 페이지 예외가 없어야 한다.
const test = base.test.extend({
  page: async ({ page }, use) => {
    const errors = [];
    page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
    page.on("console", (m) => {
      if (m.type() !== "error") return;
      if (/favicon\.ico/.test(m.location().url || "")) return; // TODO(4단계): 파비콘을 넣으면 이 예외를 지운다
      errors.push(m.text());
    });
    await use(page);
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

const T = {
  en: {
    guide: "Guide", tabs: ["Guides", "Reference"], activeTab: "Guides", firstToc: "Overview section", lastToc: "Long section 4",
    tocTitle: "On this page", filter: "adv", filterHit: "Advanced topic", jsonHeading: "JSON example",
    search: "zebra", hit: "Zebra stripes", none: "No page contains all words", matches: /1 page\(s\) match/,
    copied: "Copied", switchTo: "한국어",
  },
  ko: {
    guide: "가이드", tabs: ["가이드", "레퍼런스"], activeTab: "가이드", firstToc: "개요 섹션", lastToc: "긴 섹션 4",
    tocTitle: "이 페이지에서", filter: "고급", filterHit: "고급 주제", jsonHeading: "JSON 예시",
    search: "얼룩말", hit: "얼룩말 줄무늬", none: "모든 단어를 포함한 페이지가 없습니다", matches: /1개 페이지 일치/,
    copied: "복사됨", switchTo: "English",
  },
};

test("index.html 은 영어 첫 페이지로 이동한다", async ({ page }) => {
  await page.goto("/index.html");
  await expect(page).toHaveURL(/\/en\/guide\.html$/);
});

for (const lang of ["en", "ko"]) {
  const t = T[lang];
  test.describe(`${lang} 사이트`, () => {
    test.beforeEach(async ({ page }) => {
      await stubClipboard(page);
      await page.goto(`/${lang}/guide.html`);
    });

    test("상단 탭, 사이드바 현재 페이지, 필터", async ({ page }) => {
      await expect(page.locator("#tabs a")).toHaveText(t.tabs);
      await expect(page.locator("#tabs a.active")).toHaveText(t.activeTab);
      await expect(page.locator("#nav a.leaf[aria-current='page']")).toHaveText(t.guide);
      const before = await page.locator("#nav a.leaf:visible").count();
      expect(before).toBe(3); // 하위 그룹(Deep)은 현재 페이지가 그 안에 없으면 접혀 있다
      await page.locator("#nav input").fill(t.filter);
      await expect(page.locator("#nav a.leaf:visible")).toHaveText([t.filterHit]); // 하위 그룹도 펼쳐져 보인다
      await page.locator("#nav input").fill("");
      await expect(page.locator("#nav a.leaf:visible")).toHaveCount(before);
    });

    test("언어 전환은 같은 페이지의 다른 언어판으로 간다", async ({ page }) => {
      await page.locator("details.lang summary").click();
      await page.locator("details.lang .menu a", { hasText: t.switchTo }).click();
      const other = lang === "en" ? "ko" : "en";
      await expect(page).toHaveURL(new RegExp(`/${other}/guide\\.html$`));
      await expect(page.locator("html")).toHaveAttribute("lang", other);
    });

    test("우측 목차: 항목, 클릭 이동, 스크롤 추적", async ({ page }) => {
      await expect(page.locator("#toc h6")).toHaveText(t.tocTitle);
      const items = page.locator("#toc li a");
      await expect(items.first()).toHaveText(t.firstToc);
      await expect(items.last()).toHaveText(t.lastToc);
      const inArticle = await page.evaluate(
        () => [...document.querySelectorAll("article h2[id],article h3[id]")].filter((h) => !h.closest(".tab-panel,details")).length);
      await expect(items).toHaveCount(inArticle); // 탭 안의 제목은 목차에 넣지 않는다 (닫힌 탭이면 이동이 안 되므로)

      await page.evaluate(() => document.getElementById("json-example").scrollIntoView());
      await expect(page.locator("#toc a[aria-current]")).toHaveText(t.jsonHeading);
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      await expect(page.locator("#toc a[aria-current]")).toHaveText(t.lastToc); // 맨 아래면 마지막 항목
    });

    test("목차 항목을 누르면 그 제목이 고정 헤더 아래에 보인다", async ({ page }) => {
      await page.locator("#toc a[href='#json-example']").click();
      await expect(page).toHaveURL(/#json-example$/);
      await expect.poll(async () => Math.round((await page.locator("#json-example").boundingBox()).y)).toBeGreaterThan(100);
      await expect.poll(async () => Math.round((await page.locator("#json-example").boundingBox()).y)).toBeLessThan(220);
    });

    test("본문 탭 전환과 숨은 탭 안의 앵커 이동", async ({ page }) => {
      const panels = page.locator(".tab-panel");
      await expect(panels.nth(0)).toHaveClass(/active/);
      await expect(panels.nth(1)).not.toHaveClass(/active/);
      await page.locator(".tab-btn", { hasText: "Windows" }).click();
      await expect(panels.nth(1)).toHaveClass(/active/);
      await expect(page.locator(".tab-btn", { hasText: "Windows" })).toHaveAttribute("aria-selected", "true");

      await page.goto(`/${lang}/guide.html#windows-only-heading`); // 닫힌 탭 안의 제목으로 바로 이동
      await expect(page.locator("#windows-only-heading")).toBeVisible();
    });

    test("끊긴 링크는 표시되고 앵커 없이 페이지 처음으로 간다", async ({ page }) => {
      const stale = page.locator("a.stale-anchor");
      await expect(stale).toHaveCount(1);
      await expect(stale).toHaveAttribute("href", "reference.html");
      await expect(stale).toHaveAttribute("title", /.+/);
      await stale.click();
      await expect(page).toHaveURL(new RegExp(`/${lang}/reference\\.html$`));
      expect(await page.evaluate(() => window.scrollY)).toBe(0);
    });

    test("아코디언을 가리키는 링크가 아코디언을 연다", async ({ page }) => {
      await page.locator("article a[href$='reference.html#how-it-works']").click();
      await expect(page).toHaveURL(/reference\.html#how-it-works$/);
      await expect(page.locator("details#how-it-works")).toHaveJSProperty("open", true);
      await expect.poll(async () => Math.round((await page.locator("details#how-it-works").boundingBox()).y)).toBeGreaterThan(100);
    });

    test("코드 구문 강조: JSON 키는 문자열과 다른 색(tk-key), bash 주석", async ({ page }) => {
      const json = page.locator("pre[data-lang='json']");
      await expect(json.locator(".tk-key")).toHaveCount(3); // 키가 키로 칠해진다 (예전에는 0개였던 버그)
      await expect(json.locator(".tk-s")).toHaveCount(1);
      await expect(json.locator(".tk-n")).toHaveCount(1);
      await expect(json.locator(".tk-k")).toHaveCount(1);
      await expect(page.locator("pre[data-lang='bash'] .tk-c")).toHaveCount(1);
    });

    test("코드 복사와 페이지 복사 버튼", async ({ page }) => {
      const btn = page.locator("pre[data-lang='json'] button.copy");
      await btn.click();
      expect(await page.evaluate(() => window.__copied)).toBe('{"name": "demo", "count": 3, "ok": true}');
      await expect(btn).toHaveText(t.copied);
      await expect(btn.locator("svg")).toHaveCount(1); // 잠시 뒤 아이콘으로 돌아온다

      await page.locator("#copypage").click();
      const md = await page.evaluate(() => window.__copied);
      expect(md).toContain(lang === "en" ? "# Guide" : "# 가이드");
      expect(md).not.toContain("Documentation Index"); // 안내 배너는 빠진 원문
    });

    test("검색: 열기, 결과, 강조, 이동, 닫기, 일치 없음", async ({ page }) => {
      const indexRequests = [];
      page.on("request", (r) => { if (/search-data-/.test(r.url())) indexRequests.push(r.url()); });
      await page.keyboard.press("Control+k");
      const modal = page.locator("#searchmodal");
      await expect(modal).toBeVisible();
      await page.waitForTimeout(400);
      expect(indexRequests, "입력 전에는 색인을 받지 않는다").toEqual([]);

      await modal.locator("input").fill(t.search);
      await expect(modal.locator("a.hit").first()).toContainText(t.hit);
      await expect(modal.locator(".info")).toHaveText(t.matches);
      await expect(modal.locator("a.hit b mark").first()).toBeVisible();
      expect(indexRequests).toHaveLength(1);
      expect(indexRequests[0]).toContain(`search-data-${lang}.js`);

      await modal.locator("a.hit").first().click();
      await expect(page).toHaveURL(new RegExp(`/${lang}/zebra\\.html#zebra-stripes$`));

      await page.keyboard.press("Control+k");
      await expect(modal).toBeVisible();
      await modal.locator("input").fill("qqqzzzxxx");
      await expect(modal.locator(".info")).toHaveText(t.none);
      await page.keyboard.press("Escape");
      await expect(modal).toBeHidden();
    });

    test("레이아웃(1440px): 본문 폭 상한과 표 첫 열이 글자 단위로 줄바꿈되지 않음", async ({ page }) => {
      const article = await page.locator("article").boundingBox();
      expect(article.width).toBeLessThanOrEqual(800.5);
      const th = await page.locator("table th:first-child").boundingBox();
      expect(th.width).toBeGreaterThanOrEqual(100); // 예전에는 55px 로 눌려 한 글자씩 줄바꿈됐다
      // 첫 열의 글자가 몇 줄로 나뉘었는지: 셀 높이는 같은 행의 긴 셀을 따라 늘어나므로 텍스트 자체의 줄 수를 잰다
      const lines = await page.evaluate(() => {
        const range = document.createRange();
        range.selectNodeContents(document.querySelector("table td:first-child"));
        return new Set([...range.getClientRects()].map((r) => Math.round(r.top))).size;
      });
      expect(lines, "첫 열 텍스트의 줄 수").toBe(1);
      await expect(page.locator("#toc")).toBeVisible();
    });
  });
}

test("한국어판이 없는 페이지는 영어 원문과 안내 문구를 보여 준다", async ({ page }) => {
  await page.goto("/ko/nokorean.html");
  await expect(page.locator(".notice")).toContainText("공식 한국어판이 없어");
  await expect(page.locator("h1")).toContainText("No Korean"); // 제목 옆 # 링크 글자가 함께 있다
  await page.goto("/en/nokorean.html");
  await expect(page.locator(".notice")).toHaveCount(0);
});

for (const width of [320, 360, 390]) {
  test.describe(`좁은 화면(${width}px)`, () => {
    test.use({ viewport: { width, height: 800 } });

    for (const lang of ["en", "ko"]) {
      test(`${lang}: 가로 넘침 없음, 목차 숨김, 메뉴 토글`, async ({ page }) => {
        await page.goto(`/${lang}/guide.html`);
        // 헤더·본문·표·코드 어느 것도 페이지를 가로로 밀어내지 않는다 (예전에는 헤더가 17px 넘쳤다)
        const over = await page.evaluate(() => {
          const vw = document.documentElement.clientWidth;
          return [...document.querySelectorAll("#top *, #tabs, article > *")]
            .filter((e) => !e.closest("pre, .table-wrap, details.lang") && e.getBoundingClientRect().right > vw + 0.5)
            .map((e) => e.tagName.toLowerCase() + (e.id ? "#" + e.id : ""));
        });
        expect(over, "화면 오른쪽을 넘은 요소").toEqual([]);
        expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
        await expect(page.locator("#toc")).toBeHidden();
        await expect(page.locator("#navtoggle")).toBeVisible();
        expect((await page.locator("#nav").boundingBox()).x).toBeLessThan(0); // 화면 밖으로 접혀 있다
        await page.locator("#navtoggle").click();
        await expect(page.locator("body")).toHaveClass(/navopen/);
        await expect.poll(async () => (await page.locator("#nav").boundingBox()).x).toBeGreaterThanOrEqual(0);
      });
    }
  });
}

test.describe("1000px 이하에서는 우측 목차가 숨는다", () => {
  test.use({ viewport: { width: 1000, height: 800 } });
  test("목차 숨김", async ({ page }) => {
    await page.goto("/en/guide.html");
    await expect(page.locator("#toc")).toBeHidden();
  });
});

// 이 도구의 핵심 주장: 서버 없이 파일을 바로 열어도 동작한다 (검색 색인은 <script> 태그로 지연 로드).
test.describe("file:// 로 열기 (서버 없음)", () => {
  for (const lang of ["en", "ko"]) {
    test(`${lang}: 메뉴, 목차, 검색이 동작한다`, async ({ page }) => {
      await page.goto(fileUrl(`${lang}/guide.html`));
      await expect(page.locator("#tabs a")).toHaveCount(2); // nav-data-*.js 를 file:// 로 읽었다
      await expect(page.locator("#nav a.leaf").first()).toBeVisible();
      await expect(page.locator("#toc li a").first()).toBeVisible();
      await expect(page.locator("pre[data-lang='json'] .tk-key")).toHaveCount(3);

      await page.keyboard.press("Control+k");
      await page.locator("#searchmodal input").fill(T[lang].search);
      await expect(page.locator("#searchmodal a.hit").first()).toContainText(T[lang].hit); // search-data-*.js 지연 로드
      await page.locator("#searchmodal a.hit").first().click();
      await expect(page).toHaveURL(new RegExp(`${lang}/zebra\\.html#zebra-stripes$`));
    });
  }
});
