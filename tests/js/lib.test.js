// site_src/lib.js 의 순수 함수 테스트. 실행: node --test tests/js   (Node 18+, 설치할 것 없음)
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const L = require(path.join(__dirname, "..", "..", "site_src", "lib.js"));

const text = (tokens) => tokens.map((t) => t[1]).join("");
const kinds = (tokens) => tokens.filter((t) => t[0]).map((t) => t[0] + ":" + t[1]);
const json = L.langConfig("json");

test("anchorKey: URL 디코딩, 소문자, 글자·숫자만", () => {
  assert.equal(L.anchorKey("A%20b-C_d.é"), "abcdé");
  assert.equal(L.anchorKey("What%27s-New.v2"), "whatsnewv2");
  assert.equal(L.anchorKey("%E0%A4%A"), "e0a4a"); // 깨진 % 는 디코딩 없이 그대로 처리 (예외를 던지지 않는다)
  assert.equal(L.anchorKey("%ff"), "ff");
  assert.equal(L.anchorKey("설정-값"), "설정값");
});

test("사이드바 트리: 첫 페이지와 포함 여부", () => {
  const tree = { g: "G", c: [{ g: "sub", c: [] }, { g: "s2", c: [{ p: "en/a.html" }, { p: "en/b.html" }] }] };
  assert.equal(L.navFirst(tree), "en/a.html");
  assert.equal(L.navFirst({ g: "빈", c: [] }), "");
  assert.ok(L.navHas(tree, "en/b.html"));
  assert.ok(!L.navHas(tree, "en/zzz.html"));
});

test("사이드바 필터는 비어 있으면 모두 보이고, 대소문자를 가리지 않는다", () => {
  assert.ok(L.labelMatches("Hooks reference", ""));
  assert.ok(L.labelMatches("Hooks reference", "hook"));
  assert.ok(!L.labelMatches("Hooks reference", "mcp"));
});

test("목차: 현재 제목 순번과 맨 아래 처리", () => {
  assert.equal(L.currentIndex([-200, -50, 100, 400], 150, false), 2);
  assert.equal(L.currentIndex([300, 500], 150, false), 0); // 아직 아무것도 지나지 않았으면 첫 항목
  assert.equal(L.currentIndex([-200, -50, 100, 400], 150, true), 3); // 끝까지 내리면 마지막
  assert.equal(L.tocClass("H3"), "l3");
  assert.equal(L.tocClass("H2"), "l2");
});

const docs = () =>
  L.prepare([
    { t: "Hooks reference", p: "en/hooks.html", x: "Hooks run shell commands. A hook runs on events.", h: [["Hook events", "hook-events"]] },
    { t: "Quickstart", p: "en/quickstart.html", x: "Install it, then add a hook once.", h: [["Install", "install"]] },
    { t: "Other", p: "en/other.html", x: "nothing relevant", h: [] },
  ]);

test("검색어: 2글자 미만은 무시, 공백으로 나누고 소문자", () => {
  assert.deepEqual(L.searchTerms(""), []);
  assert.deepEqual(L.searchTerms(" a "), []);
  assert.deepEqual(L.searchTerms("Hook  Setup"), ["hook", "setup"]);
  assert.deepEqual(L.searchTerms("훅"), ["훅"]); // 한국어는 한 글자도 단어다
  assert.deepEqual(L.searchTerms(" 툴 "), ["툴"]);
  assert.deepEqual(L.searchTerms("鍵"), ["鍵"]);
  assert.deepEqual(L.searchTerms("x"), []); // 영문 한 글자는 여전히 무시
});

test("검색 점수: 모든 검색어가 있어야 하고, 제목 > 헤딩 > 본문 순으로 가중", () => {
  const [hooks, quick, other] = docs();
  assert.equal(L.scoreDoc(other, ["hook"]), -1);
  assert.equal(L.scoreDoc(hooks, ["hook", "zzz"]), -1); // 한 단어라도 없으면 제외
  assert.ok(L.scoreDoc(hooks, ["hook"]) > L.scoreDoc(quick, ["hook"])); // 제목+헤딩+여러 번 등장
  assert.equal(L.scoreDoc(quick, ["hook"]), 1); // 본문에만 한 번
  assert.equal(L.scoreDoc(quick, ["install"]), 20 + 1); // 헤딩 20 + 본문 1
});

test("검색 결과 정렬과 한도", () => {
  const hits = L.rankDocs(docs(), ["hook"]);
  assert.deepEqual(hits.map((h) => h.d.p), ["en/hooks.html", "en/quickstart.html"]);
  assert.equal(L.countOccurrences("aaaaa", "a"), 5);
  assert.equal(L.countOccurrences("a".repeat(100), "a"), 20); // 한 문서가 점수를 독점하지 못하게 20회까지만
});

test("검색 결과의 헤딩 이동 위치와 미리보기 시작 위치", () => {
  const [hooks, quick] = docs();
  assert.deepEqual(L.pickHeading(hooks, ["events"]), ["Hook events", "hook-events"]);
  assert.equal(L.pickHeading(quick, ["events"]), undefined);
  assert.equal(L.firstMatchIndex(quick, ["add", "install"]), quick.lx.indexOf("install"));
  assert.equal(L.firstMatchIndex(quick, ["zzz"]), -1);
});

test("강조 조각: 검색어 앞뒤 글자를 보존하고 겹침 없이 나눈다", () => {
  const segs = L.markSegments("Run the Hook now, hook!", ["hook"]);
  assert.deepEqual(segs, [[0, "Run the "], [1, "Hook"], [0, " now, "], [1, "hook"], [0, "!"]]);
  assert.equal(segs.map((s) => s[1]).join(""), "Run the Hook now, hook!");
  assert.deepEqual(L.markSegments("nothing", ["zz"]), [[0, "nothing"]]);
  assert.deepEqual(L.markSegments("", ["zz"]), []);
});

test("구문 강조(회귀): JSON 키는 문자열과 다른 tk-key 로 칠한다", () => {
  const src = '{ "name": "x", "n": 12, "ok": true, "none": null }';
  const tk = L.tokenize(src, json);
  assert.deepEqual(kinds(tk), [
    'tk-key:"name"', 'tk-s:"x"', 'tk-key:"n"', "tk-n:12", 'tk-key:"ok"', "tk-k:true", 'tk-key:"none"', "tk-k:null",
  ]);
  assert.equal(text(tk), src);
});

test("구문 강조: 언어별 주석·문자열·키워드, 별칭과 모르는 언어", () => {
  assert.deepEqual(kinds(L.tokenize("# note\necho hi", L.langConfig("bash"))), ["tk-c:# note", "tk-k:echo"]);
  assert.deepEqual(kinds(L.tokenize("a=1 # tail", L.langConfig("sh"))), ["tk-n:1", "tk-c:# tail"]);
  assert.deepEqual(kinds(L.tokenize('x = """a\nb"""', L.langConfig("py"))), ['tk-s:"""a\nb"""']);
  assert.deepEqual(kinds(L.tokenize("const s = `t${1}`; // c", L.langConfig("ts"))), ["tk-k:const", "tk-s:`t${1}`", "tk-c:// c"]);
  assert.strictEqual(L.langConfig("ps1"), L.langConfig("powershell"));
  assert.strictEqual(L.langConfig("PY"), L.langConfig("python"));
  assert.equal(L.langConfig("cobol"), undefined);
  assert.equal(L.langConfig(undefined), undefined);
});

test("구문 강조: 어떤 입력이든 조각을 이어 붙이면 원문과 같다 (글자 손실 없음)", () => {
  const samples = {
    bash: "if [ -f a ]; then\n  echo \"$HOME\" # c\nfi\n",
    json: '{\n  "a": [1, 2.5, {"b": "c\\"d"}],\n  "e": false\n}\n',
    python: "def f(x):\n    '''doc'''\n    return x  # c\n",
    yaml: "a: 1\nb: [x, y]  # c\n",
    powershell: "$x = 1 # c\nif ($x) { Write-Host 'hi' }\n",
    js: "// c\nfunction f(a){ return `a${a}` + 'b' }\n",
    toml: "[a]\nk = \"v\"\nn = 1\n",
  };
  for (const [lang, src] of Object.entries(samples)) {
    assert.equal(text(L.tokenize(src, L.langConfig(lang))), src, lang);
  }
  assert.equal(text(L.tokenize("", json)), "");
});

test("키보드: 탭 목록은 좌우 화살표로 돌고 Home/End 로 처음·끝", () => {
  assert.equal(L.tabIndex("ArrowRight", 0, 3), 1);
  assert.equal(L.tabIndex("ArrowRight", 2, 3), 0); // 끝에서 처음으로
  assert.equal(L.tabIndex("ArrowLeft", 0, 3), 2); // 처음에서 끝으로
  assert.equal(L.tabIndex("Home", 2, 3), 0);
  assert.equal(L.tabIndex("End", 0, 3), 2);
  assert.equal(L.tabIndex("ArrowDown", 0, 3), null); // 관련 없는 키는 건드리지 않는다
  assert.equal(L.tabIndex("ArrowRight", 0, 0), null); // 탭이 없으면 할 일 없음
});

test("키보드: 검색 결과 목록(-1 은 입력창)", () => {
  assert.equal(L.listIndex("ArrowDown", -1, 3), 0); // 입력창에서 첫 결과로
  assert.equal(L.listIndex("ArrowDown", 1, 3), 2);
  assert.equal(L.listIndex("ArrowDown", 2, 3), 2); // 끝에서 멈춤
  assert.equal(L.listIndex("ArrowUp", 0, 3), -1); // 첫 결과에서 위로 가면 입력창
  assert.equal(L.listIndex("ArrowUp", -1, 3), null); // 입력창에서 위로는 갈 곳 없음
  assert.equal(L.listIndex("ArrowDown", -1, 0), null); // 결과가 없으면 이동 없음
  assert.equal(L.listIndex("Enter", 0, 3), null);
});

test("키보드: 포커스 가두기는 끝에서 반대편으로 돈다", () => {
  assert.equal(L.cycle(0, 3, 1), 1);
  assert.equal(L.cycle(2, 3, 1), 0);
  assert.equal(L.cycle(0, 3, -1), 2);
  assert.equal(L.cycle(-1, 3, 1), 0); // 목록 밖에서 시작하면 처음/끝
  assert.equal(L.cycle(-1, 3, -1), 2);
  assert.equal(L.cycle(0, 0, 1), -1);
});
