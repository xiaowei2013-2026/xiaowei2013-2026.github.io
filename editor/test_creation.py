import base64
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from server import ConflictError, create_article, upload_image


class CreationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'content'
        self.root.mkdir()
        for folder in ['diary', 'english/notes', 'reading/books/technology', 'reading/other', 'other/notes', 'quotes', 'quotes/2000/01', 'reading/logs']:
            (self.root / folder).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp.cleanup()

    def create(self, directory='diary', title='新文章', day='2000-01-02', body='## 正文\n\n内容',
               identifier='a' * 32, quote=None, reading=None):
        return create_article(self.root, directory, title, day, body, identifier, quote, reading)

    def test_current_folder_is_used_without_extra_date_directories(self):
        for folder in ['diary', 'english/notes', 'reading/other', 'other/notes', '']:
            with self.subTest(folder=folder):
                article, url = self.create(directory=folder)
                self.assertEqual(Path(article['path']).parent.parent.as_posix(), folder or '.')
                text = (self.root / article['path']).read_text(encoding='utf-8')
                self.assertIn('draft: false', text)
                self.assertIn('url: ' + json.dumps(url), text)
                self.assertEqual(article['title'], '新文章')
                self.assertTrue(article['editable'])

    def test_book_created_in_current_category_has_stable_book_id(self):
        article, url = self.create(directory='reading/books/technology')
        text = (self.root / article['path']).read_text(encoding='utf-8')
        self.assertEqual(Path(article['path']).parent.parent.as_posix(), 'reading/books/technology')
        self.assertIn('entry_type: "book"', text)
        self.assertIn('book_id: "book-' + 'a' * 32 + '"', text)
        self.assertTrue(url.startswith('/reading/books/technology/'))
        self.assertTrue(article['editable'])

    def test_reading_log_requires_existing_book_and_valid_minutes(self):
        self.create(directory='reading/books/technology')
        metadata = {'book_id': 'book-' + 'a' * 32, 'reading_minutes': '30', 'pages': '10'}
        article, _ = self.create(directory='reading/logs', identifier='b' * 32, reading=metadata)
        self.assertIn('reading_minutes: 30', (self.root / article['path']).read_text(encoding='utf-8'))
        with self.assertRaises(ConflictError):
            self.create(directory='reading/logs', identifier='c' * 32, reading=metadata)
        with self.assertRaises(ValueError):
            self.create(directory='reading/logs', identifier='d' * 32, reading={'book_id': 'missing'})

    def test_retries_and_concurrent_requests_do_not_duplicate_or_overwrite(self):
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(lambda _: self.create(), range(3)))
        self.assertEqual(len(list(self.root.rglob('*.md'))), 1)
        self.assertEqual(len({article['path'] for article, _ in results}), 1)
        with self.assertRaises(ConflictError):
            self.create(body='Changed request with same identifier')
        self.assertEqual(len(list(self.root.rglob('*.md'))), 1)

    def test_two_articles_on_same_day_can_be_created(self):
        first, _ = self.create()
        second, _ = self.create(identifier='b' * 32)
        self.assertNotEqual(first['path'], second['path'])

    def test_invalid_input_creates_no_files(self):
        for data in [{'directory': '../outside'}, {'directory': '/absolute'}, {'directory': 'missing'}, {'directory': 'diary/../quotes'}, {'directory': '.hidden'}, {'title': ''}, {'body': ''}, {'day': '2000-02-30'},
                     {'day': '2999-01-01'}, {'identifier': '../outside'}, {'body': '{{< chart >}}'}]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.create(**data)
        self.assertEqual(list(self.root.rglob('*.md')), [])

    def test_quote_metadata_and_body_and_duplicate_checks(self):
        fields = {'quote': '成长来自每天的记录。', 'author': '作者', 'work': '出处', 'kind': '名言'}
        article, _ = self.create(directory='quotes/2000/01', body='个人感想', quote=fields)
        self.assertEqual(article['path'], 'quotes/2000/01/2000-01-02.md')
        self.assertIn('> 成长来自每天的记录。', article['body'])
        self.assertIn('个人感想', article['body'])
        for day, quote in [('2000-01-03', fields), ('2000-01-02', {'quote': '另一条不同的金句'})]:
            with self.assertRaises(ConflictError):
                self.create(directory='quotes/2000/01', day=day, quote=quote, identifier='b' * 32)
        with self.assertRaises(ValueError):
            self.create(directory='quotes/2000/01', day='2000-01-04', quote={'quote': '！！'})

    def test_images_can_be_uploaded_before_article_is_saved(self):
        image = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jEyoAAAAASUVORK5CYII=')
        url = upload_image(self.root, None, base64.b64encode(image).decode())
        self.assertTrue(url.startswith('/images/editor/'))
        self.assertEqual((self.root.parent / 'static' / url.lstrip('/')).read_bytes(), image)
        self.assertEqual(list(self.root.rglob('*.md')), [])
        article, _ = self.create(body='![图片](' + url + ')')
        self.assertIn(url, article['body'])


if __name__ == '__main__':
    unittest.main()
