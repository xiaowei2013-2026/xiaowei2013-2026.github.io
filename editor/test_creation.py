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

    def tearDown(self):
        self.temp.cleanup()

    def create(self, module='diary', title='新文章', day='2000-01-02', body='## 正文\n\n内容',
               identifier='a' * 32, quote=None):
        return create_article(self.root, module, title, day, body, identifier, quote)

    def test_categories_create_public_markdown_and_stable_urls(self):
        for module, folder in [('diary', 'diary'), ('english', 'english/notes'),
                               ('reading', 'reading/other'), ('other', 'other/notes')]:
            with self.subTest(module=module):
                article, url = self.create(module=module)
                self.assertTrue(article['path'].startswith(folder + '/2000/01/'))
                text = (self.root / article['path']).read_text(encoding='utf-8')
                self.assertIn('draft: false', text)
                self.assertIn('url: ' + json.dumps(url), text)
                self.assertEqual(article['title'], '新文章')
                self.assertIn('## 正文', article['body'])
                self.assertTrue(article['editable'])

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
        for data in [{'module': '../outside'}, {'title': ''}, {'body': ''}, {'day': '2000-02-30'},
                     {'day': '2999-01-01'}, {'identifier': '../outside'}, {'body': '{{< chart >}}'}]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.create(**data)
        self.assertEqual(list(self.root.rglob('*.md')), [])

    def test_quote_metadata_and_body_and_duplicate_checks(self):
        fields = {'quote': '成长来自每天的记录。', 'author': '作者', 'work': '出处', 'kind': '名言'}
        article, _ = self.create(module='quotes', body='个人感想', quote=fields)
        self.assertEqual(article['path'], 'quotes/2000/01/2000-01-02.md')
        self.assertIn('> 成长来自每天的记录。', article['body'])
        self.assertIn('个人感想', article['body'])
        for day, quote in [('2000-01-03', fields), ('2000-01-02', {'quote': '另一条不同的金句'})]:
            with self.assertRaises(ConflictError):
                self.create(module='quotes', day=day, quote=quote, identifier='b' * 32)
        with self.assertRaises(ValueError):
            self.create(module='quotes', day='2000-01-04', quote={'quote': '！！'})

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
