"""Local article editing prototype. Not a production authentication server."""

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
from urllib.parse import parse_qs, unquote, urlsplit
from git_sync import GitSync, SyncError
from auth import AuthError, AuthStore, session_cookie
from hugo_preview import HugoPreview
from recycle_bin import RecycleBin, TrashConflict
from sync_overview import SyncOverview

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTENT_ROOT = PROJECT_ROOT / "content"
STATIC_ROOT = Path(__file__).resolve().parent / "static"
MAX_ARTICLE_BYTES = 2 * 1024 * 1024
MODULES = {"diary": "日记", "english": "英语", "reading": "阅读", "quotes": "金句", "other": "其他"}
WRITE_LOCK = threading.RLock()


class ConflictError(ValueError):
    pass


def split_document(text: str):
    match = re.match(r"\A---\r?\n.*?\r?\n---(?:\r?\n|$)", text, re.S)
    if not match:
        raise ValueError("缺少完整文章头，此阶段不能编辑此文件")
    return text[:match.end()], text[match.end():]


def create_article(root: Path, module: str, title: str, day: str, body: str, identifier: str, quote_fields=None):
    locations = {'diary': 'diary', 'english': 'english/notes', 'reading': 'reading/other',
                 'other': 'other/notes', 'quotes': 'quotes'}
    if not isinstance(module, str) or module not in locations:
        raise ValueError('请选择有效文章分类')
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
        relative = f'quotes/{selected:%Y/%m}/{day}.md'
        url = f'/quotes/{selected:%Y/%m}/{day}/'
    else:
        if not body.strip():
            raise ValueError('请先填写正文再保存')
        slug = day + '-' + identifier[:12]
        directory = f'{locations[module]}/{selected:%Y/%m}/{slug}'
        relative, url = directory + '/index.md', '/' + directory + '/'
    fields['url'] = url
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
                return read_article(root, relative), url
            raise ConflictError('该文章或当天的金句已存在，请打开原文章编辑，未覆盖文件。')
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


def save_article(root: Path, relative: str, title: str, body: str, revision: str, backups: Path):
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
        body = body.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)
        updated = (header + newline + body.lstrip("\r\n").rstrip() + newline).encode("utf-8")
        if original.startswith(b"\xef\xbb\xbf"):
            updated = b"\xef\xbb\xbf" + updated
        backups.mkdir(parents=True, exist_ok=True)
        (backups / (secrets.token_hex(16) + ".md")).write_bytes(original)
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


def upload_image(root: Path, relative: str | None, encoded: str):
    article = article_path(root, relative) if relative is not None else None
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
    return {**summary(relative, text), "content": text, "body": body,
            "revision": hashlib.sha256(raw).hexdigest(), "editable": editable}


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


def make_handler(content_root: Path = CONTENT_ROOT, backup_root: Path | None = None, auth_store: AuthStore | None = None,
                 site_port: int | None = None, site_refresh=None):
    auth = auth_store or AuthStore(content_root.parent / '.tools' / 'editor-auth.json')
    trash = RecycleBin(content_root, WRITE_LOCK)
    backup_root = backup_root or content_root.parent / ".tools" / "editor-backups"
    class Handler(BaseHTTPRequestHandler):
        def allowed_host(self):
            return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

        def respond(self, status: int, content: bytes, mime: str, cookie: str | None = None, site=False):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            if not site:
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; frame-ancestors 'none'; base-uri 'self'")
            self.end_headers()
            self.wfile.write(content)

        def json_response(self, status: int, payload: dict, cookie: str | None = None):
            self.respond(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", cookie)

        def do_GET(self):
            if not self.allowed_host():
                self.json_response(403, {"error": "此后台仅允许本机访问"})
                return
            url = urlsplit(self.path)
            try:
                if url.path == "/api/config":
                    session = auth.session(self.headers.get('Cookie'))
                    self.json_response(200, {"token": session['csrf'] if session else auth.bootstrap_token,
                                             "local_only": True, "authenticated": bool(session),
                                             "configured": auth.configured()})
                elif url.path == "/api/articles":
                    self.json_response(200, {"articles": list_articles(content_root)})
                elif url.path == '/api/trash':
                    if not auth.session(self.headers.get('Cookie')):
                        raise AuthError('请先登录管理员账号。')
                    self.json_response(200, {'items': trash.items()})
                elif url.path == '/api/sync-plan':
                    if not auth.session(self.headers.get('Cookie')):
                        raise AuthError('请先登录管理员账号。')
                    scope = parse_qs(url.query).get('scope', ['content'])[0]
                    self.json_response(200, SyncOverview(content_root.parent).plan(scope))
                elif url.path == "/api/article":
                    relative = parse_qs(url.query).get("path", [""])[0]
                    self.json_response(200, {"article": read_article(content_root, relative)})
                elif url.path in {'/_editor/inline.js', '/_editor/inline.css'}:
                    name = url.path.rsplit('/', 1)[-1]
                    mime = 'text/javascript' if name.endswith('.js') else 'text/css'
                    self.respond(200, (STATIC_ROOT / name).read_bytes(), mime + '; charset=utf-8')
                elif url.path in {"/_prototype/", "/app.js", "/styles.css"} or (url.path == '/' and site_port is None):
                    name = {"/": "index.html", "/_prototype/": "index.html", "/app.js": "app.js", "/styles.css": "styles.css"}[url.path]
                    mime = {"index.html": "text/html", "app.js": "text/javascript", "styles.css": "text/css"}[name]
                    self.respond(200, (STATIC_ROOT / name).read_bytes(), mime + "; charset=utf-8")
                elif url.path.startswith("/vendor/"):
                    name = unquote(url.path[len("/vendor/"):])
                    allowed_files = {"toastui-editor-all.min.js", "toastui-editor.min.css", "zh-cn.js", "LICENSE"}
                    if name not in allowed_files:
                        raise FileNotFoundError()
                    mime = "text/javascript" if name.endswith(".js") else "text/css" if name.endswith(".css") else "text/plain"
                    self.respond(200, (STATIC_ROOT / "vendor" / name).read_bytes(), mime + "; charset=utf-8")
                elif url.path.startswith("/media/content/") or (url.path.startswith("/images/") and site_port is None):
                    if url.path.startswith("/media/content/"):
                        media_root = content_root.resolve()
                        relative = unquote(url.path[len("/media/content/"):])
                    else:
                        media_root = (content_root.parent / "static").resolve()
                        relative = unquote(url.path.lstrip("/"))
                    path = (media_root / relative).resolve()
                    if not path.is_relative_to(media_root) or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                        raise ValueError("图片路径无效")
                    self.respond(200, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")
                elif site_port is not None:
                    # Do not forward owner cookies, auth tokens, or arbitrary upstream addresses.
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
            except AuthError as error:
                self.json_response(error.status, {"error": str(error)})
            except SyncError as error:
                self.json_response(502, {'error': str(error)})
            except (ValueError, UnicodeError) as error:
                self.json_response(400, {"error": str(error)})
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return
            except OSError:
                self.json_response(500, {"error": "无法读取文件，请检查本地权限"})

        def do_POST(self):
            origin = self.headers.get("Origin")
            expected = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
            if not self.allowed_host() or (origin and origin not in expected):
                self.json_response(403, {"error": "请求未授权，请刷新此本地页面后重试"})
                return
            try:
                session = auth.session(self.headers.get('Cookie'))
                csrf = session['csrf'] if session else auth.bootstrap_token
                supplied = self.headers.get('X-Editor-Token', '')
                if supplied and self.path != '/api/login' and not session:
                    raise AuthError('登录已过期，请重新登录。')
                if not secrets.compare_digest(supplied, csrf):
                    raise AuthError('请求未授权，请刷新页面后重试。', 403)
                if self.path != '/api/login' and not session:
                    raise AuthError('请先登录管理员账号。')
                length = int(self.headers.get("Content-Length", "0"))
                maximum = 4096 if self.path in {'/api/login', '/api/logout'} else 12 * 1024 * 1024
                if not 0 < length <= maximum or self.headers.get("Content-Type") != "application/json":
                    raise ValueError("请求大小或格式无效")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("请求格式无效")
                if self.path == '/api/login':
                    identifier, session = auth.login(data.get('password'))
                    self.json_response(200, {'authenticated': True, 'token': session['csrf']}, session_cookie(identifier))
                elif self.path == '/api/logout':
                    auth.logout()
                    self.json_response(200, {'authenticated': False, 'token': auth.bootstrap_token}, session_cookie(clear=True))
                elif self.path == "/api/save":
                    article = save_article(content_root, data["path"], data["title"], data["body"], data["revision"], backup_root)
                    self.json_response(200, {"article": article, "github_synced": False})
                elif self.path == '/api/delete':
                    with WRITE_LOCK:
                        article = read_article(content_root, data['path'])
                        record = trash.delete(data['path'], data['revision'], article['title'], data.get('url', ''))
                    if site_refresh:
                        site_refresh()
                    self.json_response(200, {'item': record, 'github_synced': False})
                elif self.path == '/api/restore':
                    with WRITE_LOCK:
                        pending_file = content_root.parent / '.tools' / 'editor-sync.json'
                        if pending_file.exists():
                            pending = json.loads(pending_file.read_text(encoding='utf-8'))
                            record, _ = trash.record(data['id'])
                            relative = 'content/' + record['path']
                            pending_delete = pending.get('operation') == 'delete' and pending['article'] == relative
                            pending_batch = pending.get('operation') == 'batch' and any(item['path'] == relative and item['action'] == 'D' for item in pending.get('snapshot', []))
                            if pending_delete or pending_batch:
                                raise TrashConflict('这篇文章的删除提交尚未推送完成，请先重试发布删除，再恢复。')
                        record = trash.restore(data['id'])
                    if site_refresh:
                        site_refresh()
                    self.json_response(200, {'item': record})
                elif self.path == '/api/sync-delete':
                    with WRITE_LOCK:
                        record, directory = trash.record(data['id'])
                        if not (directory / 'article.md').is_file():
                            raise ValueError('文章已恢复，不能发布删除')
                        result = GitSync(content_root.parent).sync_deletion(trash.target(record['path']), record['revision'])
                        trash.mark_published(data['id'])
                    self.json_response(200, result)
                elif self.path == '/api/sync-batch':
                    with WRITE_LOCK:
                        result = SyncOverview(content_root.parent).sync_batch(data['scope'], data['revision'])
                        for item in trash.items():
                            if not trash.target(item['path']).exists():
                                relative = 'content/' + item['path']
                                if not GitSync(content_root.parent).git('ls-tree', '--name-only', 'HEAD', '--', relative):
                                    trash.mark_published(item['id'])
                    self.json_response(200, result)
                elif self.path == '/api/create':
                    article, url = create_article(content_root, data['module'], data['title'], data['date'],
                                                  data['body'], data['identifier'], data.get('quote_fields'))
                    if site_refresh:
                        site_refresh()
                    self.json_response(200, {'article': article, 'url': url, 'github_synced': False})
                elif self.path == '/api/upload-new':
                    url = upload_image(content_root, None, data['data'])
                    if site_refresh:
                        site_refresh()
                    self.json_response(200, {'url': url})
                elif self.path == "/api/upload":
                    self.json_response(200, {"url": upload_image(content_root, data["path"], data["data"])})
                elif self.path == "/api/sync":
                    with WRITE_LOCK:
                        path = article_path(content_root, data["path"])
                        result = GitSync(content_root.parent).sync(path, data["revision"])
                    self.json_response(200, result)
                else:
                    self.json_response(404, {"error": "接口不存在"})
            except (ConflictError, TrashConflict) as error:
                self.json_response(409, {"error": str(error)})
            except AuthError as error:
                self.json_response(error.status, {"error": str(error)})
            except SyncError as error:
                self.json_response(502, {"error": str(error), "github_synced": False})
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
    parser.add_argument("--port", type=int, default=1314)
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
    print("仅监听本机。保存修改本地 Markdown；点击同步才会提交并推送 GitHub。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        preview.close()


if __name__ == "__main__":
    main()
