// JS 커버리지를 켜고 E2E 를 돌린 뒤 보고한다 (운영체제와 무관하게 동작하도록 npm 스크립트 대신 Node 로 묶었다).
const { spawnSync } = require("node:child_process");

const env = { ...process.env, JS_COVERAGE: "1" };
const run = spawnSync("npx", ["playwright", "test", "--reporter=line"], { stdio: "inherit", shell: true, env, cwd: __dirname });
if (run.status !== 0) process.exit(run.status || 1);
const report = spawnSync(process.execPath, ["js-coverage-report.js", ...process.argv.slice(2)], { stdio: "inherit", cwd: __dirname });
process.exit(report.status || 0);
