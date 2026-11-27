"""docs_diff 명령줄, 콘솔 설정, 수집기의 네트워크 래퍼(_open/get/get_bytes)를 가짜 응답으로 확인한다. 네트워크 없음."""
import contextlib
import io
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

import _path  # noqa: F401
import docsnap.common as docs_common
import docsnap.history.diff as docs_diff
import docsnap.fetch as f
import fixtures as fx


class DiffCli(unittest.TestCase):
    def snapshots(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        old = fx.write_snapshot(os.path.join(d.name, "old.json"), [fx.page("a", "A", "# A\n\nold text"), fx.page("b", "B", "# B\n\nsame")])
        new = fx.write_snapshot(os.path.join(d.name, "new.json"), [fx.page("a", "A", "# A\n\nnew text"), fx.page("b", "B", "# B\n\nsame")])
        return d.name, old, new

    def run_main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = docs_diff.main(argv)
        return code, out.getvalue()

    def test_without_two_arguments_it_prints_usage_and_exits_2(self):
        code, text = self.run_main(["only-one"])
        self.assertEqual(code, 2)
        self.assertIn("docs_diff.py", text)

    def test_two_files_print_the_unified_diff_of_changed_pages_only(self):
        _, old, new = self.snapshots()
        code, text = self.run_main([old, new])
        self.assertEqual(code, 0)
        self.assertIn("-old text", text)
        self.assertIn("+new text", text)
        self.assertNotIn("same", text)  # 바뀌지 않은 페이지는 나오지 않는다

    def test_page_filter_limits_the_output(self):
        _, old, new = self.snapshots()
        self.assertIn("+new text", self.run_main([old, new, "en/a"])[1])
        self.assertIn("변경된 페이지가 없습니다.", self.run_main([old, new, "en/b"])[1])

    def test_identical_snapshots_say_so(self):
        _, old, _ = self.snapshots()
        self.assertEqual(self.run_main([old, old]), (0, "변경된 페이지가 없습니다.\n"))

    def test_a_date_resolves_to_the_kept_history_file_and_a_missing_one_fails_clearly(self):
        with tempfile.TemporaryDirectory() as d:
            path = fx.write_snapshot(os.path.join(d, "2026-11-20.json.gz"), [fx.page("a", "A", "x")])
            self.assertEqual(docs_diff.resolve("2026-11-20", d), path)
            self.assertEqual(docs_diff.resolve("some/file.json", d), "some/file.json")  # 날짜가 아니면 경로 그대로
            with self.assertRaises(SystemExit) as cm:
                docs_diff.resolve("2026-01-01", d)
            self.assertIn("보관된 이력이 없습니다", str(cm.exception))


class Stream:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def reconfigure(self, **kw):
        if self.error:
            raise self.error
        self.calls.append(kw)


class SetupConsole(unittest.TestCase):
    def run_setup(self, out, err, env):
        with mock.patch.object(docs_common.sys, "stdout", out), mock.patch.object(docs_common.sys, "stderr", err), \
                mock.patch.dict(os.environ, env):  # 끝나면 환경 변수는 원래대로 돌아온다
            if "PYTHONIOENCODING" not in env:
                os.environ.pop("PYTHONIOENCODING", None)
            docs_common.setup_console()

    def test_both_streams_become_utf8_and_line_buffered(self):
        out, err = Stream(), Stream()
        self.run_setup(out, err, {})
        for s in (out, err):
            self.assertEqual(s.calls, [{"errors": "replace", "line_buffering": True, "encoding": "utf-8"}])

    def test_an_explicit_PYTHONIOENCODING_is_respected(self):
        out, err = Stream(), Stream()
        self.run_setup(out, err, {"PYTHONIOENCODING": "cp949"})
        self.assertNotIn("encoding", out.calls[0])  # 인코딩은 사용자 지정을 존중하고 줄 단위 버퍼만 켠다
        self.assertTrue(out.calls[0]["line_buffering"])

    def test_streams_that_cannot_be_reconfigured_are_left_alone(self):
        self.run_setup(io.StringIO(), Stream(error=ValueError("detached")), {})  # 예외 없이 지나간다


class FakeResponse:
    def __init__(self, url, ctype, body):
        self.url, self.ctype, self.body = url, ctype, body
        self.headers = {"content-type": ctype}

    def geturl(self):
        return self.url

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Network(unittest.TestCase):
    def test_open_decodes_utf8_and_sends_the_client_name_and_timeout(self):
        seen = {}

        def fake_urlopen(req, timeout):
            seen["ua"], seen["timeout"] = req.headers.get("User-agent"), timeout
            return FakeResponse("https://x/final", "text/markdown", "한글 본문".encode("utf-8"))

        with mock.patch.object(f.urllib.request, "urlopen", fake_urlopen):
            self.assertEqual(f._open("https://x/start"), ("https://x/final", "text/markdown", "한글 본문"))
        self.assertEqual(seen, {"ua": "docs-snapshot/1.0", "timeout": 30})  # 일반 클라이언트 이름만 보낸다 (개인 정보 없음)

    def test_get_retries_with_growing_waits_then_succeeds(self):
        with mock.patch.object(f, "_open", side_effect=[OSError("a"), OSError("b"), ("u", "text/markdown", "ok")]), \
                mock.patch.object(f.time, "sleep") as sleep:
            self.assertEqual(f.get("https://x/p.md"), "ok")
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2])

    def test_get_gives_up_after_three_attempts_with_the_last_error(self):
        with mock.patch.object(f, "_open", side_effect=OSError("down")) as op, mock.patch.object(f.time, "sleep"):
            with self.assertRaises(OSError):
                f.get("https://x/p.md")
        self.assertEqual(op.call_count, 3)

    def test_a_404_is_not_retried_but_a_500_and_a_429_are(self):
        def http(code):
            return urllib.error.HTTPError("https://x/p.md", code, "e", {}, io.BytesIO())

        for code, calls in ((404, 1), (403, 1), (500, 3), (429, 3)):
            with mock.patch.object(f, "_open", side_effect=http(code)) as op, mock.patch.object(f.time, "sleep"):
                with self.assertRaises(urllib.error.HTTPError):
                    f.get("https://x/p.md")
            self.assertEqual(op.call_count, calls, code)
        with mock.patch.object(f.urllib.request, "urlopen", side_effect=http(404)) as op, mock.patch.object(f.time, "sleep"):
            with self.assertRaises(urllib.error.HTTPError):
                f.get_bytes("https://x/a.png")
        self.assertEqual(op.call_count, 1)

    def test_html_for_a_md_url_is_retried_once_at_the_final_address(self):
        calls = []

        def fake_open(url):
            calls.append(url)
            return ("https://x/moved", "text/html", "<html>") if len(calls) == 1 else ("https://x/moved.md", "text/markdown", "# real")

        with mock.patch.object(f, "_open", fake_open):
            self.assertEqual(f.get("https://x/old.md"), "# real")
        self.assertEqual(calls, ["https://x/old.md", "https://x/moved.md"])

    def test_html_instead_of_markdown_is_an_error_after_the_retries(self):
        with mock.patch.object(f, "_open", return_value=("https://x/moved", "text/html", "<html>")), mock.patch.object(f.time, "sleep"):
            with self.assertRaises(ValueError):
                f.get("https://x/old.md")

    def test_get_bytes_retries_and_returns_the_raw_bytes(self):
        responses = [urllib.error.URLError("flaky"), FakeResponse("u", "image/png", b"\x89PNG")]

        def fake_urlopen(req, timeout):
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        with mock.patch.object(f.urllib.request, "urlopen", fake_urlopen), mock.patch.object(f.time, "sleep") as sleep:
            self.assertEqual(f.get_bytes("https://x/a.png"), b"\x89PNG")
        self.assertEqual(sleep.call_count, 1)

    def test_get_bytes_raises_when_every_attempt_fails(self):
        with mock.patch.object(f.urllib.request, "urlopen", side_effect=urllib.error.URLError("down")), mock.patch.object(f.time, "sleep"):
            with self.assertRaises(urllib.error.URLError):
                f.get_bytes("https://x/a.png")


if __name__ == "__main__":
    unittest.main()
