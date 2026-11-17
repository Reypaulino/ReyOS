"""Tiny Chrome DevTools Protocol client (stdlib only) for Reyva's tests:
QTWEBENGINE_REMOTE_DEBUGGING exposes each tab as a DevTools target."""
import base64
import json
import os
import socket
import struct
import urllib.request
from urllib.parse import urlsplit


def targets(port: int) -> list[dict]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as response:
            return [t for t in json.loads(response.read()) if t.get("type") == "page"]
    except Exception:
        return []


class Session:
    def __init__(self, ws_url: str, timeout: float = 30.0) -> None:
        parts = urlsplit(ws_url)
        self.sock = socket.create_connection((parts.hostname, parts.port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {parts.path} HTTP/1.1\r\nHost: {parts.hostname}:{parts.port}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("DevTools closed the connection")
            response += chunk
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise ConnectionError(response[:200])
        self.buffer = response.split(b"\r\n\r\n", 1)[1]
        self.next_id = 0

    def _send(self, text: str) -> None:
        data = text.encode()
        header = bytearray([0x81])
        mask = os.urandom(4)
        if len(data) < 126:
            header.append(0x80 | len(data))
        elif len(data) < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", len(data))
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", len(data))
        self.sock.sendall(bytes(header) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n: int) -> bytes:
        while len(self.buffer) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("DevTools closed the connection")
            self.buffer += chunk
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    def _recv(self) -> dict:
        message = b""
        while True:
            first, second = self._read(2)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(length)
            opcode = first & 0x0F
            if opcode == 8:
                raise ConnectionError("DevTools closed the connection")
            if opcode in (0, 1):
                message += payload
                if first & 0x80:
                    return json.loads(message)

    def call(self, method: str, **params) -> dict:
        self.next_id += 1
        my_id = self.next_id
        self._send(json.dumps({"id": my_id, "method": method, "params": params}))
        while True:
            message = self._recv()
            if message.get("id") == my_id:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})

    def evaluate(self, expression: str, await_promise: bool = False):
        result = self.call("Runtime.evaluate", expression=expression, awaitPromise=await_promise, returnByValue=True)
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass
