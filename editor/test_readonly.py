import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from server import article_path, list_articles, make_handler, read_article


class ReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "content"
        self.root.mkdir()
        (self.root / "diary").mkdir()
        self.file = self.root / "diary" / "一天.md"
        self.original = ('---\r\ntitle: "一天的记录"\r\ndate: 2026-10-05\r\n'
                         'tags: ["时间"]\r\n---\r\n\r\n# 今天\r\n'
                         '![图片](图片和附件/example.jpg)\r\n').encode("utf-8")
        self.file.write_bytes(self.original)
        (self.root / "diary" / "_index.md").write_text('---\ntitle: "日记"\n---\n', encoding="utf-8")
        self.outside = Path(self.temp.name) / "secret.md"
        self.outside.write_text("outside", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_preserves_original_markdown_and_line_endings(self):
        article = read_article(self.root, "diary/一天.md")
        self.assertEqual(article["content"].encode("utf-8"), self.original)
        self.assertEqual(article["title"], "一天的记录")
        self.assertEqual(article["module"], "日记")
        self.assertEqual(self.file.read_bytes(), self.original)

    def test_lists_articles_and_section_pages(self):
        items = list_articles(self.root)
        self.assertEqual(len(items), 2)
        self.assertEqual({item["kind"] for item in items}, {"文章", "目录页"})
        self.assertTrue(all("content" not in item for item in items))

    def test_blocks_traversal_and_non_markdown(self):
        for relative in ["../secret.md", str(self.outside), "diary/../../secret.md", "diary\\一天.md", "diary/image.jpg"]:
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                article_path(self.root, relative)

    def test_rejects_external_symlink(self):
        link = self.root / "linked.md"
        try:
            link.symlink_to(self.outside)
        except (OSError, NotImplementedError):
            self.skipTest("System does not permit creating symlinks")
        with self.assertRaises(ValueError):
            read_article(self.root, "linked.md")

    def test_http_reads_and_rejects_writes_without_file_changes(self):
        handler = make_handler(self.root)
        handler.log_message = lambda *args: None
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            connection.request("GET", "/api/article?path=" + quote("diary/一天.md"))
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["article"]["content"].encode("utf-8"), self.original)
            for method in ["POST", "PUT", "PATCH", "DELETE"]:
                connection.request(method, "/api/article", body=b'{"content":"overwrite"}')
                response = connection.getresponse()
                self.assertEqual(response.status, 403 if method == "POST" else 405)
                response.read()
            connection.request("GET", "/api/article?path=../secret.md")
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            connection.request("GET", "/api/articles", headers={"Host": "external.example"})
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            for endpoint in ["/", "/app.js", "/styles.css"]:
                connection.request("GET", endpoint)
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertGreater(len(response.read()), 0)
            self.assertEqual(self.file.read_bytes(), self.original)
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
