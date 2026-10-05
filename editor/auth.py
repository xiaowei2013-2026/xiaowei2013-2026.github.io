"""Single-owner authentication for the loopback-only editor."""
from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
import time
from http.cookies import SimpleCookie
from pathlib import Path

ITERATIONS = 600_000
COOKIE_NAME = 'growth_owner'
SESSION_SECONDS = 8 * 60 * 60
IDLE_SECONDS = 30 * 60


class AuthError(ValueError):
    def __init__(self, message, status=401):
        super().__init__(message)
        self.status = status


def set_password(path: Path, password: str):
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError('密码长度需为 12 至 256 个字符。')
    salt = secrets.token_bytes(32)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)
    record = {'algorithm': 'pbkdf2-sha256', 'iterations': ITERATIONS,
              'salt': salt.hex(), 'digest': digest.hex()}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            json.dump(record, file)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


class AuthStore:
    def __init__(self, path: Path):
        self.path = path
        self.sessions = {}
        self.failures = []
        self.lock = threading.Lock()
        self.fingerprint = None
        self.bootstrap_token = secrets.token_urlsafe(32)

    def record(self):
        try:
            raw = self.path.read_bytes()
            record = json.loads(raw)
            if (record['algorithm'] != 'pbkdf2-sha256' or record['iterations'] != ITERATIONS
                    or len(bytes.fromhex(record['salt'])) != 32 or len(bytes.fromhex(record['digest'])) != 32):
                raise ValueError()
        except FileNotFoundError:
            raw, record = b'', None
        except (OSError, ValueError, KeyError, TypeError):
            raise AuthError('管理员配置无法读取，请重新设置密码。', 503)
        fingerprint = hashlib.sha256(raw).hexdigest()
        if fingerprint != self.fingerprint:
            self.sessions.clear()
            self.fingerprint = fingerprint
        return record

    def session(self, cookie_header):
        with self.lock:
            self.record()
            cookie = SimpleCookie()
            try:
                cookie.load(cookie_header or '')
                identifier = cookie[COOKIE_NAME].value if COOKIE_NAME in cookie else ''
            except Exception:
                return None
            now = time.monotonic()
            self.sessions = {key: value for key, value in self.sessions.items()
                             if now < value['expires'] and now - value['last_seen'] < IDLE_SECONDS}
            session = self.sessions.get(identifier)
            if session:
                session['last_seen'] = now
            return session

    def configured(self):
        with self.lock:
            return self.record() is not None

    def login(self, password):
        with self.lock:
            record = self.record()
            if not record:
                raise AuthError('请先在本机运行 setup-editor.cmd 设置管理员密码。', 503)
            now = time.monotonic()
            self.failures = [when for when in self.failures if now - when < 300]
            if len(self.failures) >= 5:
                raise AuthError('登录失败次数过多，请 5 分钟后再试。', 429)
            if not isinstance(password, str) or len(password) > 256:
                self.failures.append(now)
                raise AuthError('密码不正确。')
            digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(record['salt']), ITERATIONS)
            if not hmac.compare_digest(digest.hex(), record['digest']):
                self.failures.append(now)
                raise AuthError('密码不正确。')
            self.failures.clear()
            self.sessions.clear()  # A new login replaces the previous owner session.
            identifier = secrets.token_urlsafe(32)
            session = {'csrf': secrets.token_urlsafe(32), 'expires': now + SESSION_SECONDS, 'last_seen': now}
            self.sessions[identifier] = session
            return identifier, session

    def logout(self):
        with self.lock:
            self.sessions.clear()


def session_cookie(identifier='', clear=False):
    # HTTP is supported only on loopback. Add Secure when HTTPS deployment is implemented.
    return f'{COOKIE_NAME}={identifier}; HttpOnly; SameSite=Strict; Path=/; Max-Age={0 if clear else SESSION_SECONDS}'


def main():
    path = Path(__file__).resolve().parents[1] / '.tools' / 'editor-auth.json'
    print('设置网站管理员密码（至少 12 个字符，输入时不会显示）。')
    try:
        password = getpass.getpass('新密码: ')
        repeated = getpass.getpass('再次输入: ')
        if password != repeated:
            raise ValueError('两次密码不一致，未修改配置。')
        set_password(path, password)
    except (ValueError, OSError) as error:
        print(str(error))
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\n已取消，未修改配置。')
        return 1
    print('管理员密码已设置。刷新编辑页面，点击“管理员登录”。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
