"""Review and publish a working-tree snapshot without consuming unrelated staged work."""
import hashlib
import json
import os
from pathlib import Path

from git_sync import GitSync, SyncError


class SyncOverview(GitSync):
    SCOPES = {'content'}
    IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.avif'}

    def in_scope(self, relative, scope):
        path = Path(relative)
        if (path.is_absolute() or '..' in path.parts or not path.parts or
                path.parts[0] in {'.git', '.tools', '.codex', '.agents', '.aws', 'public'} or
                relative.startswith('resources/_gen/') or relative == '.hugo_build.lock'):
            return False
        return (scope == 'project' or (relative.startswith('content/') and (path.suffix.lower() == '.md' or path.suffix.lower() in self.IMAGE_EXTENSIONS)) or
                (relative.startswith('static/images/') and path.suffix.lower() in self.IMAGE_EXTENSIONS))

    def fingerprint(self, relative):
        path = self.root / relative
        if not path.parent.resolve().is_relative_to(self.root):
            raise SyncError('改动路径超出项目范围，请在终端检查。')
        if path.is_symlink():
            return hashlib.sha256(('link:' + os.readlink(path)).encode()).hexdigest()
        if not path.exists():
            return 'deleted'
        if not path.is_file():
            raise SyncError('目录或主题子模块的改动请在终端处理后再同步。')
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def changes(self):
        entries = self.git('diff', '--name-status', '--no-renames', '-z', 'HEAD', raw=True).split('\0')
        changes = {}
        for position in range(0, len(entries) - 1, 2):
            action, path = entries[position:position + 2]
            if action and path:
                changes[path] = {'path': path, 'action': action[0]}
        for path in self.git('ls-files', '--others', '--exclude-standard', '-z', raw=True).split('\0'):
            if path:
                changes[path] = {'path': path, 'action': 'A'}
        return [changes[path] for path in sorted(changes) if self.in_scope(path, 'project')]

    @staticmethod
    def revision(scope, snapshot, head):
        return hashlib.sha256(json.dumps([scope, head, snapshot], sort_keys=True).encode()).hexdigest()

    def plan(self, scope='content'):
        if scope not in self.SCOPES:
            raise ValueError('同步范围无效')
        head = self.git('rev-parse', 'HEAD')
        remote = self.git('rev-parse', 'refs/remotes/origin/main')
        all_changes = self.changes()
        snapshot = [{**item, 'fingerprint': self.fingerprint(item['path'])} for item in all_changes
                    if self.in_scope(item['path'], scope)]
        pending = json.loads(self.state.read_text(encoding='utf-8')) if self.state.exists() else None
        retry = bool(pending and head == pending['commit'] and head != remote)
        blocked = ''
        if self.git('branch', '--show-current') != 'main':
            blocked = '请先切换到 main 分支。'
        if retry:
            if pending.get('operation') == 'batch' and pending.get('scope') == scope:
                snapshot = pending['snapshot']
                revision = pending['revision']
                if any(self.fingerprint(item['path']) != item['fingerprint'] for item in snapshot):
                    blocked = '上次提交还未推送，但文件又发生修改，请在终端处理未推送提交。'
            else:
                revision = self.revision(scope, snapshot, head)
                blocked = '另有未推送的同步提交，请先在原文章或原同步范围中重试。'
        else:
            revision = self.revision(scope, snapshot, head)
        counts = self.git('rev-list', '--left-right', '--count', 'HEAD...refs/remotes/origin/main').split()
        ahead, behind = map(int, counts)
        if behind or (ahead and not retry):
            blocked = '本地提交与 GitHub 分支不一致，请先在终端处理。'
        return {'scope': scope, 'changes': snapshot, 'revision': revision, 'retry': retry,
                'ahead': ahead, 'behind': behind, 'blocked': blocked,
                'other_changes': sum(not self.in_scope(item['path'], scope) for item in all_changes)}

    def sync_batch(self, scope, revision):
        plan = self.plan(scope)
        if plan['blocked']:
            raise SyncError(plan['blocked'])
        if plan['revision'] != revision:
            raise SyncError('文件清单已变化，请刷新同步清单，检查后重试。')
        snapshot = plan['changes']
        def check():
            if any(self.fingerprint(item['path']) != item['fingerprint'] for item in snapshot):
                raise SyncError('同步期间文件发生修改，请刷新清单后重试。')
        result = self.sync_paths('batch:' + scope, revision, [item['path'] for item in snapshot],
                                 check, 'batch', {'scope': scope, 'snapshot': snapshot})
        result['files'] = len(snapshot)
        return result
