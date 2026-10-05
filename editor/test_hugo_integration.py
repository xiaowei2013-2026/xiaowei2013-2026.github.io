"""Exercise authentication, saving and original Hugo rendering in an isolated site."""
import hashlib
import base64
import http.client
import json
import os
import re
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from auth import set_password
from hugo_preview import HugoPreview
from server import PROJECT_ROOT, make_handler, read_article


class HugoIntegrationTests(unittest.TestCase):
    def test_original_site_proxy_and_saved_article_rebuild(self):
        executable = PROJECT_ROOT / '.tools' / 'hugo' / ('hugo.exe' if os.name == 'nt' else 'hugo')
        if not executable.exists():
            self.skipTest('Project Hugo executable is unavailable')
        with tempfile.TemporaryDirectory(prefix='growth-hugo-test-', dir=PROJECT_ROOT / '.tools') as directory:
            root = Path(directory)
            root.joinpath('hugo.yaml').write_text(
                'title: Original theme fixture\ntheme: blowfish\nthemesDir: ' +
                json.dumps(str(PROJECT_ROOT / 'themes')) + '\nparams:\n  article:\n    showTableOfContents: true\n', encoding='utf-8')
            partial = root / 'layouts' / 'partials' / 'extend-head-uncached.html'
            partial.parent.mkdir(parents=True)
            partial.write_bytes((PROJECT_ROOT / 'layouts' / 'partials' / partial.name).read_bytes())
            article = root / 'content' / 'note' / 'index.md'
            article.parent.mkdir(parents=True)
            article.write_text('---\ntitle: Original fixture\n---\n## Original heading\n\nOriginal body\n', encoding='utf-8')
            set_password(root / '.tools' / 'editor-auth.json', 'isolated-hugo-password')
            preview = HugoPreview(root, 0, executable)
            handler = make_handler(root / 'content', site_port=preview.port, site_refresh=preview.refresh)
            handler.log_message = lambda *args: None
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
            preview.public_port = server.server_port
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            try:
                preview.start()
                thread.start()
                connection.request('GET', '/note/')
                response = connection.getresponse()
                html = response.read().decode('utf-8')
                self.assertEqual(response.status, 200)
                self.assertIn('single_header', html)
                self.assertIn('Original heading', html)
                self.assertIn('/_editor/inline.js', html)
                self.assertIn('note/index.md', html)
                connection.request('GET', '/_editor/inline.js')
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                connection.request('GET', '/api/config')
                token = json.loads(connection.getresponse().read())['token']
                connection.request('POST', '/api/login', json.dumps({'password': 'isolated-hugo-password'}),
                                   {'Content-Type': 'application/json', 'X-Editor-Token': token})
                response = connection.getresponse()
                cookie = response.getheader('Set-Cookie').split(';')[0]
                token = json.loads(response.read())['token']
                before = read_article(root / 'content', 'note/index.md')
                data = {'path': 'note/index.md', 'title': 'Updated fixture',
                        'body': '## Updated heading\n\nSaved fixture paragraph\n', 'revision': before['revision']}
                connection.request('POST', '/api/save', json.dumps(data),
                                   {'Content-Type': 'application/json', 'X-Editor-Token': token, 'Cookie': cookie})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                saved = json.loads(response.read())['article']
                for _ in range(40):
                    connection.request('GET', '/note/')
                    html = connection.getresponse().read().decode('utf-8')
                    if saved['revision'] in html:
                        break
                    time.sleep(0.1)
                self.assertIn(saved['revision'], html)
                self.assertIn('Updated fixture', html)
                self.assertIn('Saved fixture paragraph', html)
                self.assertIn('#updated-heading', html)
                self.assertEqual(saved['revision'], hashlib.sha256(article.read_bytes()).hexdigest())
                image = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jEyoAAAAASUVORK5CYII=')
                headers = {'Content-Type': 'application/json', 'X-Editor-Token': token, 'Cookie': cookie}
                connection.request('POST', '/api/upload-new', json.dumps({'data': base64.b64encode(image).decode()}), headers)
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                image_url = json.loads(response.read())['url']
                create = {'module': 'english', 'title': 'Created article', 'date': '2000-01-02',
                          'body': '## New heading\n\n![picture](' + image_url + ')', 'identifier': 'e' * 32}
                connection.request('POST', '/api/create', json.dumps(create), headers)
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                created = json.loads(response.read())
                for _ in range(40):
                    connection.request('GET', created['url'])
                    response = connection.getresponse()
                    html = response.read().decode('utf-8')
                    if response.status == 200 and created['article']['revision'] in html:
                        break
                    time.sleep(0.1)
                self.assertTrue('Created article' in html, (root / '.tools' / 'editor-hugo.log').read_text(encoding='utf-8')[-3000:])
                self.assertIn('New heading', html)
                self.assertIn(created['article']['revision'], html)
                connection.request('GET', image_url)
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), image)
                connection.request('POST', '/api/delete', json.dumps({'path': created['article']['path'],
                    'revision': created['article']['revision'], 'url': created['url']}), headers)
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                deleted = json.loads(response.read())['item']
                for _ in range(40):
                    connection.request('GET', created['url'])
                    response = connection.getresponse()
                    removed = response.status == 404
                    response.read()
                    if removed:
                        break
                    time.sleep(0.1)
                self.assertTrue(removed, 'Hugo still serves the deleted article')
                connection.request('GET', '/api/trash', headers={'Cookie': cookie})
                self.assertEqual(json.loads(connection.getresponse().read())['items'][0]['id'], deleted['id'])
                connection.request('POST', '/api/restore', json.dumps({'id': deleted['id']}), headers)
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                for _ in range(40):
                    connection.request('GET', created['url'])
                    response = connection.getresponse()
                    html = response.read().decode('utf-8')
                    if response.status == 200 and created['article']['revision'] in html:
                        break
                    time.sleep(0.1)
                self.assertIn(created['article']['revision'], html)
            finally:
                connection.close()
                if thread.is_alive():
                    server.shutdown()
                    thread.join(timeout=5)
                server.server_close()
                preview.close()


if __name__ == '__main__':
    unittest.main()
