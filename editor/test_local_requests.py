import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from server import make_handler, read_article


class LocalRequestTests(unittest.TestCase):
    def test_passwordless_edits_require_local_host_origin_and_request_token(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = root / 'content'
            content.mkdir()
            article = content / 'note.md'
            original = b'---\ntitle: Note\n---\nOriginal\n'
            article.write_bytes(original)
            handler = make_handler(content)
            handler.log_message = lambda *args: None
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            def request(method, route, payload=None, token='', **extra):
                headers = {'Content-Type': 'application/json', 'X-Editor-Token': token, **extra}
                connection.request(method, route, json.dumps(payload) if payload is not None else None, headers)
                response = connection.getresponse()
                return response.status, json.loads(response.read()), response.getheader('Set-Cookie')
            try:
                status, config, cookie = request('GET', '/api/config')
                self.assertEqual(status, 200)
                self.assertTrue(config['local_only'])
                self.assertNotIn('authenticated', config)
                self.assertIsNone(cookie)
                token = config['token']
                self.assertEqual(request('POST', '/api/save', {}, '')[0], 403)
                self.assertEqual(request('POST', '/api/create-category', {}, '')[0], 403)
                self.assertEqual(request('POST', '/api/save', {}, 'incorrect')[0], 403)
                self.assertEqual(request('POST', '/api/save', {}, token, Origin='https://attacker.invalid')[0], 403)
                self.assertEqual(request('POST', '/api/save', {}, token, Origin='null')[0], 403)
                self.assertEqual(request('POST', '/api/save', {}, token, **{'Sec-Fetch-Site': 'cross-site'})[0], 403)
                self.assertEqual(request('POST', '/api/save', {}, token, Host='external.example')[0], 403)
                self.assertEqual(request('GET', '/api/config', Host='external.example')[0], 403)
                self.assertEqual(article.read_bytes(), original)
                payload = {'path': 'note.md', 'title': 'Updated', 'body': 'New body',
                           'revision': read_article(content, 'note.md')['revision']}
                local_origin = 'http://127.0.0.1:' + str(server.server_port)
                self.assertEqual(request('POST', '/api/save', payload, token, Origin=local_origin)[0], 200)
                self.assertIn(b'New body', article.read_bytes())
                self.assertFalse((root / '.tools' / 'editor-auth.json').exists())
                for route in ['/api/login', '/api/logout', '/api/sync', '/api/restore']:
                    self.assertEqual(request('POST', route, {}, token)[0], 404)
                other_handler = make_handler(content)
                other_server = ThreadingHTTPServer(('127.0.0.1', 0), other_handler)
                other_thread = threading.Thread(target=other_server.serve_forever, daemon=True)
                other_thread.start()
                other_connection = http.client.HTTPConnection('127.0.0.1', other_server.server_port, timeout=5)
                try:
                    other_connection.request('GET', '/api/config')
                    other_token = json.loads(other_connection.getresponse().read())['token']
                    self.assertNotEqual(token, other_token)
                    self.assertEqual(request('POST', '/api/save', payload, other_token)[0], 403)
                finally:
                    other_connection.close()
                    other_server.shutdown()
                    other_server.server_close()
                    other_thread.join(timeout=5)
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
