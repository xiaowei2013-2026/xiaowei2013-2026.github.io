"""Run the project's existing Hugo site behind the same-origin editor."""
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


class HugoPreview:
    def __init__(self, root: Path, public_port: int, executable: Path | None = None):
        self.root = root
        self.process = None
        self.log = None
        with socket.socket() as socket_:
            socket_.bind(('127.0.0.1', 0))
            self.port = socket_.getsockname()[1]
        self.url = f'http://127.0.0.1:{self.port}'
        self.public_port = public_port
        self.executable = executable
        self.config = None

    def start(self):
        executable = self.executable or self.root / '.tools' / 'hugo' / ('hugo.exe' if os.name == 'nt' else 'hugo')
        if not executable.is_file():
            raise RuntimeError('找不到项目 Hugo 程序，请先安装或恢复 .tools/hugo。')
        directory = self.root / '.tools'
        directory.mkdir(exist_ok=True)
        config = directory / 'editor-hugo.yaml'
        self.config = config
        config.write_text('params:\n  inlineEditor: true\n', encoding='utf-8')
        self.log = (directory / 'editor-hugo.log').open('w', encoding='utf-8')
        command = [str(executable), 'server', '--source', str(self.root), '--bind', '127.0.0.1',
                   '--port', str(self.port), '--baseURL', f'http://localhost:{self.public_port}/',
                   '--destination', str(directory / 'editor-site'),
                   '--cleanDestinationDir',
                   '--appendPort=false', '--environment', 'production', '--minify',
                   '--disableFastRender', '--disableLiveReload', '--config', 'hugo.yaml,' + str(config)]
        self.process = subprocess.Popen(command, cwd=self.root, stdout=self.log, stderr=self.log,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        for _ in range(100):
            if self.process.poll() is not None:
                self.close()
                raise RuntimeError('Hugo 启动失败，请查看 .tools/editor-hugo.log。')
            try:
                with urllib.request.urlopen(self.url + '/', timeout=1) as response:
                    if response.status == 200:
                        return
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)
        self.close()
        raise RuntimeError('Hugo 启动超时，请查看 .tools/editor-hugo.log。')

    def refresh(self):
        # A new section/static directory can be missed by Hugo's incremental cache.
        # Changing this private overlay requests a full config reload and discovers it.
        if self.config:
            self.config.write_text('params:\n  inlineEditor: true\n# refresh ' + str(time.time_ns()) + '\n', encoding='utf-8')

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log:
            self.log.close()
