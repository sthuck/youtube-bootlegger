"""HTTPS still works when a packaged Python has no default CA installation."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import shutil
import ssl
import subprocess
import threading
from urllib.error import URLError

import certifi
import pytest

from src.youtube_bootlegger.core.tool_installer import urlopen_get


@pytest.fixture
def https_server(tmp_path):
    openssl = shutil.which('openssl')
    if not openssl:
        pytest.skip('openssl is needed to create the local HTTPS test certificate')
    certificate, key = tmp_path / 'server.pem', tmp_path / 'server.key'
    subprocess.run([
        openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
        '-keyout', str(key), '-out', str(certificate), '-subj', '/CN=localhost',
        '-addext', 'subjectAltName=DNS:localhost',
        '-addext', 'basicConstraints=critical,CA:TRUE',
    ], check=True, capture_output=True)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'verified download')

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield certificate, server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_download_uses_bundled_roots_without_system_ca_files(https_server, monkeypatch, tmp_path):
    certificate, port = https_server
    monkeypatch.setenv('SSL_CERT_FILE', str(tmp_path / 'missing-system-roots.pem'))
    monkeypatch.setenv('SSL_CERT_DIR', str(tmp_path))
    monkeypatch.setenv('NO_PROXY', 'localhost,127.0.0.1')
    monkeypatch.setattr(certifi, 'where', lambda: str(certificate))
    with urlopen_get(f'https://localhost:{port}/tool') as response:
        assert response.read() == b'verified download'


def test_download_rejects_untrusted_certificate(https_server, monkeypatch):
    _, port = https_server
    monkeypatch.setenv('NO_PROXY', 'localhost,127.0.0.1')
    with pytest.raises(URLError) as error:
        urlopen_get(f'https://localhost:{port}/tool')
    assert isinstance(error.value.reason, ssl.SSLCertVerificationError)


def test_download_rejects_wrong_hostname(https_server, monkeypatch):
    certificate, port = https_server
    monkeypatch.setenv('NO_PROXY', 'localhost,127.0.0.1')
    monkeypatch.setattr(certifi, 'where', lambda: str(certificate))
    with pytest.raises(URLError) as error:
        urlopen_get(f'https://127.0.0.1:{port}/tool')
    assert isinstance(error.value.reason, ssl.SSLCertVerificationError)
    assert 'mismatch' in str(error.value.reason)
