# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview
A tool that builds an **offline snapshot** of the official Claude Code docs (https://code.claude.com/docs) in **English and Korean**: collect → JSON → static HTML site (official-site-like layout), plus a single entry point. **Never translate**: the Korean side is the official `/docs/ko/<slug>.md` text; pages without one fall back to the English text with a notice. UI strings (`UI_TEXT` in the converter) are the only text written here. Python 3.9+ standard library only (no packages; uses `str.removesuffix`). User-facing usage is in `README.md`; this file covers what you need to modify and verify the code.

`output/` and `logs/` are both git-ignored (logs stay local).

## Commands
- **Full build** (needs internet, ~10 s–2 min): `python build_docs_snapshot.py [out_dir] [log_dir]`. Defaults are `output/` and `logs/` next to the script, regardless of cwd.
- **Per stage** (use a scratch folder, not `output/`):
  ```
  python docs_fetch_json.py tmp/docs.json tmp/site/assets
  python docs_json_to_html.py tmp/docs.json tmp/site
  ```
  The fetcher's optional 2nd argument is the assets folder (the build passes `.building/site/assets` so assets are saved once, straight into the site). Without it assets go next to the JSON. `docs_fetch_json.py` with no argument writes `YYYY-MM-DD/docs.json` relative to the **cwd** (unlike the build script).
- **Tests** (stdlib `unittest`, no network): `python -m unittest discover tests`. Run after touching the converter, `anchor_key`/`anchorKey`, or the history/diff code in the build script.
- **Diff two kept days**: `python docs_diff.py 2026-11-20 2026-11-27 [en/page]` (dates resolve to `output/history/DATE.json.gz`; paths also work).
- **Offline verification** against real data: re-run only the converter on the kept history, writing to a scratch folder, not into `output/`: `python docs_json_to_html.py output/history/YYYY-MM-DD.json.gz <scratch>/site output/site/assets` (3rd arg = where to copy assets from; skipped if `<scratch>/site/assets` exists). Expect `없는 파일 0개` (0 missing files), `헤딩 220/220` and `아코디언 N/N` Korean id matches, and about 450 anchors per language that end up as `stale` (see Invariants).
- **Visual check**: serve the site with `python -m http.server` (browser tools block `file:` URLs; the site itself works over `file://`) and compare against the official site's look. Don't pipe it into `Select-Object -First N` and then trust the exit code; the closed pipe makes it nonzero.
- Don't use `python -I`: the scripts import each other from the same folder.

## Architecture
| File | Role |
|---|---|
| `build_docs_snapshot.py` | Entry point: connectivity check → fetch → convert → change summary → swap `site/` → save history + diff → log |
| `docs_fetch_json.py` | Reads the page list from `llms.txt`, downloads each English `.md`, its official Korean counterpart, and the images/videos, writes one JSON |
| `docs_json_to_html.py` | JSON (.json or .gz) → two-language static HTML site that opens via `file://`; contains its own Markdown→HTML converter, layout (`PAGE`/`CSS`/`JS`), search and highlighting |
| `docs_diff.py` | `open_json` (json or .gz), `diff_snapshots` (per-page unified diff, keys `en/slug` and `ko/slug`; Korean is compared only when both snapshots have it); CLI for any two kept days. Imported by the build script and the converter |
| `docs_common.py` | `norm` / `slug` / `ko_url`: the shared URL rules; `setup_console()`: UTF-8 + line-buffered stdout/stderr (called in each script's `__main__`, before the build's `Tee`) |
| `tests/` | `unittest` suite: markdown renderer + components, anchor-rule sync, fetcher (fake network), build/history/diff/`site` swap, two-language site output |
| `reference/` | Local-only docs-site screenshot (design reference); git-ignored because it reproduces Anthropic's page |

**`docs.json`**: top-level keys `source, fetched_at, page_count, languages, nav_names_ko, ko_errors, redirects, unresolved_links, non_page_links, assets_dir, asset_errors, pages[]`. Page keys: `category` (list `[tab, sidebar section, group, subgroup…]`; `_unlisted` for hidden pages), `title, url, description, content, nav_label, assets` ({remote URL: `assets/file`, shared by both languages}), `ko` (`{title, description, content, nav_label}` = official Korean page, or `null` when the official site has none) and `error` / `ko_error` on a failed fetch. `nav_names_ko` maps English tab/group/subgroup names to the Korean site's names (paired by position on each tab's first page, plus same-slug menu items); names identical in both languages are omitted.

**Fetch** also collects hidden pages (`_unlisted`), old-link aliases (`redirects`) and sidebar names (`nav_label`). The Korean page list is derived from the English `llms.txt` (`ko/llms.txt` does not exist): `/docs/en/` → `/docs/ko/`. A Korean URL that 404s, serves HTML, or redirects outside `/docs/ko/` (currently `changelog`, `claude-tag`) means “no Korean version” (`ko = null`, not an error); any other failure sets `ko_error` and fails the build. It deliberately skips `CHANGELOG.md`, `plugins/` and `examples/` of the GitHub repo `anthropics/claude-code` (too volatile / duplicates the docs).

**Convert** writes `<site>/en/...html` and `<site>/ko/...html` (original URL structure), `index.html` (redirect to the first English page), `nav-data-{en,ko}.js` (tab → group → page tree + `window.DOCS_UI` strings), `search-data-{en,ko}.js`, `style.css`, `nav.js`. Internal docs links (English or Korean URLs) become relative paths inside the page's own language; images/videos point to the shared `assets/`. Layout follows the official site: header (logo, language switch, search button `Ctrl K`), top tab bar (`category[0]`), sidebar of the active tab (`category[2:]`; top-level groups are headers, deeper groups collapsible), a right-hand “On this page” table of contents (`#toc`, built in the browser from the article's `h2`/`h3` ids with scroll tracking; hidden when under 2 headings or below 1240px wide), serif titles, a “Copy page” button (markdown embedded as JSON in `#md-src`), per-block copy buttons. Mintlify blocks in the markdown are rendered as components: `> [tab] name` runs → tab group, `> [accordion] title` → `<details>`, `> [card] [Title](url)` runs → card grid; a `>` description directly under the h1 renders as plain lead text. Search reads the current language's `search-data-*.js` (`window.DOCS_SEARCH`, ~10MB each, built from `plain_text`), lazy-loaded via a `<script>` tag on the first query so it works over `file://`. Code blocks get rule-based syntax highlighting in the browser (`pre[data-lang]` -> `tk-*` spans). Pages with no Korean version are rendered under `ko/` from the English text with a `.notice` banner. Also supports GitHub-style callouts (`> [!NOTE]`), tables, nested lists and code blocks.

**Heading ids**: official Korean pages keep the English anchors in their links (e.g. `#agents-md`), so the Korean `Renderer` is given `hint=` the English page's `(level, id)` list and reuses those ids in order; on a level mismatch it falls back to the normal slug rule for the rest. The converter prints how many Korean pages matched fully (expect all).

**Link classification** (`resolve_links` in the fetcher) for docs URLs that were linked but not collected: `redirects` (old URL alias), `_unlisted` (added as a hidden page), `non_page_links` (GET returns 405 or a non-docs response, e.g. MCP endpoints such as `/docs/mcp`), `unresolved_links` (any other failure, e.g. 404).

## Build behavior (`build_docs_snapshot.py`)
- Builds in `output/.building/` (`docs.json` + `site/`; the fetcher writes assets straight into `.building/site/assets`, so there is no second copy). Only if every page is fetched (English and Korean) and converted does `swap_site` replace `output/site/` (old one is parked as `site.old` and restored if the swap fails), then `save_history` runs, `.building` is deleted and `output/index.html` (redirect to `site/index.html`) is rewritten. On failure the existing site stays untouched. No zip is produced.
- Output layout: `output/{index.html, site/, history/}`. One site, one source of truth: `history/YYYY-MM-DD.json.gz` (the gzipped `docs.json`) and `history/YYYY-MM-DD.diff` (full per-page unified diff vs. the comparison target; omitted when nothing changed). `prune_history` keeps the newest `KEEP_HISTORY = 30` dates (counts dates, not calendar days). There is no per-date folder and no uncompressed `docs.json` outside `.building`.
- No internet → exit 1 without touching the site; only a log file is written.
- `docs_json_to_html.main()` returns the number of links pointing to missing files (both languages); non-zero fails the build.
- The change summary uses `find_previous` **before** pruning. Priority: latest history strictly older than today > latest non-today legacy folder `output/YYYY-MM-DD/docs.json` > today's legacy folder. Legacy folders (made by the previous layout) are deleted by `remove_legacy_dirs` after the first successful build. So a same-day re-run still compares against yesterday once history exists. The log's change summary is English-only (page URLs); Korean changes appear in the diff file as `ko/…`.

## Logs
- One file per run (success, failure or error): `logs/YYYY/YYYY-MM-DD_HHMMSS.log` (e.g. `logs/2026/2026-11-26_153729.log`); same-second collisions get `_2`. Logs are independent of `output/`, so pruning never deletes them.
- Contents: result, start/end/duration, collection summary (pages, Korean pages / missing Korean, assets, aliases, hidden pages, non-doc/unresolved links), change vs. previous history, pruned legacy folders and history, traceback on error, the `LOG_GUIDE` table, full console output. Log text is Korean.
- `LOG_GUIDE` (in `build_docs_snapshot.py`) is appended to every log and explains what each section signals (new feature, deprecation/move, behavior change). Keep it in sync if you add or rename log sections.
- The log's change summary points to the full diff file and reports counts of added/removed/changed pages and, per changed page, the character delta, new/removed/edited sections and up to 3 added/removed representative lines (140 chars). It is a rule-based section/line comparison, not a full diff or prose summary — treat it as clues, not conclusions.

## Invariants when editing
- `anchor_key` (Python) and `anchorKey` (inside the `JS` constant) must keep the same rule (URL-decode, lowercase, letters/digits only). `tests/test_anchor_sync.py` guards this. The site's heading-id rules differ (`.`, `/`, `’`), so `nav.js` falls back to this punctuation-insensitive match.
- **Anchors are settled at build time** (`resolve_anchors` / `resolve_anchor`), after every page's ids are known. Docs links with a `#frag` (and same-page `#frag` links) are rewritten to a real id: `exact` → `key` (case/punctuation only) → `strict` (every word of the frag is in exactly one id, so a heading lengthened upstream is followed; ambiguity is never guessed) → `stale`. A `stale` link drops its anchor, opens the page top and gets `class="stale-anchor"` + a `title` (`UI_TEXT["stale"]`). `Renderer(defer_anchors=True)` leaves `href="\x01N\x01"` markers for this; the default (used by tests) writes `rel#frag` directly. The totals and the lists go to `docs_json_to_html.REPORT`, which the build copies into the log's `링크 검증` section. About 450 stale links per language (892 unique at last run) are expected: the target section no longer exists upstream. A jump in that number means upstream restructured.
- Accordions (`> [accordion] Title`) get an `id` from the same slug rule as headings (shared dedupe counter); Korean accordions borrow the English page's accordion ids in order (`acc_hint`), counted separately from headings. `reveal()` in `nav.js` opens the `<details>` on navigation.
- Site HTML/CSS/JS live as the `PAGE`, `CSS` and `JS` string constants in `docs_json_to_html.py`. `JS` is a raw string (write JS backslashes as-is; avoid `"""` and `'''` inside — build such strings in JS code instead); `CSS`/`PAGE` are normal strings (`PAGE` goes through `str.format`, so literal braces must be doubled). Edit those, never the generated files under `output/`.
- Official Korean text is never translated or edited. UI wording in `UI_TEXT` is the only hand-written Korean; do not add translated doc content.
- URL comparison rules belong only in `docs_common.norm` / `slug`; both the fetcher and the converter import them.
- Assets are stored once. The converter copies assets only when `<out>/assets` does not exist yet (standalone runs); otherwise it assumes the fetcher already saved them there. Page `assets` values are site-root-relative (`assets/file`).

## Environment notes
- Sources and logs are UTF-8 with Korean text. PowerShell `Get-Content` shows them garbled; use the Read tool or `-Encoding utf8`.
- `.mcp.json` points at a local IntelliJ (`idea`) MCP server; it is mostly irrelevant for this Python project. `.idea/`, `__pycache__/` and `.claude/settings.local.json` are git-ignored.
 