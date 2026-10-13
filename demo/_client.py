"""
A tiny HTTP client for the demo scripts (standard library only, so it runs on any Python 3.9+).

In plain words: the demo scripts talk to the running OpenID Vision server exactly like the web interface does -
upload a picture, read the JSON answer. Nothing here is special-cased for the demo.
"""

from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status, self.message = status, message


class Api:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", api_key: str | None = None, timeout: float = 300):
        self.base, self.timeout = base_url.rstrip("/"), timeout
        self.headers = {"X-API-Key": api_key} if api_key else {}

    # ------------------------------------------------------------------ plumbing
    def _send(self, request: urllib.request.Request, raw: bool = False):
        for key, value in self.headers.items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            body = error.read()
            try:
                message = json.loads(body)["error"]["message"]
            except Exception:
                message = body[:200].decode("utf-8", "replace")
            raise ApiError(error.code, message) from None
        except urllib.error.URLError as error:
            raise ApiError(0, f"cannot reach {self.base}: {error.reason}") from None
        if raw:
            return body
        return json.loads(body) if body else None

    def get(self, path: str, query: dict | None = None, raw: bool = False):
        url = self.base + path + ("?" + urllib.parse.urlencode(query) if query else "")
        return self._send(urllib.request.Request(url), raw=raw)

    def delete(self, path: str, query: dict | None = None):
        url = self.base + path + ("?" + urllib.parse.urlencode(query) if query else "")
        return self._send(urllib.request.Request(url, method="DELETE"))

    def post_json(self, path: str, body: dict):
        request = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
        return self._send(request)

    def post_form(self, path: str, fields: dict[str, str], files: list[tuple[str, Path]]):
        """multipart/form-data: ``files`` is a list of (field name, path)."""
        boundary = uuid.uuid4().hex
        parts: list[bytes] = []
        for name, value in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        for name, file_path in files:
            kind = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{file_path.name}"\r\n'
                         f"Content-Type: {kind}\r\n\r\n".encode() + file_path.read_bytes() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        request = urllib.request.Request(self.base + path, data=b"".join(parts), method="POST",
                                         headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        return self._send(request)
