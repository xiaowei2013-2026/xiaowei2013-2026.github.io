import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from auth import AuthError, AuthStore, IDLE_SECONDS, SESSION_SECONDS, set_password
from server import make_handler, read_article

PASSWORD = 'isolated-owner-password'


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / '.tools' / 'editor-auth.json'
        set_password(self.path, PASSWORD)
        self.auth = AuthStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_password_is_salted_and_not_stored_as_plaintext(self):
        before = json.loads(self.path.read_text())
        self.assertNotIn(PASSWORD, self.path.read_text())
        set_password(self.path, PASSWORD)
        after = json.loads(self.path.read_text())
        self.assertNotEqual(before['salt'], after['salt'])
        self.assertNotEqual(before['digest'], after['digest'])
        with self.assertRaises(ValueError):
            set_password(self.path, 'short')
        self.assertEqual(json.loads(self.path.read_text()), after)

    def test_login_expiry_logout_and_password_change_invalidate_sessions(self):
        with patch('auth.time.monotonic', return_value=100):
            identifier, session = self.auth.login(PASSWORD)
            cookie = 'growth_owner=' + identifier
            self.assertIsNotNone(self.auth.session(cookie))
        with patch('auth.time.monotonic', return_value=100 + IDLE_SECONDS + 1):
            self.assertIsNone(self.auth.session(cookie))
        identifier, _ = self.auth.login(PASSWORD)
        cookie = 'growth_owner=' + identifier
        set_password(self.path, 'different-owner-password')
        self.assertIsNone(self.auth.session(cookie))
        identifier, _ = self.auth.login('different-owner-password')
        self.auth.logout()
        self.assertIsNone(self.auth.session('growth_owner=' + identifier))

    def test_absolute_expiry_even_when_recently_active(self):
        with patch('auth.time.monotonic', return_value=100):
            identifier, session = self.auth.login(PASSWORD)
            session['last_seen'] = 100 + SESSION_SECONDS - 1
        with patch('auth.time.monotonic', return_value=100 + SESSION_SECONDS):
            self.assertIsNone(self.auth.session('growth_owner=' + identifier))

    def test_bad_password_rate_limit_and_recovery(self):
        with patch('auth.time.monotonic', return_value=100):
            for _ in range(5):
                with self.assertRaises(AuthError) as error:
                    self.auth.login('wrong')
                self.assertEqual(error.exception.status, 401)
            with self.assertRaises(AuthError) as error:
                self.auth.login(PASSWORD)
            self.assertEqual(error.exception.status, 429)
        with patch('auth.time.monotonic', return_value=401):
            self.assertTrue(self.auth.login(PASSWORD))

    def test_missing_or_corrupt_configuration_fails_closed(self):
        self.path.unlink()
        self.assertFalse(self.auth.configured())
        with self.assertRaises(AuthError):
            self.auth.login(PASSWORD)
        self.path.write_text('{}')
        with self.assertRaises(AuthError):
            self.auth.session(None)

    def test_http_public_reads_owner_writes_csrf_and_logout(self):
        content = self.root / 'content'
        content.mkdir()
        article = content / 'note.md'
        original = b'---\ntitle: Note\n---\nOriginal\n'
        article.write_bytes(original)
        handler = make_handler(content, auth_store=self.auth)
        handler.log_message = lambda *args: None
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        def request(method, route, payload=None, token='', cookie='', origin=None):
            headers = {'Content-Type': 'application/json', 'X-Editor-Token': token, 'Cookie': cookie}
            if origin:
                headers['Origin'] = origin
            connection.request(method, route, json.dumps(payload) if payload is not None else None, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read()), response.getheader('Set-Cookie')
        try:
            status, config, _ = request('GET', '/api/config')
            self.assertEqual(status, 200)
            self.assertFalse(config['authenticated'])
            self.assertEqual(request('GET', '/api/articles')[0], 200)
            token = config['token']
            for route in ['/api/save', '/api/upload', '/api/sync', '/api/create', '/api/upload-new', '/api/delete', '/api/restore', '/api/sync-delete', '/api/sync-batch']:
                self.assertEqual(request('POST', route, {}, token)[0], 401)
            self.assertEqual(request('GET', '/api/trash')[0], 404)
            self.assertEqual(request('GET', '/api/sync-plan')[0], 404)
            self.assertEqual(article.read_bytes(), original)
            self.assertEqual(request('POST', '/api/login', {'password': PASSWORD}, token,
                                     origin='https://attacker.invalid')[0], 403)
            status, login, cookie = request('POST', '/api/login', {'password': PASSWORD}, token)
            self.assertEqual(status, 200)
            self.assertIn('HttpOnly', cookie)
            self.assertIn('SameSite=Strict', cookie)
            cookie = cookie.split(';')[0]
            self.assertNotEqual(login['token'], token)
            self.assertTrue(request('GET', '/api/config', cookie=cookie)[1]['authenticated'])
            for route in ['/api/sync', '/api/sync-batch', '/api/restore', '/api/sync-delete']:
                self.assertEqual(request('POST', route, {}, login['token'], cookie)[0], 404)
            self.assertEqual(request('POST', '/api/save', {}, token, cookie)[0], 403)
            payload = {'path': 'note.md', 'title': 'Updated', 'body': 'New body',
                       'revision': read_article(content, 'note.md')['revision']}
            self.assertEqual(request('POST', '/api/save', payload, login['token'], cookie)[0], 200)
            self.assertIn(b'New body', article.read_bytes())
            status, _, cleared = request('POST', '/api/logout', {}, login['token'], cookie)
            self.assertEqual(status, 200)
            self.assertIn('Max-Age=0', cleared)
            self.assertEqual(request('POST', '/api/save', payload, login['token'], cookie)[0], 401)
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
