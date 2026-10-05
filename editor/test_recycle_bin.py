import hashlib
import tempfile
import unittest
from pathlib import Path

from recycle_bin import RecycleBin, TrashConflict


class RecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.content = Path(self.temp.name) / 'content'
        self.article = self.content / 'diary' / 'entry' / 'index.md'
        self.article.parent.mkdir(parents=True)
        self.raw = b'---\r\ntitle: Note\r\n---\r\nBody\r\n'
        self.article.write_bytes(self.raw)
        self.revision = hashlib.sha256(self.raw).hexdigest()
        self.trash = RecycleBin(self.content)

    def tearDown(self):
        self.temp.cleanup()

    def test_delete_restore_preserves_exact_bytes_and_images(self):
        image = self.article.parent / 'photo.png'
        image.write_bytes(b'original image')
        item = self.trash.delete('diary/entry/index.md', self.revision, 'Note', '/diary/entry/')
        self.assertFalse(self.article.exists())
        self.assertEqual(image.read_bytes(), b'original image')
        self.assertEqual(self.trash.items()[0]['id'], item['id'])
        self.assertFalse(item['github_deleted'])
        restored = self.trash.restore(item['id'])
        self.assertEqual(restored['url'], '/diary/entry/')
        self.assertEqual(self.article.read_bytes(), self.raw)
        self.assertEqual(self.trash.items(), [])

    def test_external_edit_blocks_deletion(self):
        self.article.write_bytes(self.raw + b'external')
        with self.assertRaises(TrashConflict):
            self.trash.delete('diary/entry/index.md', self.revision, 'Note')
        self.assertTrue(self.article.exists())
        self.assertEqual(self.trash.items(), [])

    def test_restore_never_overwrites_existing_file(self):
        item = self.trash.delete('diary/entry/index.md', self.revision, 'Note')
        self.article.write_bytes(b'new same-name file')
        with self.assertRaises(TrashConflict):
            self.trash.restore(item['id'])
        self.assertEqual(self.article.read_bytes(), b'new same-name file')
        self.assertEqual(len(self.trash.items()), 1)

    def test_directory_traversal_and_index_pages_are_protected(self):
        for path in ['../secret.md', '/outside.md', 'diary/_index.md', 'diary\\entry\\index.md']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.trash.delete(path, self.revision, 'Note')
        with self.assertRaises(ValueError):
            self.trash.restore('../outside')
        self.assertTrue(self.article.exists())
