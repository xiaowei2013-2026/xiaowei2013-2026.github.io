import unittest
from pathlib import Path
from unittest.mock import patch

from git_sync import SyncError
from sync_overview import SyncOverview
import test_git_sync as git_tests


class OverviewTests(unittest.TestCase):
    run_git = git_tests.SyncTests.run_git
    tearDown = git_tests.SyncTests.tearDown

    def setUp(self):
        git_tests.SyncTests.setUp(self)
        self.overview = SyncOverview(self.root)

    def test_batch_sync_adds_modifies_deletes_and_preserves_other_staged_work(self):
        deleted = self.root / 'content' / 'deleted.md'
        deleted.write_text('old')
        self.run_git('add', 'content/deleted.md')
        self.run_git('commit', '-m', 'Existing article')
        self.run_git('push', 'origin', 'main')
        deleted.unlink()
        self.article.write_text('Changed existing article')
        new = self.root / 'content' / '中文 空格[1].md'
        new.write_text('New article', encoding='utf-8')
        image = self.root / 'static' / 'images' / 'new.png'
        image.parent.mkdir(parents=True)
        image.write_bytes(b'image')
        (self.root / 'other.txt').write_text('staged unrelated change')
        self.run_git('add', 'other.txt')
        secret = self.root / '.tools' / 'private.json'
        secret.parent.mkdir(parents=True)
        secret.write_text('private content')
        plan = self.overview.plan()
        self.assertEqual(len(plan['changes']), 4)
        self.assertEqual(plan['other_changes'], 1)
        result = self.overview.sync_batch('content', plan['revision'])
        self.assertTrue(result['github_synced'])
        self.assertEqual(self.run_git('diff', '--cached', '--name-only'), 'other.txt')
        published = self.run_git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD')
        self.assertNotIn('other.txt', published)
        self.assertNotIn('.tools', published)
        self.assertEqual(self.overview.plan()['changes'], [])

    def test_changed_file_list_requires_new_review(self):
        self.article.write_text('Reviewed version')
        plan = self.overview.plan()
        self.article.write_text('Later version')
        head = self.run_git('rev-parse', 'HEAD')
        with self.assertRaises(SyncError):
            self.overview.sync_batch('content', plan['revision'])
        self.assertEqual(self.run_git('rev-parse', 'HEAD'), head)

    def test_pending_batch_retries_same_commit(self):
        self.article.write_text('New body')
        plan = self.overview.plan()
        git = self.overview.git
        def fail_push(*args, **kwargs):
            if args[0] == 'push':
                raise SyncError('Simulated network failure')
            return git(*args, **kwargs)
        with patch.object(self.overview, 'git', side_effect=fail_push):
            with self.assertRaises(SyncError):
                self.overview.sync_batch('content', plan['revision'])
        head = self.run_git('rev-parse', 'HEAD')
        restarted = SyncOverview(self.root)
        retry = restarted.plan()
        self.assertTrue(retry['retry'])
        self.assertEqual(retry['revision'], plan['revision'])
        self.assertEqual(restarted.sync_batch('content', retry['revision'])['commit'], head)
        self.assertEqual(self.run_git('rev-list', '--count', 'HEAD'), '2')

    def test_empty_content_plan_excludes_website_code_and_does_not_commit(self):
        (self.root / 'README.md').write_text('Website change')
        plan = self.overview.plan()
        self.assertEqual(plan['changes'], [])
        self.assertEqual(plan['other_changes'], 1)
        self.assertFalse(self.overview.sync_batch('content', plan['revision'])['changed'])
        self.assertEqual(self.run_git('rev-list', '--count', 'HEAD'), '1')
        with self.assertRaises(ValueError):
            self.overview.plan('project')

    def test_pending_batch_with_new_file_modifications_is_blocked(self):
        self.article.write_text('Reviewed version')
        plan = self.overview.plan()
        git = self.overview.git
        def fail_push(*args, **kwargs):
            if args[0] == 'push':
                raise SyncError('Simulated network failure')
            return git(*args, **kwargs)
        with patch.object(self.overview, 'git', side_effect=fail_push):
            with self.assertRaises(SyncError):
                self.overview.sync_batch('content', plan['revision'])
        self.article.write_text('Modified after failed push')
        self.assertTrue(self.overview.plan()['blocked'])
