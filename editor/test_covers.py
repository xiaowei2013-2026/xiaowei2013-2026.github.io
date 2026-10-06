import base64
import tempfile
import unittest
from pathlib import Path

from server import ConflictError, create_article, read_article, save_article


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jEyoAAAAASUVORK5CYII=')
COVER = {'data': base64.b64encode(PNG).decode()}


class CoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'content'
        (self.root / 'diary').mkdir(parents=True)
        self.backups = self.root.parent / '.tools' / 'backups'

    def tearDown(self):
        self.temp.cleanup()

    def create(self, cover=COVER):
        return create_article(self.root, 'diary', 'Diary', '2000-01-02', 'Only diary text', 'a' * 32, cover=cover)[0]

    def test_new_diary_copies_original_cover_into_bundle_without_body_image(self):
        article = self.create()
        bundle = (self.root / article['path']).parent
        image = next(bundle.glob('feature-editor-*.png'))
        self.assertEqual(image.read_bytes(), PNG)
        self.assertEqual(article['body'].strip(), 'Only diary text')
        self.assertNotIn('![', article['body'])
        self.assertIn('featureimage: "' + image.name + '"', article['content'])
        self.assertIn('showHero: false', article['content'])
        self.assertTrue(article['cover_url'].startswith('/media/content/diary/'))
        self.create()
        self.assertEqual(len(list(bundle.glob('feature-editor-*'))), 1)

    def test_existing_cover_is_detected_and_preserved_without_selection(self):
        article = self.create(cover=None)
        bundle = (self.root / article['path']).parent
        old = bundle / 'campus-feature.JPG'
        old.write_bytes(b'\xff\xd8\xfforiginal bytes')
        current = read_article(self.root, article['path'])
        self.assertTrue(current['cover_url'].endswith('campus-feature.JPG'))
        saved = save_article(self.root, current['path'], 'Changed title', current['body'], current['revision'], self.backups)
        self.assertEqual(saved['cover_url'], current['cover_url'])
        self.assertEqual(old.read_bytes(), b'\xff\xd8\xfforiginal bytes')

    def test_replaces_cover_without_deleting_old_images_or_inserting_body_image(self):
        article = self.create(cover=None)
        bundle = (self.root / article['path']).parent
        old = bundle / 'feature-old.jpg'
        old.write_bytes(b'\xff\xd8\xffold')
        saved = save_article(self.root, article['path'], article['title'], article['body'], article['revision'], self.backups, COVER)
        self.assertTrue(old.exists())
        self.assertEqual(saved['body'], article['body'])
        self.assertIn('feature-editor-', saved['content'])
        again = save_article(self.root, saved['path'], saved['title'], saved['body'], saved['revision'], self.backups)
        self.assertEqual(again['cover_url'], saved['cover_url'])

    def test_flat_markdown_uses_hugo_asset_cover(self):
        path = self.root / 'diary' / 'flat.md'
        path.write_text('---\ntitle: Flat\n---\nText\n', encoding='utf-8')
        article = read_article(self.root, 'diary/flat.md')
        saved = save_article(self.root, article['path'], article['title'], article['body'], article['revision'], self.backups, COVER)
        image = next((self.root.parent / 'assets' / 'editor-covers').glob('*.png'))
        self.assertEqual(image.read_bytes(), PNG)
        self.assertIn('featureimage: "editor-covers/', saved['content'])
        self.assertTrue(saved['cover_url'].startswith('/media/assets/editor-covers/'))

    def test_invalid_cover_and_stale_revision_write_no_images(self):
        for cover in [{'data': 'invalid'}, {'data': base64.b64encode(b'<svg/>').decode()}, 'bad']:
            with self.subTest(cover=cover), self.assertRaises(ValueError):
                self.create(cover)
        self.assertEqual(list(self.root.rglob('*.md')), [])
        article = self.create(cover=None)
        with self.assertRaises(ConflictError):
            save_article(self.root, article['path'], article['title'], article['body'], 'stale', self.backups, COVER)
        self.assertEqual(list(self.root.rglob('*.png')), [])
