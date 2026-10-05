"""Reversible removal of Markdown articles; attached/shared images stay in place."""
import hashlib
import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path


class TrashConflict(ValueError):
    pass


class RecycleBin:
    def __init__(self, content: Path, lock=None):
        self.content = content.resolve()
        self.root = self.content.parent / '.tools' / 'editor-trash'
        self.lock = lock or threading.RLock()
        if not self.root.resolve().is_relative_to(self.content.parent):
            raise ValueError('回收站路径无效')

    def target(self, relative):
        if not isinstance(relative, str) or not relative or '\\' in relative:
            raise ValueError('文章路径无效')
        candidate = Path(relative)
        target = (self.content / candidate).resolve()
        if (candidate.is_absolute() or '..' in candidate.parts or not target.is_relative_to(self.content)
                or target.suffix != '.md' or target.name == '_index.md'):
            raise ValueError('只能删除文章，不能删除目录页或项目外文件')
        return target

    def record(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier):
            raise ValueError('回收站编号无效')
        directory = (self.root / identifier).resolve()
        if not directory.is_relative_to(self.root.resolve()):
            raise ValueError('回收站路径无效')
        record = json.loads((directory / 'record.json').read_text(encoding='utf-8'))
        if record.get('id') != identifier:
            raise ValueError('回收站记录无效')
        if (directory / 'article.md').is_symlink():
            raise ValueError('回收站文件不能是链接')
        self.target(record['path'])
        return record, directory

    @staticmethod
    def write_record(directory, record):
        temporary = directory / 'record.tmp'
        temporary.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
        os.replace(temporary, directory / 'record.json')

    def delete(self, relative, revision, title, url=''):
        with self.lock:
            if not isinstance(url, str) or (url and (not url.startswith('/') or url.startswith('//') or '\\' in url)):
                raise ValueError('文章网址无效')
            target = self.target(relative)
            raw = target.read_bytes()
            if hashlib.sha256(raw).hexdigest() != revision:
                raise TrashConflict('文章已在其他地方修改，请刷新检查后再删除，未删除文件。')
            identifier = secrets.token_hex(16)
            directory = self.root / identifier
            directory.mkdir(parents=True)
            record = {'id': identifier, 'path': relative, 'title': title, 'revision': revision,
                      'deleted_at': datetime.now(timezone.utc).isoformat(), 'github_deleted': False, 'url': url}
            self.write_record(directory, record)
            os.replace(target, directory / 'article.md')
            return record

    def items(self):
        with self.lock:
            items = []
            for directory in self.root.glob('*'):
                try:
                    record, directory = self.record(directory.name)
                    if (directory / 'article.md').is_file():
                        items.append(record)
                except (OSError, ValueError, KeyError):
                    continue
            return sorted(items, key=lambda item: item['deleted_at'], reverse=True)

    def restore(self, identifier):
        with self.lock:
            record, directory = self.record(identifier)
            target = self.target(record['path'])
            if target.exists():
                raise TrashConflict('原位置已有文章，恢复会覆盖它，因此未恢复。请先处理同名文件。')
            payload = directory / 'article.md'
            if hashlib.sha256(payload.read_bytes()).hexdigest() != record['revision']:
                raise TrashConflict('回收站中的文章内容发生变化，未恢复。')
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(payload, target)
            return record

    def mark_published(self, identifier):
        with self.lock:
            record, directory = self.record(identifier)
            record['github_deleted'] = True
            self.write_record(directory, record)
