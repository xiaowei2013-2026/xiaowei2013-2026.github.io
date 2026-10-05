import hashlib
import tempfile
import unittest
from pathlib import Path

from server import ConflictError, content_directory, delete_article


class DeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'content'
        self.bundle = self.root / 'reading' / 'books' / 'technology' / 'book'
        self.bundle.mkdir(parents=True)
        self.article = self.bundle / 'index.md'
        self.article.write_bytes(b'---\ntitle: Book\n---\nBody\n')
        self.relative = self.article.relative_to(self.root).as_posix()
        self.revision = hashlib.sha256(self.article.read_bytes()).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def test_delete_only_removes_markdown_and_creates_no_trash(self):
        image = self.bundle / 'image.png'
        image.write_bytes(b'original image')
        delete_article(self.root, self.relative, self.revision)
        self.assertFalse(self.article.exists())
        self.assertEqual(image.read_bytes(), b'original image')
        self.assertFalse((self.root.parent / '.tools' / 'editor-trash').exists())

    def test_external_changes_and_section_index_are_protected(self):
        self.article.write_bytes(b'Changed outside editor')
        with self.assertRaises(ConflictError):
            delete_article(self.root, self.relative, self.revision)
        index = self.bundle.parent / '_index.md'
        index.write_bytes(b'Category')
        with self.assertRaises(ValueError):
            delete_article(self.root, index.relative_to(self.root).as_posix(), hashlib.sha256(index.read_bytes()).hexdigest())
        self.assertTrue(index.exists())

    def test_leaf_bundle_is_not_a_new_article_directory(self):
        with self.assertRaises(ValueError):
            content_directory(self.root, self.bundle.relative_to(self.root).as_posix())
