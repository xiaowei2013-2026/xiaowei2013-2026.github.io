"""Local Markdown editing on the original Hugo site."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import re
import secrets
import tempfile
import threading
import http.client
import unicodedata
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit, quote
from hugo_preview import HugoPreview

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTENT_ROOT = PROJECT_ROOT / "content"
STATIC_ROOT = Path(__file__).resolve().parent / "static"
MAX_ARTICLE_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BYTES = 16 * 1024 * 1024
MODULES = {"diary": "日记", "english": "英语", "reading": "阅读", "quotes": "金句", "other": "其他"}
WRITE_LOCK = threading.RLock()


class ConflictError(ValueError):
    pass


def split_document(text: str):
    match = re.match(r"\A---\r?\n.*?\r?\n---(?:\r?\n|$)", text, re.S)
    if not match:
        raise ValueError("缺少完整文章头，此阶段不能编辑此文件")
    return text[:match.end()], text[match.end():]


def content_directory(root: Path, directory: str) -> Path:
    if not isinstance(directory, str) or '\\' in directory or ':' in directory:
        raise ValueError('文章目录无效')
    candidate = Path(directory)
    if candidate.is_absolute() or any(part in {'.', '..'} or part.startswith('.') for part in candidate.parts):
        raise ValueError('不允许访问内容目录之外的文件夹')
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_dir():
        raise ValueError('当前内容目录不存在或超出项目范围')
    current = resolved
    while current != root.resolve():
        if (current / 'index.md').exists():
            raise ValueError('不能在文章资源目录内新建文章，请进入所属栏目')
        current = current.parent
    return resolved


def create_category(root: Path, directory: str, title: str, slug: str, description: str, identifier: str, backups: Path):
    if not isinstance(title, str) or not title.strip() or len(title) > 100 or '\n' in title or '\r' in title:
        raise ValueError('分类名称不能为空，且不能超过 100 字或包含换行')
    if not isinstance(description, str) or len(description) > 2000:
        raise ValueError('分类说明不能超过 2000 字')
    if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier):
        raise ValueError('新建请求标识无效，请刷新后重试')
    if not isinstance(slug, str):
        raise ValueError('目录名称无效')
    slug = slug.strip() or ('category-' + identifier[:12])
    if (not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', slug) or
            slug.upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM' + str(i) for i in range(1, 10)), *('LPT' + str(i) for i in range(1, 10))}):
        raise ValueError('目录名请使用小写英文字母、数字和短横线，长度不超过 64 字')
    fields = {'title': title.strip(), 'description': description.strip(), 'draft': False,
              'showHero': False, 'editor_id': identifier}
    encoded = ('---\n' + ''.join(key + ': ' + json.dumps(value, ensure_ascii=False) + '\n'
                                 for key, value in fields.items()) + '---\n').encode('utf-8')
    with WRITE_LOCK:
        parent = content_directory(root, directory)
        child = parent / slug
        if child.is_symlink():
            raise ConflictError('同名目录已存在，未覆盖')
        index = child / '_index.md'
        if child.exists() and (not index.is_file() or index.is_symlink() or index.read_bytes() != encoded):
            raise ConflictError('同名分类或目录已存在，请更换目录名，未覆盖文件')
        parent_index = parent / '_index.md'
        original = updated = None
        if parent_index.exists():
            parent_index = article_path(root, parent_index.relative_to(root.resolve()).as_posix())
            original = parent_index.read_bytes()
            text = original.decode('utf-8-sig')
            _, body = split_document(text)
            # Existing section pages may contain hand-written navigation, as /other/ does.
            if not re.search(r'\]\(' + re.escape(slug) + r'/\)', body):
                label = title.strip().replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]')
                label = label.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                newline = '\r\n' if '\r\n' in text else '\n'
                text = text.rstrip() + newline + newline + '- [' + label + '](' + slug + '/)' + newline
                updated = text.encode('utf-8')
                if original.startswith(b'\xef\xbb\xbf'):
                    updated = b'\xef\xbb\xbf' + updated
        if not child.exists():
            child.mkdir()
            try:
                with index.open('xb') as file:
                    file.write(encoded)
            except OSError:
                child.rmdir()
                raise
        if updated is not None:
            backups.mkdir(parents=True, exist_ok=True)
            (backups / (secrets.token_hex(16) + '.md')).write_bytes(original)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=parent, suffix='.tmp', delete=False) as file:
                    temporary = Path(file.name)
                    file.write(updated)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, parent_index)
            finally:
                if temporary and temporary.exists():
                    temporary.unlink()
        relative = child.relative_to(root.resolve()).as_posix()
        return {'directory': relative, 'title': title.strip(), 'url': '/' + relative + '/'}


def parent_snapshot(root: Path, directory: Path):
    index = directory / '_index.md'
    relative = directory.relative_to(root.resolve()).as_posix()
    return {'parent_directory': '' if relative == '.' else relative,
            'parent_revision': hashlib.sha256(index.read_bytes()).hexdigest() if index.is_file() else None}


def delete_category(root: Path, directory: str, revision: str, backups: Path):
    with WRITE_LOCK:
        target = content_directory(root, directory)
        if target == root.resolve():
            raise ValueError('首页不能删除')
        index = target / '_index.md'
        if index.is_symlink():
            raise ValueError('不能删除链接目录或链接文件')
        original = article_path(root, index.relative_to(root.resolve()).as_posix()).read_bytes()
        if hashlib.sha256(original).hexdigest() != revision:
            raise ConflictError('分类已在其他地方修改，请刷新页面后重试')
        header, _ = split_document(original.decode('utf-8-sig'))
        if not re.search(r'^editor_id:\s*"[a-f0-9]{32}"\s*$', header, re.M):
            raise ValueError('只能删除在网页中新建的分类，原有栏目不允许删除')
        entries = list(target.rglob('*'))
        if any(path.is_symlink() or (path != index and not path.is_dir()) for path in entries):
            raise ConflictError('分类中还有文章、子分类或附件，请先处理内容，再删除空分类')
        parent = target.parent
        parent_index = parent / '_index.md'
        parent_original = parent_updated = None
        if parent_index.exists():
            parent_index = article_path(root, parent_index.relative_to(root.resolve()).as_posix())
            parent_original = parent_index.read_bytes()
            text = parent_original.decode('utf-8-sig')
            parent_header, parent_body = split_document(text)
            cleaned = re.sub(r'^[ \t]*-[ \t]+\[[^\r\n]*\]\(' + re.escape(target.name) + r'/\)[ \t]*(?:\r?\n|$)',
                             '', parent_body, flags=re.M)
            if cleaned != parent_body:
                newline = '\r\n' if '\r\n' in text else '\n'
                parent_updated = ((parent_header + cleaned).rstrip('\r\n') + newline).encode('utf-8')
                if parent_original.startswith(b'\xef\xbb\xbf'):
                    parent_updated = b'\xef\xbb\xbf' + parent_updated
        backups.mkdir(parents=True, exist_ok=True)
        (backups / (secrets.token_hex(16) + '.md')).write_bytes(original)
        temporary = None
        try:
            if parent_updated is not None:
                (backups / (secrets.token_hex(16) + '.md')).write_bytes(parent_original)
                with tempfile.NamedTemporaryFile(dir=parent, suffix='.tmp', delete=False) as file:
                    temporary = Path(file.name)
                    file.write(parent_updated)
                    file.flush()
                    os.fsync(file.fileno())
            # Only the verified category index and empty directories are removed.
            # Files added by another editor are never recursively deleted.
            index.unlink()
            try:
                for path in sorted((path for path in entries if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
                    path.rmdir()
                target.rmdir()
                if temporary:
                    os.replace(temporary, parent_index)
            except OSError:
                target.mkdir(exist_ok=True)
                if not index.exists():
                    index.write_bytes(original)
                raise
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
        return {'deleted': True, 'directory': directory, **parent_snapshot(root, parent)}


def create_article(root: Path, directory: str, title: str, day: str, body: str, identifier: str, quote_fields=None, reading_fields=None, cover=None):
    target = content_directory(root, directory)
    directory = target.relative_to(root.resolve()).as_posix()
    if directory == '.':
        directory = ''
    module = directory.split('/')[0]
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError('标题不能为空，且不能超过 200 字')
    if not isinstance(day, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
        raise ValueError('日期必须是 YYYY-MM-DD')
    selected = date.fromisoformat(day)
    if selected > datetime.now(timezone(timedelta(hours=8))).date():
        raise ValueError('日期不能晚于今天，否则公开网站不会显示这篇文章')
    if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier):
        raise ValueError('新建请求标识无效，请刷新页面后重试')
    if not isinstance(body, str) or len(body.encode('utf-8')) > MAX_ARTICLE_BYTES:
        raise ValueError('正文无效或超过 2 MB')
    if '{{<' in body or '{{%' in body:
        raise ValueError('新建文章暂不支持 Hugo 图表组件')
    fields = {'title': title.strip(), 'date': day, 'draft': False, 'editor_id': identifier}
    if directory == 'reading/books' or directory.startswith('reading/books/'):
        metadata = reading_fields or {}
        if not isinstance(metadata, dict):
            raise ValueError('阅读信息无效')
        author = metadata.get('author', '')
        status = metadata.get('status', '在读')
        if not isinstance(author, str) or len(author) > 200 or status not in {'未读', '在读', '已读'}:
            raise ValueError('书籍信息无效')
        fields.update(entry_type='book', book_id='book-' + identifier, author=author.strip(), status=status)
    elif directory == 'reading/logs' or directory.startswith('reading/logs/'):
        metadata = reading_fields or {}
        if not isinstance(metadata, dict):
            raise ValueError('阅读信息无效')
        book_id = metadata.get('book_id', '')
        books = [path for path in (root / 'reading' / 'books').rglob('*.md') if path.name != '_index.md']
        if not isinstance(book_id, str) or not book_id or not any(
                re.search(r'^book_id:\s*[\"\']?' + re.escape(book_id) + r'[\"\']?\s*$',
                          path.read_text(encoding='utf-8-sig'), re.M) for path in books):
            raise ValueError('请输入已存在书籍的 book_id')
        try:
            minutes = int(metadata.get('reading_minutes', ''))
            pages = int(metadata.get('pages', '0'))
        except (ValueError, TypeError):
            raise ValueError('阅读分钟数和页数必须是非负整数')
        if minutes < 0 or pages < 0:
            raise ValueError('阅读分钟数和页数必须是非负整数')
        fields.update(entry_type='reading-log', book_id=book_id, reading_minutes=minutes, pages=pages)
    if module == 'quotes':
        if not isinstance(quote_fields, dict):
            raise ValueError('请填写金句原文')
        for key in ('quote', 'author', 'work', 'kind'):
            value = quote_fields.get(key, '')
            if not isinstance(value, str) or len(value) > 2000:
                raise ValueError('金句信息无效或过长')
            fields[key] = value.strip()
        quote_key = ''.join(char for char in unicodedata.normalize('NFKC', fields['quote']).casefold() if char.isalnum())
        if not quote_key:
            raise ValueError('请填写金句原文，不能只有标点或空格')
        attribution = ' · '.join(fields[key] for key in ('author', 'work') if fields[key])
        body = '\n'.join('> ' + line for line in fields['quote'].splitlines()) + '\n\n' + ('——' + attribution + '\n\n' if attribution else '') + body.strip()
        relative = f'{directory}/{day}.md'
        url = f'/{directory}/{day}/'
    else:
        if not body.strip():
            raise ValueError('请先填写正文再保存')
        slug = day + '-' + identifier[:12]
        bundle = '/'.join(part for part in (directory, slug) if part)
        relative, url = bundle + '/index.md', '/' + bundle + '/'
    fields['url'] = url
    cover_file = prepare_cover(root, root / relative, cover)
    if cover_file:
        fields.update(featureimage=cover_file[0], showHero=False, hideFeatureImage=False)
    encoded = ('---\n' + ''.join(key + ': ' + json.dumps(value, ensure_ascii=False) + '\n'
                                 for key, value in fields.items()) + '---\n\n' + body.strip() + '\n').encode('utf-8')
    if len(encoded) > MAX_ARTICLE_BYTES:
        raise ValueError('文章超过 2 MB')
    with WRITE_LOCK:
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError('文章路径无效')
        if path.exists():
            if path.read_bytes() == encoded:
                if cover_file:
                    write_cover(cover_file)
                return read_article(root, relative), url
            raise ConflictError('该文章或当天的金句已存在，请打开原文章编辑，未覆盖文件。')
        if fields.get('entry_type') == 'reading-log':
            for existing in (root / 'reading' / 'logs').rglob('*.md'):
                text = existing.read_text(encoding='utf-8-sig')
                if (re.search(r'^book_id:\s*[\"\']?' + re.escape(book_id) + r'[\"\']?\s*$', text, re.M) and
                        re.search(r'^date:\s*[\"\']?' + re.escape(day) + r'[\"\']?\s*$', text, re.M)):
                    raise ConflictError('这本书当天的阅读记录已经存在')
        if module == 'quotes':
            for existing in (root / 'quotes').rglob('*.md'):
                if existing.name == '_index.md':
                    continue
                text = existing.read_text(encoding='utf-8-sig')
                values = {}
                header, _ = split_document(text)
                for key in ('date', 'quote'):
                    match = re.search(r'^' + key + r':\s*([^\r\n]*)', header, re.M)
                    if match:
                        raw = match.group(1).strip()
                        values[key] = json.loads(raw) if raw.startswith('"') else raw.strip("'")
                key = ''.join(char for char in unicodedata.normalize('NFKC', values.get('quote', '')).casefold() if char.isalnum())
                if values.get('date') == day or key == quote_key:
                    raise ConflictError('金句原文或日期已存在，请打开原文章编辑。')
        path.parent.mkdir(parents=True, exist_ok=True)
        if cover_file:
            write_cover(cover_file)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as file:
                temporary = Path(file.name)
                file.write(encoded)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
        return read_article(root, relative), url


def delete_article(root: Path, relative: str, revision: str):
    with WRITE_LOCK:
        path = article_path(root, relative)
        if path.name == '_index.md':
            raise ValueError('栏目目录页不能删除')
        if hashlib.sha256(path.read_bytes()).hexdigest() != revision:
            raise ConflictError('文章已在其他地方修改，请重新打开后再删除')
        path.unlink()
        parent = path.parent.parent if path.name == 'index.md' else path.parent
        return {'deleted': True, **parent_snapshot(root, parent)}


def save_article(root: Path, relative: str, title: str, body: str, revision: str, backups: Path, cover=None):
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError("标题不能为空，且不能超过 200 字")
    if not isinstance(body, str) or len(body.encode("utf-8")) > MAX_ARTICLE_BYTES:
        raise ValueError("正文无效或超过 2 MB")
    with WRITE_LOCK:
        path = article_path(root, relative)
        original = path.read_bytes()
        if hashlib.sha256(original).hexdigest() != revision:
            raise ConflictError("文件已在其他地方修改。请保留当前内容，重新读取后合并，未覆盖文件。")
        header, old_body = split_document(original.decode("utf-8-sig"))
        if "{{<" in old_body or "{{%" in old_body or "{{<" in body or "{{%" in body:
            raise ValueError("含 Hugo 图表组件的页面暂不支持可视化保存")
        newline = "\r\n" if "\r\n" in header else "\n"
        title_line = "title: " + json.dumps(title.strip(), ensure_ascii=False)
        if re.search(r"^title:", header, re.M):
            header = re.sub(r"^title:[^\r\n]*", lambda _: title_line, header, count=1, flags=re.M)
        else:
            header = header.replace(newline, newline + title_line + newline, 1)
        cover_file = prepare_cover(root, path, cover)
        if cover_file:
            for key, value in {'featureimage': cover_file[0], 'showHero': False, 'hideFeatureImage': False}.items():
                line = key + ': ' + json.dumps(value, ensure_ascii=False)
                if re.search(r'^' + key + r':', header, re.M | re.I):
                    header = re.sub(r'^' + key + r':[^\r\n]*', lambda _: line, header, count=1, flags=re.M | re.I)
                else:
                    header = header.replace(newline, newline + line + newline, 1)
        body = body.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)
        updated = (header + newline + body.lstrip("\r\n").rstrip() + newline).encode("utf-8")
        if original.startswith(b"\xef\xbb\xbf"):
            updated = b"\xef\xbb\xbf" + updated
        backups.mkdir(parents=True, exist_ok=True)
        (backups / (secrets.token_hex(16) + ".md")).write_bytes(original)
        if cover_file:
            write_cover(cover_file)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as temporary:
                temp_path = Path(temporary.name)
                temporary.write(updated)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()
        return read_article(root, relative)


def decode_image(encoded: str):
    if not isinstance(encoded, str):
        raise ValueError('图片数据无效')
    if len(encoded) > 12 * 1024 * 1024:
        raise ValueError("图片不能超过 8 MB")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise ValueError("图片数据无效")
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("图片不能超过 8 MB")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = ".png"
    elif data.startswith(b"\xff\xd8\xff"):
        extension = ".jpg"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        extension = ".webp"
    else:
        raise ValueError("仅支持 PNG、JPEG 或 WebP 图片")
    return data, extension


def prepare_cover(root: Path, article: Path, cover):
    if cover is None:
        return None
    if not isinstance(cover, dict):
        raise ValueError('封面图片数据无效')
    data, extension = decode_image(cover.get('data'))
    name = 'feature-editor-' + hashlib.sha256(data).hexdigest()[:32] + extension
    if article.name == 'index.md':
        directory = article.parent.resolve()
        if not directory.is_relative_to(root.resolve()):
            raise ValueError('封面目录超出内容范围')
        reference = name
    else:
        directory = (root.parent / 'assets' / 'editor-covers').resolve()
        if not directory.is_relative_to(root.parent.resolve()):
            raise ValueError('封面目录超出项目范围')
        reference = 'editor-covers/' + name
    path = directory / name
    if path.is_symlink() or (path.exists() and path.read_bytes() != data):
        raise ConflictError('封面文件路径已被占用，未覆盖原文件')
    return reference, path, data


def write_cover(prepared):
    _, path, data = prepared
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data:
            raise ConflictError('封面文件已在其他地方修改，未覆盖文件')
        return
    with path.open('xb') as file:
        file.write(data)


def upload_image(root: Path, relative: str | None, encoded: str):
    article = article_path(root, relative) if relative is not None else None
    data, extension = decode_image(encoded)
    # Flat Markdown files aren't Hugo leaf bundles: their uploads belong in static.
    if article is not None and article.name == "index.md":
        directory = article.parent / "editor-images"
        directory = directory.resolve()
        if not directory.is_relative_to(root.resolve()):
            raise ValueError("图片路径无效")
        prefix = "editor-images/"
    else:
        directory = root.parent / "static" / "images" / "editor"
        directory = directory.resolve()
        if not directory.is_relative_to((root.parent / "static").resolve()):
            raise ValueError("图片路径无效")
        if not directory.is_relative_to(root.parent.resolve()):
            raise ValueError("图片不能写入项目之外")
        prefix = "/images/editor/"
    directory.mkdir(parents=True, exist_ok=True)
    name = secrets.token_hex(16) + extension
    (directory / name).write_bytes(data)
    return prefix + name


def article_path(root: Path, relative: str) -> Path:
    if not relative or "\\" in relative:
        raise ValueError("请选择 content 目录中的 Markdown 文件")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("不允许访问 content 目录之外的文件")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if not resolved.is_relative_to(resolved_root) or resolved.suffix.lower() != ".md":
        raise ValueError("不允许访问 content 目录之外的 Markdown 文件")
    if not resolved.is_file():
        raise FileNotFoundError("文章不存在")
    if resolved.stat().st_size > MAX_ARTICLE_BYTES:
        raise ValueError("文章超过 2 MB，暂不支持在线读取")
    return resolved


def summary(relative: str, text: str) -> dict:
    """Read top-level display fields without interpreting or rewriting YAML."""
    fields = {}
    lines = text.lstrip("\ufeff").splitlines()
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            match = re.match(r"^(title|date|description):\s*(.*?)\s*$", line)
            if not match:
                continue
            key, value = match.groups()
            if value.startswith('"'):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1].replace("''", "'")
            fields[key] = str(value)
    return {
        "path": relative,
        "title": fields.get("title") or Path(relative).stem,
        "date": fields.get("date", ""),
        "description": fields.get("description", ""),
        "module": MODULES.get(relative.split("/")[0], "站点"),
        "kind": "目录页" if Path(relative).name == "_index.md" else "文章",
    }


def read_article(root: Path, relative: str) -> dict:
    path = article_path(root, relative)
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    try:
        _, body = split_document(text)
        editable = "{{<" not in body and "{{%" not in body
    except ValueError:
        body, editable = text, False
    cover_url = ''
    match = re.search(r'^featureimage:\s*([^\r\n]*)', text, re.M | re.I)
    reference = ''
    if match:
        value = match.group(1).strip()
        try:
            reference = json.loads(value) if value.startswith('"') else value.strip("'")
        except ValueError:
            reference = ''
    if isinstance(reference, str) and reference and not urlsplit(reference).scheme and not Path(reference).is_absolute():
        candidate = (path.parent / reference).resolve()
        asset = (root.parent / 'assets' / reference).resolve()
        if candidate.is_relative_to(root.resolve()) and candidate.is_file():
            cover_url = '/media/content/' + quote(candidate.relative_to(root.resolve()).as_posix())
        elif asset.is_relative_to((root.parent / 'assets').resolve()) and asset.is_file():
            cover_url = '/media/assets/' + quote(asset.relative_to((root.parent / 'assets').resolve()).as_posix())
    if not cover_url and path.name == 'index.md':
        images = sorted(item for item in path.parent.iterdir() if item.is_file() and item.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'})
        for pattern in ('feature', 'cover', 'thumbnail'):
            selected = next((item for item in images if pattern in item.name.lower() and item.resolve().is_relative_to(root.resolve())), None)
            if selected:
                cover_url = '/media/content/' + quote(selected.relative_to(root).as_posix())
                break
    return {**summary(relative, text), "content": text, "body": body,
            "revision": hashlib.sha256(raw).hexdigest(), "editable": editable, "cover_url": cover_url}


def list_articles(root: Path) -> list[dict]:
    articles = []
    for path in root.rglob("*.md"):
        relative = path.relative_to(root).as_posix()
        try:
            article = read_article(root, relative)
        except (OSError, ValueError, UnicodeError):
            continue
        articles.append({key: value for key, value in article.items() if key not in {"content", "body", "revision"}})
    return sorted(articles, key=lambda item: (item["date"], item["path"]), reverse=True)


def make_handler(content_root: Path = CONTENT_ROOT, backup_root: Path | None = None,
                 site_port: int | None = None, site_refresh=None):
    request_token = secrets.token_hex(32)
    backup_root = backup_root or content_root.parent / ".tools" / "editor-backups"
    class Handler(BaseHTTPRequestHandler):
        def allowed_host(self):
            return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

        def respond(self, status: int, content: bytes, mime: str, site=False):
            # Drain bounded rejected requests before closing, so Windows delivers the
            # JSON error instead of resetting a socket with unread request bytes.
            if self.command in {'POST', 'PUT', 'PATCH', 'DELETE'} and not getattr(self, '_body_read', False):
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                except ValueError:
                    length = 0
                if 0 < length <= MAX_REQUEST_BYTES:
                    timeout = self.connection.gettimeout()
                    try:
                        self.connection.settimeout(2)
                        self.rfile.read(length)
                    except OSError:
                        pass
                    finally:
                        self.connection.settimeout(timeout)
                self._body_read = True
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            if not site:
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; frame-ancestors 'none'; base-uri 'self'")
            self.end_headers()
            self.wfile.write(content)

        def json_response(self, status: int, payload: dict):
            self.respond(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            if not self.allowed_host():
                self.json_response(403, {"error": "此后台仅允许本机访问"})
                return
            url = urlsplit(self.path)
            try:
                if url.path == "/api/config":
                    self.json_response(200, {"token": request_token, "local_only": True})
                elif url.path == "/api/articles":
                    self.json_response(200, {"articles": list_articles(content_root)})
                elif url.path == "/api/article":
                    relative = parse_qs(url.query).get("path", [""])[0]
                    self.json_response(200, {"article": read_article(content_root, relative)})
                elif url.path in {'/_editor/inline.js', '/_editor/inline.css'}:
                    name = url.path.rsplit('/', 1)[-1]
                    mime = 'text/javascript' if name.endswith('.js') else 'text/css'
                    self.respond(200, (STATIC_ROOT / name).read_bytes(), mime + '; charset=utf-8')
                elif url.path.startswith("/vendor/"):
                    name = unquote(url.path[len("/vendor/"):])
                    allowed_files = {"toastui-editor-all.min.js", "toastui-editor.min.css", "zh-cn.js", "LICENSE"}
                    if name not in allowed_files:
                        raise FileNotFoundError()
                    mime = "text/javascript" if name.endswith(".js") else "text/css" if name.endswith(".css") else "text/plain"
                    self.respond(200, (STATIC_ROOT / "vendor" / name).read_bytes(), mime + "; charset=utf-8")
                elif url.path.startswith("/media/content/") or url.path.startswith('/media/assets/') or (url.path.startswith("/images/") and site_port is None):
                    if url.path.startswith("/media/content/"):
                        media_root = content_root.resolve()
                        relative = unquote(url.path[len("/media/content/"):])
                    elif url.path.startswith('/media/assets/'):
                        media_root = (content_root.parent / 'assets').resolve()
                        relative = unquote(url.path[len('/media/assets/'):])
                    else:
                        media_root = (content_root.parent / "static").resolve()
                        relative = unquote(url.path.lstrip("/"))
                    path = (media_root / relative).resolve()
                    if not path.is_relative_to(media_root) or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                        raise ValueError("图片路径无效")
                    self.respond(200, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")
                elif url.path.startswith("/api/"):
                    self.json_response(404, {"error": "接口不存在"})
                elif site_port is not None:
                    # Keep browser cookies and editor request tokens out of the Hugo proxy.
                    connection = http.client.HTTPConnection('127.0.0.1', site_port, timeout=15)
                    try:
                        connection.request('GET', self.path, headers={'Host': f'localhost:{self.server.server_port}'})
                        response = connection.getresponse()
                        content = response.read()
                        if response.status in {301, 302, 307, 308}:
                            location = response.getheader('Location', '/')
                            if urlsplit(location).netloc:
                                location = urlsplit(location).path or '/'
                            self.send_response(response.status)
                            self.send_header('Location', location)
                            self.send_header('Content-Length', '0')
                            self.end_headers()
                        else:
                            self.respond(response.status, content, response.getheader('Content-Type', 'application/octet-stream'), site=True)
                    finally:
                        connection.close()
                else:
                    self.json_response(404, {"error": "页面不存在"})
            except FileNotFoundError:
                self.json_response(404, {"error": "文章不存在"})
            except (ValueError, UnicodeError) as error:
                self.json_response(400, {"error": str(error)})
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return
            except OSError:
                self.json_response(500, {"error": "无法读取文件，请检查本地权限"})

        def do_POST(self):
            origin = self.headers.get("Origin")
            expected = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
            if not self.allowed_host() or (origin and origin not in expected) or self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.json_response(403, {"error": "请求未授权，请刷新此本地页面后重试"})
                return
            try:
                supplied = self.headers.get('X-Editor-Token', '')
                if not secrets.compare_digest(supplied, request_token):
                    self.json_response(403, {"error": "请求未授权，请刷新此本地页面后重试"})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                maximum = MAX_REQUEST_BYTES
                if not 0 < length <= maximum or self.headers.get("Content-Type") != "application/json":
                    raise ValueError("请求大小或格式无效")
                raw = self.rfile.read(length)
                self._body_read = True
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError("请求格式无效")
                if self.path == "/api/save":
                    article = save_article(content_root, data["path"], data["title"], data["body"], data["revision"], backup_root, data.get('cover'))
                    if data.get('cover') and site_refresh:
                        site_refresh()
                    self.json_response(200, {"article": article, "local_only": True})
                elif self.path == '/api/delete':
                    result = delete_article(content_root, data['path'], data['revision'])
                    if site_refresh:
                        site_refresh()
                    self.json_response(200, result)
                elif self.path == '/api/create':
                    article, url = create_article(content_root, data['directory'], data['title'], data['date'],
                                                  data['body'], data['identifier'], data.get('quote_fields'), data.get('reading_fields'), data.get('cover'))
                    if site_refresh:
                        site_refresh()
                    self.json_response(200, {'article': article, 'url': url, 'local_only': True})
                elif self.path == '/api/create-category':
                    category = create_category(content_root, data['directory'], data['title'], data.get('slug', ''),
                                               data.get('description', ''), data['identifier'], backup_root)
                    if site_refresh:
                        site_refresh()
                    self.json_response(200, {'category': category, 'local_only': True})
                elif self.path == '/api/delete-category':
                    result = delete_category(content_root, data['directory'], data['revision'], backup_root)
                    if site_refresh:
                        site_refresh()
                    self.json_response(200, result)
                elif self.path == '/api/upload-new':
                    url = upload_image(content_root, None, data['data'])
                    if site_refresh:
                        site_refresh()
                    self.json_response(200, {'url': url})
                elif self.path == "/api/upload":
                    self.json_response(200, {"url": upload_image(content_root, data["path"], data["data"])})
                else:
                    self.json_response(404, {"error": "接口不存在"})
            except ConflictError as error:
                self.json_response(409, {"error": str(error)})
            except FileNotFoundError:
                self.json_response(404, {"error": "文章不存在"})
            except (ValueError, KeyError, TypeError, UnicodeError) as error:
                self.json_response(400, {"error": str(error)})
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return
            except OSError:
                self.json_response(500, {"error": "保存失败，请检查目录权限"})

        def reject_write(self):
            self.json_response(405, {"error": "此操作未开放"})

        do_PUT = reject_write
        do_PATCH = reject_write
        do_DELETE = reject_write

    return Handler


def main():
    parser = argparse.ArgumentParser(description="本地文章可视化编辑")
    parser.add_argument("--port", type=int, default=1313)
    args = parser.parse_args()
    preview = HugoPreview(PROJECT_ROOT, args.port)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(site_port=preview.port, site_refresh=preview.refresh))
    except OSError:
        parser.exit(1, f"无法启动：端口 {args.port} 被占用或不可用，请结束旧后台，或用 --port 指定其他端口。\n")
    try:
        preview.start()
    except (OSError, RuntimeError) as error:
        server.server_close()
        preview.close()
        parser.exit(1, str(error) + '\n')
    print(f"原网站与直接编辑：http://localhost:{server.server_port}/", flush=True)
    print("仅监听本机。网页只修改本地 Markdown；写作完成后在终端统一 commit、push。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        preview.close()


if __name__ == "__main__":
    main()
