import json
import socket
from collections.abc import Iterator


def encode_turn(
    transcript: str,
    audio_bytes: int,
    emergency: bool = False,
    location: tuple[float, float] | dict[str, object] | None = None,
) -> bytes:
    message: dict[str, object] = {
        "transcript": transcript,
        "audio_bytes": audio_bytes,
        "emergency": emergency,
    }
    if emergency and location is not None:
        if isinstance(location, dict):
            message["lat"] = location["lat"]
            message["lon"] = location["lon"]
            message["loc_source"] = location["source"]
        else:
            message["lat"], message["lon"] = location
    return (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")


def connect(host: str, port: int) -> socket.socket:
    return socket.create_connection((host, port))


def listen(host: str, port: int) -> socket.socket:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(1)
    return server


def receive_lines(connection: socket.socket) -> Iterator[bytes]:
    buffer = b""
    while True:
        chunk = connection.recv(4096)
        if not chunk:
            if buffer:
                yield buffer
            return
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if line:
                yield line
