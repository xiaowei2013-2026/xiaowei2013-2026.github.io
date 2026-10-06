import tempfile
import hashlib
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from server import ConflictError, create_category, create_article, delete_category


class CategoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'content'
        self.parent = self.root / 'other'
        self.parent.mkdir(parents=True)
        self.index = self.parent / '_index.md'
        self.original = b'\xef\xbb\xbf---\r\ntitle: Other\r\n---\r\n\r\n- [Typing](typing/)\r\n'
        self.index.write_bytes(self.original)
        self.backups = self.root.parent / '.tools' / 'backups'

    def tearDown(self):
        self.temp.cleanup()

    def create(self, directory='other', title='工具', slug='tools', identifier='a' * 32):
        return create_category(self.root, directory, title, slug, '分类说明', identifier, self.backups)

    def test_creates_local_category_and_preserves_parent_navigation_and_encoding(self):
        category = self.create()
        self.assertEqual(category['directory'], 'other/tools')
        self.assertEqual(category['url'], '/other/tools/')
        child = self.parent / 'tools' / '_index.md'
        self.assertIn('title: "工具"', child.read_text(encoding='utf-8'))
        current = self.index.read_bytes()
        self.assertTrue(current.startswith(self.original))
        self.assertIn('- [工具](tools/)'.encode(), current)
        self.assertEqual(next(self.backups.glob('*.md')).read_bytes(), self.original)
        article, _ = create_article(self.root, category['directory'], 'Note', '2000-01-01', 'Body', 'b' * 32)
        self.assertTrue(article['path'].startswith('other/tools/'))

    def test_retries_and_concurrent_requests_do_not_duplicate_navigation(self):
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda _: self.create(), range(3)))
        self.assertEqual(len({item['url'] for item in results}), 1)
        self.assertEqual(self.index.read_text(encoding='utf-8-sig').count('[工具](tools/)'), 1)
        with self.assertRaises(ConflictError):
            self.create(title='Changed title')
        with self.assertRaises(ConflictError):
            self.create(identifier='b' * 32)

    def test_nested_and_automatic_directories(self):
        first = self.create(slug='')
        self.assertEqual(first['directory'], 'other/category-' + 'a' * 12)
        child = self.create(directory=first['directory'], slug='nested', identifier='b' * 32)
        self.assertEqual(child['directory'], first['directory'] + '/nested')

    def test_invalid_names_paths_and_existing_directories_never_overwrite(self):
        for data in [{'title': ''}, {'title': 'bad\nname'}, {'directory': '../outside'}, {'slug': '../outside'},
                     {'slug': 'CON'}, {'slug': 'a/b'}, {'slug': '中文'}, {'slug': 'Tools'}]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.create(**data)
        self.assertEqual(self.index.read_bytes(), self.original)
        existing = self.parent / 'tools'
        existing.mkdir()
        with self.assertRaises(ConflictError):
            self.create()
        self.assertFalse((existing / '_index.md').exists())

    def test_root_creation_does_not_replace_homepage(self):
        item = self.create(directory='', slug='learning')
        self.assertEqual(item['url'], '/learning/')
        self.assertFalse((self.root / '_index.md').exists())

    def delete(self, item):
        index = self.root / item['directory'] / '_index.md'
        return delete_category(self.root, item['directory'], hashlib.sha256(index.read_bytes()).hexdigest(), self.backups)

    def test_deletes_empty_category_and_only_its_parent_link(self):
        item = self.create()
        self.delete(item)
        self.assertFalse((self.root / item['directory']).exists())
        self.assertEqual(self.index.read_bytes(), self.original)
        self.assertIn(self.original, [path.read_bytes() for path in self.backups.glob('*.md')])

    def test_deletes_root_category_and_empty_resource_directories(self):
        item = self.create(directory='', slug='temporary')
        (self.root / item['directory'] / 'empty' / 'nested').mkdir(parents=True)
        self.delete(item)
        self.assertFalse((self.root / item['directory']).exists())

    def test_nonempty_category_keeps_articles_subcategories_and_images(self):
        item = self.create()
        parent_before = self.index.read_bytes()
        for name in ['article.md', 'photo.png', 'nested/_index.md']:
            file = self.root / item['directory'] / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b'Keep this content')
            with self.subTest(name=name), self.assertRaises(ConflictError):
                self.delete(item)
            self.assertEqual(file.read_bytes(), b'Keep this content')
            file.unlink()
        self.assertEqual(self.index.read_bytes(), parent_before)

    def test_modified_category_original_sections_and_home_are_protected(self):
        item = self.create()
        index = self.root / item['directory'] / '_index.md'
        revision = hashlib.sha256(index.read_bytes()).hexdigest()
        index.write_bytes(index.read_bytes() + b'Changed outside editor')
        with self.assertRaises(ConflictError):
            delete_category(self.root, item['directory'], revision, self.backups)
        with self.assertRaises(ValueError):
            delete_category(self.root, 'other', hashlib.sha256(self.index.read_bytes()).hexdigest(), self.backups)
        with self.assertRaises(ValueError):
            delete_category(self.root, '', '', self.backups)
        with self.assertRaises(ValueError):
            delete_category(self.root, '../outside', '', self.backups)
