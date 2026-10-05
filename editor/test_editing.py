import base64
import hashlib
import tempfile
import unittest
from pathlib import Path

from server import ConflictError, read_article, save_article, upload_image


class EditingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "content"
        self.path = self.root / "diary" / "index.md"
        self.path.parent.mkdir(parents=True)
        self.original = b'---\r\ntitle: "Old"\r\nslug: "original"\r\ntags: ["keep"]\r\n---\r\n\r\nOld body\r\n'
        self.path.write_bytes(self.original)
        self.backups = Path(self.temp.name) / "backups"

    def tearDown(self):
        self.temp.cleanup()

    def test_saves_markdown_and_preserves_other_metadata_and_backup(self):
        old = read_article(self.root, "diary/index.md")
        result = save_article(self.root, "diary/index.md", "新标题", "## 新段落\n\n**文字**", old["revision"], self.backups)
        current = self.path.read_bytes()
        self.assertIn(b'slug: "original"\r\ntags: ["keep"]\r\n', current)
        self.assertIn("## 新段落".encode(), current)
        self.assertEqual(result["title"], "新标题")
        self.assertNotEqual(result["revision"], old["revision"])
        self.assertEqual(next(self.backups.glob("*.md")).read_bytes(), self.original)

    def test_conflict_does_not_overwrite_external_edit(self):
        revision = hashlib.sha256(self.original).hexdigest()
        external = self.original + b"external edit\r\n"
        self.path.write_bytes(external)
        with self.assertRaises(ConflictError):
            save_article(self.root, "diary/index.md", "Title", "changed", revision, self.backups)
        self.assertEqual(self.path.read_bytes(), external)

    def test_shortcode_page_cannot_be_rewritten(self):
        self.path.write_bytes(self.original + b'{{< typing-chart >}}\r\n')
        old = read_article(self.root, "diary/index.md")
        self.assertFalse(old["editable"])
        with self.assertRaises(ValueError):
            save_article(self.root, "diary/index.md", "Title", "changed", old["revision"], self.backups)

    def test_upload_retains_image_bytes_and_uses_hugo_paths(self):
        data = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jEyoAAAAASUVORK5CYII=')
        url = upload_image(self.root, "diary/index.md", base64.b64encode(data).decode())
        self.assertTrue(url.startswith("editor-images/"))
        self.assertEqual((self.path.parent / url).read_bytes(), data)
        flat = self.root / "diary" / "note.md"
        flat.write_bytes(self.original)
        url = upload_image(self.root, "diary/note.md", base64.b64encode(data).decode())
        self.assertTrue(url.startswith("/images/editor/"))
        self.assertEqual((self.root.parent / "static" / url.lstrip("/")).read_bytes(), data)

    def test_non_image_and_traversal_are_rejected(self):
        with self.assertRaises(ValueError):
            upload_image(self.root, "diary/index.md", base64.b64encode(b'<svg onload="evil()"></svg>').decode())
        with self.assertRaises(ValueError):
            save_article(self.root, "../outside.md", "Title", "Body", "", self.backups)


if __name__ == "__main__":
    unittest.main()
