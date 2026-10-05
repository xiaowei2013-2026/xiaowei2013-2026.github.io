"""Publish one saved article using an isolated Git index."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


class SyncError(RuntimeError):
    pass


class GitSync:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.state = self.root / '.tools' / 'editor-sync.json'

    def git(self, *args, env=None, input=None, raw=False):
        environment = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_LITERAL_PATHSPECS': '1', **(env or {})}
        try:
            result = subprocess.run(['git', *args], cwd=self.root, env=environment,
                                    input=input, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=45)
        except (OSError, subprocess.TimeoutExpired):
            raise SyncError('Git 操作失败或超时，请检查 Git 安装和网络后重试。')
        if result.returncode:
            # Git output can contain credential-bearing URLs. Keep it out of HTTP responses.
            failure = result.stderr.casefold()
            if 'sec_e_no_credentials' in failure or 'acquirecredentialshandle failed' in failure:
                raise SyncError('编辑服务的 Windows 运行环境无法初始化 Git TLS 凭据。请关闭服务，在普通 PowerShell 中运行 .\\preview-editor.cmd，再重新登录发布。文章已保存在本地。')
            if any(message in failure for message in ('authentication failed', 'could not read username', 'terminal prompts disabled')):
                raise SyncError('GitHub 身份验证未完成。请在普通终端登录 GitHub 后重试，文章已保存在本地。')
            if any(message in failure for message in ('could not resolve host', 'failed to connect', 'connection timed out', 'could not resolve proxy')):
                raise SyncError('无法连接 GitHub，请检查网络和 Git 代理设置后重试，文章已保存在本地。')
            raise SyncError('Git 操作失败：' + args[0] + '。请检查网络、Git 身份和仓库权限后重试。')
        return result.stdout if raw else result.stdout.strip()

    def paths(self, article: Path):
        paths = {article.relative_to(self.root).as_posix()}
        text = article.read_text(encoding='utf-8-sig')
        # Only uploaded images referenced by this article, never the whole upload directory.
        for reference in re.findall(r'(?:editor-images/|/images/editor/)[a-f0-9]{32}\.(?:png|jpg|webp)', text):
            image = (self.root / 'static' / reference.lstrip('/') if reference.startswith('/')
                     else article.parent / reference).resolve()
            if not image.is_relative_to(self.root) or not image.is_file():
                raise SyncError('文章引用的上传图片缺失或路径无效，请检查图片后重试。')
            paths.add(image.relative_to(self.root).as_posix())
        return sorted(paths)

    def sync(self, article: Path, revision: str):
        def check():
            if hashlib.sha256(article.read_bytes()).hexdigest() != revision:
                raise SyncError('本地文章已经改变，请重新打开并检查内容后同步。')
        check()
        return self.sync_paths(article.relative_to(self.root).as_posix(), revision,
                               self.paths(article), check, 'update')

    def sync_deletion(self, article: Path, revision: str):
        article = article.resolve()
        if not article.is_relative_to(self.root / 'content') or article.suffix != '.md' or article.name == '_index.md':
            raise SyncError('删除路径无效')
        def check():
            if article.exists():
                raise SyncError('文章已经恢复到本地，不能发布删除。')
        check()
        relative = article.relative_to(self.root).as_posix()
        return self.sync_paths(relative, revision, [relative], check, 'delete')

    def sync_paths(self, relative, revision, paths, check, operation, details=None):
        if self.git('rev-parse', '--show-toplevel').replace('\\', '/') != self.root.as_posix():
            raise SyncError('文章目录必须是当前 Git 仓库根目录。')
        if self.git('branch', '--show-current') != 'main':
            raise SyncError('请切换到 main 分支后同步。')
        git_directory = Path(self.git('rev-parse', '--absolute-git-dir'))
        if any((git_directory / name).exists() for name in
               ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply')):
            raise SyncError('仓库正在合并或变基，请先在终端完成或取消该操作。')
        if self.git('ls-files', '--unmerged'):
            raise SyncError('仓库存在冲突，请先解决冲突。')
        self.git('remote', 'get-url', 'origin')
        self.git('fetch', '--no-tags', 'origin', 'refs/heads/main:refs/remotes/origin/main')
        head = self.git('rev-parse', 'HEAD')
        remote = self.git('rev-parse', 'refs/remotes/origin/main')
        pending = json.loads(self.state.read_text(encoding='utf-8')) if self.state.exists() else None
        if pending and head == pending['commit']:
            if remote == head:
                self.state.unlink()
                pending = None
            elif remote == pending['base']:
                if pending['article'] != relative or pending.get('operation', 'update') != operation:
                    raise SyncError('另一篇文章尚未同步完成，请先打开那篇文章重试同步。')
                if pending['revision'] != revision:
                    raise SyncError('上次提交尚未推送，文章又发生修改。请先在终端处理未推送的提交。')
                return self.push(pending)
        if head != remote:
            raise SyncError('本地提交和 GitHub 版本不一致，请先在终端处理，再同步文章。')
        if pending:
            self.state.unlink()
        if operation == 'delete' and not self.git('ls-tree', '--name-only', head, '--', relative):
            paths = []  # A local article that was never published requires no commit.
        with tempfile.TemporaryDirectory(prefix='growth-editor-index-') as directory:
            environment = {'GIT_INDEX_FILE': str(Path(directory) / 'index')}
            self.git('read-tree', head, env=environment)
            if paths:
                self.git('add', '-A', '--', *paths, env=environment)
            tree = self.git('write-tree', env=environment)
            check()
            if tree == self.git('rev-parse', head + '^{tree}'):
                return {'github_synced': True, 'changed': False, 'commit': head}
            message = ('Sync articles and images' if operation == 'batch' else
                       ('Delete article: ' if operation == 'delete' else 'Update article: ') + relative)
            commit = self.git('commit-tree', tree, '-p', head, input=message + '\n', env=environment)
        pending = {'commit': commit, 'base': head, 'article': relative, 'revision': revision, 'paths': paths, 'operation': operation}
        pending.update(details or {})
        self.state.parent.mkdir(parents=True, exist_ok=True)
        self.state.write_text(json.dumps(pending), encoding='utf-8')
        self.git('update-ref', 'refs/heads/main', commit, head)
        return self.push(pending)

    def push(self, pending):
        # Reconcile only the published paths. All other staged changes remain staged.
        self.git('reset', '--quiet', 'HEAD', '--', *pending['paths'])
        self.git('push', 'origin', pending['commit'] + ':refs/heads/main')
        self.state.unlink()
        return {'github_synced': True, 'changed': True, 'commit': pending['commit']}
