"""Minimal RFC 6455 client for Soloist's local WebSocket API.

Kodi ships no WebSocket library, and Soloist only needs unencrypted text
frames on 127.0.0.1, so this stays on the standard library. No Kodi imports
here, so the module is testable outside Kodi.
"""

import base64
import hashlib
import os
import socket
import struct
import threading

_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONTINUATION = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA


class ConnectionClosed(Exception):
    pass


def accept_key(key):
    return base64.b64encode(hashlib.sha1(key.encode() + _GUID).digest()).decode()


def encode_frame(opcode, payload, mask_key=None):
    """Encode one final client frame. Clients must mask (RFC 6455 5.3)."""
    if mask_key is None:
        mask_key = os.urandom(4)
    header = bytearray([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length < 1 << 16:
        header.append(0x80 | 126)
        header += struct.pack("!H", length)
    else:
        header.append(0x80 | 127)
        header += struct.pack("!Q", length)
    masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return bytes(header) + mask_key + masked


def read_frame(read_exact):
    """Read one frame via read_exact(n) -> bytes. Returns (fin, opcode, payload)."""
    first, second = read_exact(2)
    fin = bool(first & 0x80)
    opcode = first & 0x0F
    length = second & 0x7F
    if length == 126:
        (length,) = struct.unpack("!H", read_exact(2))
    elif length == 127:
        (length,) = struct.unpack("!Q", read_exact(8))
    mask_key = read_exact(4) if second & 0x80 else None
    payload = read_exact(length) if length else b""
    if mask_key:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return fin, opcode, payload


class WebSocket:
    def __init__(self, host, port, timeout=5.0):
        self._sock = socket.create_connection((host, port), timeout)
        self._send_lock = threading.Lock()
        try:
            self._handshake(host, port)
        except Exception:
            self._sock.close()
            raise
        self._sock.settimeout(None)

    def _handshake(self, host, port):
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            "GET / HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self._sock.sendall(request.encode())
        # Byte by byte so no frame data after the headers gets swallowed.
        response = b""
        while not response.endswith(b"\r\n\r\n"):
            chunk = self._sock.recv(1)
            if not chunk:
                raise ConnectionClosed("closed during handshake")
            response += chunk
            if len(response) > 16384:
                raise ConnectionError("handshake response too long")
        lines = response.decode("latin-1").split("\r\n")
        if " 101 " not in lines[0] + " ":
            raise ConnectionError(f"handshake rejected: {lines[0]}")
        headers = {}
        for line in lines[1:]:
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        if headers.get("sec-websocket-accept") != accept_key(key):
            raise ConnectionError("handshake accept key mismatch")

    def _read_exact(self, n):
        data = b""
        while len(data) < n:
            chunk = self._sock.recv(n - len(data))
            if not chunk:
                raise ConnectionClosed("connection closed")
            data += chunk
        return data

    def _send(self, opcode, payload):
        with self._send_lock:
            self._sock.sendall(encode_frame(opcode, payload))

    def send_text(self, text):
        self._send(OP_TEXT, text.encode())

    def recv_text(self):
        """Block until a complete text message arrives; answers pings."""
        parts = []
        while True:
            fin, opcode, payload = read_frame(self._read_exact)
            if opcode == OP_PING:
                self._send(OP_PONG, payload)
            elif opcode == OP_PONG:
                pass
            elif opcode == OP_CLOSE:
                try:
                    self._send(OP_CLOSE, payload[:2])
                except OSError:
                    pass
                raise ConnectionClosed("server closed the connection")
            elif opcode in (OP_TEXT, OP_BINARY, OP_CONTINUATION):
                parts.append(payload)
                if fin:
                    return b"".join(parts).decode()

    def settimeout(self, timeout):
        self._sock.settimeout(timeout)

    def close(self):
        try:
            self._send(OP_CLOSE, struct.pack("!H", 1000))
        except OSError:
            pass
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._sock.close()
