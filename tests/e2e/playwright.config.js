// 브라우저 E2E 설정. 고정 사이트(build_fixture.py)를 만들고 python http.server 로 띄운 뒤 Chromium 으로 확인한다.
// 사이트 자체는 서버 없이 file:// 로도 열려야 하므로 같은 사이트를 file:// 로도 연다 (spec 의 file:// 테스트).
const { defineConfig, devices } = require("@playwright/test");

const PY = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const PORT = 4173;

module.exports = defineConfig({
  testDir: __dirname,
  testMatch: "*.spec.js",
  timeout: 30000,
  expect: { timeout: 7000 },
  fullyParallel: true,
  reporter: [["list"]],
  outputDir: "test-results",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: {
    // 사이트를 먼저 만들고(&&) 그 폴더를 서빙한다. 순서가 보장되도록 한 명령으로 묶었다.
    command: `${PY} build_fixture.py && ${PY} -m http.server ${PORT} --bind 127.0.0.1 --directory .site`,
    url: `http://127.0.0.1:${PORT}/index.html`,
    reuseExistingServer: false,
    timeout: 60000,
    cwd: __dirname,
  },
});
