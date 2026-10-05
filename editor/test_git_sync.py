import hashlib
import http.client
import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from git_sync import GitSync, SyncError
from server import make_handler, create_article, upload_image
from auth import set_password


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        self.remote = Path(self.temp.name) / 'remote.git'
        self.run_git('init', '--initial-branch=main')
        self.run_git('config', 'user.name', 'Test')
        self.run_git('config', 'user.email', 'test@example.invalid')
        self.article = self.root / 'content' / 'diary' / 'index.md'
        self.article.parent.mkdir(parents=True)
        self.article.write_text('---\ntitle: Article\n---\nOriginal\n', encoding='utf-8')
        (self.root / 'other.txt').write_text('original')
        self.run_git('add', '.')
        self.run_git('commit', '-m', 'Initial')
        self.run_git('init', '--bare', str(self.remote))
        self.run_git('remote', 'add', 'origin', str(self.remote))
        self.run_git('push', '-u', 'origin', 'main')
        self.syncer = GitSync(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def run_git(self, *args):
        result = subprocess.run(['git', *args], cwd=self.root, capture_output=True,
                                text=True, encoding='utf-8', errors='replace',
                                env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'}, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def revision(self):
        return hashlib.sha256(self.article.read_bytes()).hexdigest()

    def test_only_article_and_referenced_uploads_are_published(self):
        name = 'a' * 32 + '.png'
        directory = self.article.parent / 'editor-images'
        directory.mkdir()
        (directory / name).write_bytes(b'image')
        (directory / ('b' * 32 + '.png')).write_bytes(b'orphan')
        self.article.write_text('---\ntitle: Article\n---\n![picture](editor-images/' + name + ')\n')
        (self.root / 'other.txt').write_text('staged other change')
        self.run_git('add', 'other.txt')
        (self.root / 'unfinished.txt').write_text('private local work')
        result = self.syncer.sync(self.article, self.revision())
        self.assertTrue(result['github_synced'])
        committed = self.run_git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').splitlines()
        self.assertEqual(committed, ['content/diary/editor-images/' + name, 'content/diary/index.md'])
        self.assertEqual(self.run_git('diff', '--cached', '--name-only'), 'other.txt')
        self.assertEqual(self.run_git('rev-parse', 'HEAD'), self.run_git('rev-parse', 'origin/main'))
        self.assertEqual(self.run_git('show', 'HEAD:other.txt'), 'original')
        self.assertFalse(self.syncer.state.exists())

    def test_failed_push_retries_same_commit_after_restart(self):
        self.article.write_text('Changed article')
        git = self.syncer.git
        def fail_push(*args, **kwargs):
            if args[0] == 'push':
                raise SyncError('Test network failure')
            return git(*args, **kwargs)
        with patch.object(self.syncer, 'git', side_effect=fail_push):
            with self.assertRaises(SyncError):
                self.syncer.sync(self.article, self.revision())
        head = self.run_git('rev-parse', 'HEAD')
        self.assertTrue(self.syncer.state.exists())
        result = GitSync(self.root).sync(self.article, self.revision())
        self.assertEqual(result['commit'], head)
        self.assertEqual(self.run_git('rev-list', '--count', 'HEAD'), '2')

    def test_unrelated_local_commit_is_not_pushed(self):
        (self.root / 'other.txt').write_text('unrelated')
        self.run_git('add', 'other.txt')
        self.run_git('commit', '-m', 'Unrelated local work')
        before = self.run_git('rev-parse', 'origin/main')
        self.article.write_text('Changed article')
        with self.assertRaises(SyncError):
            self.syncer.sync(self.article, self.revision())
        self.assertEqual(self.run_git('rev-parse', 'origin/main'), before)

    def test_changed_revision_and_missing_image_do_not_commit(self):
        revision = self.revision()
        head = self.run_git('rev-parse', 'HEAD')
        self.article.write_text('Changed')
        with self.assertRaises(SyncError):
            self.syncer.sync(self.article, revision)
        self.article.write_text('![missing](/images/editor/' + 'c' * 32 + '.png)')
        with self.assertRaises(SyncError):
            self.syncer.sync(self.article, self.revision())
        self.assertEqual(self.run_git('rev-parse', 'HEAD'), head)

    def test_no_changes_does_not_create_commit(self):
        head = self.run_git('rev-parse', 'HEAD')
        result = self.syncer.sync(self.article, self.revision())
        self.assertFalse(result['changed'])
        self.assertEqual(result['commit'], head)

    def test_tls_error_is_actionable_and_does_not_expose_credentials(self):
        result = subprocess.CompletedProcess([], 1, '', 'https://secret-token@example.invalid schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS')
        with patch('git_sync.subprocess.run', return_value=result):
            with self.assertRaises(SyncError) as error:
                self.syncer.git('fetch', 'origin')
        self.assertIn('普通 PowerShell', str(error.exception))
        self.assertNotIn('secret-token', str(error.exception))

    def test_new_article_and_uploaded_image_are_published_together(self):
        import base64
        url = upload_image(self.root / 'content', None, base64.b64encode(b'\x89PNG\r\n\x1a\nimage').decode())
        article, _ = create_article(self.root / 'content', 'diary', 'New article', '2000-01-02',
                                    '![picture](' + url + ')', 'd' * 32)
        result = self.syncer.sync(self.root / 'content' / article['path'], article['revision'])
        self.assertTrue(result['github_synced'])
        paths = self.run_git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').splitlines()
        self.assertEqual(sorted(paths), sorted(['content/' + article['path'], 'static' + url]))

    def test_deletion_publishes_only_article_and_can_be_restored_and_republished(self):
        from recycle_bin import RecycleBin
        (self.root / 'other.txt').write_text('unrelated staged change')
        self.run_git('add', 'other.txt')
        trash = RecycleBin(self.root / 'content')
        item = trash.delete('diary/index.md', self.revision(), 'Note')
        result = self.syncer.sync_deletion(self.article, item['revision'])
        self.assertTrue(result['github_synced'])
        self.assertEqual(self.run_git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD'), 'content/diary/index.md')
        self.assertEqual(self.run_git('diff', '--cached', '--name-only'), 'other.txt')
        trash.restore(item['id'])
        restored = self.syncer.sync(self.article, self.revision())
        self.assertTrue(restored['github_synced'])
        self.assertIn('Original', self.run_git('show', 'origin/main:content/diary/index.md'))

    def test_deletion_failed_push_retries_same_commit(self):
        revision = self.revision()
        self.article.unlink()
        git = self.syncer.git
        def fail_push(*args, **kwargs):
            if args[0] == 'push':
                raise SyncError('Test network failure')
            return git(*args, **kwargs)
        with patch.object(self.syncer, 'git', side_effect=fail_push):
            with self.assertRaises(SyncError):
                self.syncer.sync_deletion(self.article, revision)
        commit = self.run_git('rev-parse', 'HEAD')
        result = GitSync(self.root).sync_deletion(self.article, revision)
        self.assertEqual(result['commit'], commit)
        self.assertEqual(self.run_git('rev-list', '--count', 'HEAD'), '2')

    def test_never_published_deletion_requires_no_commit(self):
        head = self.run_git('rev-parse', 'HEAD')
        result = self.syncer.sync_deletion(self.root / 'content' / 'never-published.md', 'unused')
        self.assertFalse(result['changed'])
        self.assertEqual(self.run_git('rev-parse', 'HEAD'), head)

    def test_sync_http_requires_token_and_returns_sync_result(self):
        set_password(self.root / '.tools' / 'editor-auth.json', 'isolated-test-password')
        handler = make_handler(self.root / 'content')
        handler.log_message = lambda *args: None
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        payload = json.dumps({'path': 'diary/index.md', 'revision': self.revision()})
        try:
            connection.request('POST', '/api/sync', payload, {'Content-Type': 'application/json'})
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            connection.request('GET', '/api/config')
            token = json.loads(connection.getresponse().read())['token']
            connection.request('POST', '/api/login', json.dumps({'password': 'isolated-test-password'}),
                               {'Content-Type': 'application/json', 'X-Editor-Token': token})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            cookie = response.getheader('Set-Cookie').split(';')[0]
            token = json.loads(response.read())['token']
            with patch.object(GitSync, 'sync', return_value={'github_synced': True, 'changed': False}) as sync:
                connection.request('POST', '/api/sync', payload,
                                   {'Content-Type': 'application/json', 'X-Editor-Token': token, 'Cookie': cookie})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertTrue(json.loads(response.read())['github_synced'])
                sync.assert_called_once_with(self.article.resolve(), self.revision())
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_remote_changes_are_not_overwritten(self):
        base = self.run_git('rev-parse', 'HEAD')
        (self.root / 'other.txt').write_text('remote change')
        self.run_git('add', 'other.txt')
        self.run_git('commit', '-m', 'Remote advance')
        self.run_git('push', 'origin', 'main')
        self.run_git('reset', '--hard', base)
        self.article.write_text('Local article change')
        with self.assertRaises(SyncError):
            self.syncer.sync(self.article, self.revision())
        self.assertEqual(self.run_git('rev-parse', 'HEAD'), base)


if __name__ == '__main__':
    unittest.main()
