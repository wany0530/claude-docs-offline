# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview
A tool that builds an **offline snapshot** of the official Claude Code docs (https://code.claude.com/docs): collect → JSON → static HTML site, plus a single entry point. Python 3.9+ standard library only (no packages; uses `str.removesuffix`). User-facing usage is in `README.md`; this file covers what you need to modify and verify the code.

`output/` and `logs/` are both git-ignored (logs stay local).

## Commands
- **Full build** (needs internet, ~10 s–2 min): `python build_docs_snapshot.py [out_dir] [log_dir]`. Defaults are `output/` and `logs/` next to the script, regardless of cwd.
- **Per stage**:
  ```
  python docs_fetch_json.py output/YYYY-MM-DD/docs.json
  python docs_json_to_html.py output/YYYY-MM-DD/docs.json output/YYYY-MM-DD/html
  ```
  `docs_fetch_json.py` with no argument writes `YYYY-MM-DD/docs.json` relative to the **cwd** (unlike the build script).
- **Tests** (stdlib `unittest`, no network): `python -m unittest discover tests`. Run after touching the converter, `anchor_key`/`anchorKey`, or the history/diff code in the build script.
- **Diff two kept days**: `python docs_diff.py 2026-11-20 2026-11-27 [en/page]` (dates resolve to `output/history/DATE.json.gz`; paths also work).
- **Offline verification** against real data: re-run only the converter on the existing `output/YYYY-MM-DD/docs.json`, writing to a scratch folder, not into `output/`. Expect `없는 파일 0개` (0 missing files) and roughly 470 unresolved anchors (see Invariants). Don't pipe it into `Select-Object -First N` and then trust the exit code; the closed pipe makes it nonzero.
- Don't use `python -I`: the scripts import each other from the same folder.

## Architecture
| File | Role |
|---|---|
| `build_docs_snapshot.py` | Entry point: connectivity check → fetch → convert → change summary → prune old snapshots → log |
| `docs_fetch_json.py` | Reads the page list from `llms.txt`, downloads each `.md` and the images/videos, writes one JSON |
| `docs_json_to_html.py` | JSON → static HTML site that opens via `file://`; contains its own Markdown→HTML converter |
| `docs_diff.py` | `open_json` (json or .gz), `diff_snapshots` (per-page unified diff); CLI for any two kept days. Imported by the build script |
| `docs_common.py` | `norm` / `slug`: the shared URL rules; `setup_console()`: UTF-8 + line-buffered stdout/stderr (called in each script's `__main__`, before the build's `Tee`) |
| `tests/` | `unittest` suite: markdown renderer, anchor-rule sync, build/history/diff, site output |
| `reference/` | Local-only docs-site screenshot (design reference); git-ignored because it reproduces Anthropic's page |

**`docs.json`**: top-level keys `source, fetched_at, page_count, redirects, unresolved_links, non_page_links, assets_dir, asset_errors, pages[]`. Page keys: `category` (list; `_unlisted` for hidden pages), `title, url, description, content, nav_label, assets` ({remote URL: `assets/file`}), and `error` on a failed fetch.

**Fetch** also collects hidden pages (`_unlisted`), old-link aliases (`redirects`) and sidebar names (`nav_label`). It deliberately skips `CHANGELOG.md`, `plugins/` and `examples/` of the GitHub repo `anthropics/claude-code` (too volatile / duplicates the docs).

**Convert** writes `<html>/index.html` (full TOC) and pages at the original URL structure (`en/...html`). Internal docs links become relative paths; images/videos point to `assets/`. The sidebar (`nav-data.js` + `nav.js`) has a title filter, full-text search and code-copy buttons. Search reads `search-data.js` (`window.DOCS_SEARCH`, ~10MB, built from `plain_text`), lazy-loaded via a `<script>` tag on the first query so it works over `file://`. Code blocks get rule-based syntax highlighting in the browser (`pre[data-lang]` -> `tk-*` spans). Both live in `JS +=` blocks (raw strings) after the main `JS` constant. Supports GitHub-style callouts (`> [!NOTE]`), tables, nested lists and code blocks.

**Link classification** (`resolve_links` in the fetcher) for docs URLs that were linked but not collected: `redirects` (old URL alias), `_unlisted` (added as a hidden page), `non_page_links` (GET returns 405 or a non-docs response, e.g. MCP endpoints such as `/docs/mcp`), `unresolved_links` (any other failure, e.g. 404).

## Build behavior (`build_docs_snapshot.py`)
- Builds in `output/.building/`. Only if every page is fetched and converted does it move the result to `output/YYYY-MM-DD/{docs.json, assets/, html/}`, then run `prune` (`KEEP_SNAPSHOTS = 1`, at the top of the file) and rewrite `output/index.html` (a redirect to the latest `html/index.html`). On failure the existing snapshot stays untouched and `.building` is deleted. No zip is produced.
- No internet → exit 1 without touching snapshots; only a log file is written.
- `docs_json_to_html.main()` returns the number of links pointing to missing files; non-zero fails the build.
- Old snapshot folders are deleted (`KEEP_SNAPSHOTS = 1`), but each successful build gzips `docs.json` to `output/history/YYYY-MM-DD.json.gz` and writes `YYYY-MM-DD.diff` (full per-page unified diff vs. the comparison target; omitted when nothing changed). `prune_history` keeps the newest `KEEP_HISTORY = 30` dates (counts dates, not calendar days).
- The change summary uses `find_previous` **before** pruning. Priority: latest history strictly older than today > latest non-today snapshot folder > today's snapshot folder. So a same-day re-run still compares against yesterday once history exists; only the first run after history was introduced falls back to the snapshot folder.

## Logs
- One file per run (success, failure or error): `logs/YYYY/YYYY-MM-DD_HHMMSS.log` (e.g. `logs/2026/2026-11-26_153729.log`); same-second collisions get `_2`. Logs are independent of `output/`, so pruning never deletes them.
- Contents: result, start/end/duration, collection summary (pages, assets, aliases, hidden pages, non-doc/unresolved links), change vs. previous snapshot, pruned snapshots, traceback on error, the `LOG_GUIDE` table, full console output. Log text is Korean.
- `LOG_GUIDE` (in `build_docs_snapshot.py`) is appended to every log and explains what each section signals (new feature, deprecation/move, behavior change). Keep it in sync if you add or rename log sections.
- The log's change summary points to the full diff file and reports counts of added/removed/changed pages and, per changed page, the character delta, new/removed/edited sections and up to 3 added/removed representative lines (140 chars). It is a rule-based section/line comparison, not a full diff or prose summary — treat it as clues, not conclusions.

## Invariants when editing
- `anchor_key` (Python) and `anchorKey` (inside the `JS` constant) must keep the same rule (URL-decode, lowercase, letters/digits only). `tests/test_anchor_sync.py` guards this. The site's heading-id rules differ (`.`, `/`, `’`), so `nav.js` falls back to this punctuation-insensitive match.
- The ~470 anchors that remain unresolved (reported at the end of the convert step; 476 at last run) come from headings renamed upstream or accordion titles; they cannot be restored and are expected.
- Site HTML/CSS/JS live as the `PAGE`, `CSS` and `JS` string constants in `docs_json_to_html.py` (`JS` is extended by `JS += r"""..."""` blocks for search and highlighting; those are raw strings, so write JS backslashes as-is and avoid `"""` or `'''` inside). Edit those, never the generated files under `output/`.
- URL comparison rules belong only in `docs_common.norm` / `slug`; both the fetcher and the converter import them.
- `docs.json` and `assets/` must be in the same folder (the converter looks for assets next to the JSON).

## Environment notes
- Sources and logs are UTF-8 with Korean text. PowerShell `Get-Content` shows them garbled; use the Read tool or `-Encoding utf8`.
- `.mcp.json` points at a local IntelliJ (`idea`) MCP server; it is mostly irrelevant for this Python project. `.idea/`, `__pycache__/` and `.claude/settings.local.json` are git-ignored.
 