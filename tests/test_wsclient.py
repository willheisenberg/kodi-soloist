import base64
import os
import socket
import struct
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "service.soloist", "resources", "lib"))

import pytest
import wsclient


def _reader(data):
    buffer = bytearray(data)

    def read_exact(n):
        chunk = bytes(buffer[:n])
        del buffer[:n]
        if len(chunk) < n:
            raise wsclient.ConnectionClosed("eof")
        return chunk

    return read_exact


def test_accept_key_matches_rfc_example():
    # RFC 6455 section 1.3
    assert wsclient.accept_key("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


@pytest.mark.parametrize("length", [0, 5, 125, 126, 65535, 65536])
def test_frame_roundtrip(length):
    payload = os.urandom(length)
    frame = wsclient.encode_frame(wsclient.OP_TEXT, payload, mask_key=b"\x01\x02\x03\x04")
    assert frame[1] & 0x80  # client frames are masked
    assert wsclient.read_frame(_reader(frame)) == (True, wsclient.OP_TEXT, payload)


def test_read_unmasked_server_frame():
    frame = bytes([0x81, 5]) + b"hello"
    assert wsclient.read_frame(_reader(frame)) == (True, wsclient.OP_TEXT, b"hello")


def _server_frame(opcode, payload, fin=True):
    return bytes([(0x80 if fin else 0) | opcode, len(payload)]) + payload


class _FakeServer:
    """Accepts one client, completes the handshake, then sends `frames`."""

    def __init__(self, frames, accept_override=None):
        self._listener = socket.socket()
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(1)
        self.port = self._listener.getsockname()[1]
        self._frames = frames
        self._accept_override = accept_override
        self.received = []
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        conn, _ = self._listener.accept()
        with conn:
            request = b""
            while not request.endswith(b"\r\n\r\n"):
                request += conn.recv(1)
            key = next(
                line.split(":", 1)[1].strip()
                for line in request.decode().split("\r\n")
                if line.lower().startswith("sec-websocket-key")
            )
            accept = self._accept_override or wsclient.accept_key(key)
            conn.sendall(
                (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
                ).encode()
                + b"".join(self._frames)
            )

            def read_exact(n):
                data = b""
                while len(data) < n:
                    chunk = conn.recv(n - len(data))
                    if not chunk:
                        raise wsclient.ConnectionClosed("eof")
                    data += chunk
                return data

            try:
                while True:
                    self.received.append(wsclient.read_frame(read_exact))
            except (wsclient.ConnectionClosed, OSError):
                pass
        self._listener.close()

    def join(self):
        self._thread.join(timeout=5)


def test_client_handles_ping_fragments_and_close():
    server = _FakeServer(
        [
            _server_frame(wsclient.OP_PING, b"hi"),
            _server_frame(wsclient.OP_TEXT, b'{"type":', fin=False),
            _server_frame(wsclient.OP_CONTINUATION, b'"auth_state"}'),
            _server_frame(wsclient.OP_CLOSE, struct.pack("!H", 1000)),
        ]
    )
    ws = wsclient.WebSocket("127.0.0.1", server.port)
    ws.send_text('{"type":"command","command":"get_auth_state"}')
    assert ws.recv_text() == '{"type":"auth_state"}'
    with pytest.raises(wsclient.ConnectionClosed):
        ws.recv_text()
    ws.close()
    server.join()
    opcodes = [opcode for _, opcode, _ in server.received]
    assert opcodes[:3] == [wsclient.OP_TEXT, wsclient.OP_PONG, wsclient.OP_CLOSE]
    assert server.received[0][2] == b'{"type":"command","command":"get_auth_state"}'
    assert server.received[1][2] == b"hi"


def test_client_rejects_wrong_accept_key():
    server = _FakeServer([], accept_override=base64.b64encode(b"x" * 20).decode())
    with pytest.raises(ConnectionError):
        wsclient.WebSocket("127.0.0.1", server.port)
    server.join()
