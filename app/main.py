import argparse
import json
import random
import re
import traceback
from collections import deque
from dataclasses import dataclass
from queue import Queue
from socket import socket
from threading import Condition, Event, Thread
from typing import Any
from urllib.request import urlopen

from .config import Settings, load_settings
from .language import detect_lang
from .microphone import stream_microphone
from .realtime_stt import RealtimeSTT
from .relay import connect, encode_turn, listen, receive_lines
from .tts import speak

EMERGENCY_KEYWORDS = (
    "help",
    "emergency",
    "danger",
    "fire",
    "accident",
    "ambulance",
    "police",
    "madad",
    "bachao",
    "khatra",
    "aag",
    "मदद",
    "बचाओ",
    "खतरा",
    "आग",
    "पुलिस",
    "एम्बुलेंस",
)
EMERGENCY_KEYWORD_PATTERN = re.compile(
    r"(?<!\w)("
    + "|".join(re.escape(keyword) for keyword in EMERGENCY_KEYWORDS)
    + r")(?!\w)",
    re.IGNORECASE,
)


def find_emergency_keyword(text: str) -> str | None:
    match = EMERGENCY_KEYWORD_PATTERN.search(text)
    return match.group(1) if match is not None else None


# TODO: Replace test coordinates with real device GPS.
TEST_EMERGENCY_LOCATION = (12.9716, 77.5946)
MAX_RETRY_QUEUE_SIZE = 100
MAX_RECONNECT_BACKOFF_SECONDS = 15


def get_location(settings: Settings) -> dict[str, float | str] | None:
    if settings.relay_lat is not None and settings.relay_lon is not None:
        return {
            "lat": settings.relay_lat,
            "lon": settings.relay_lon,
            "source": "manual",
        }

    if settings.location_source in ("ip", "auto"):
        try:
            with urlopen("https://ipapi.co/json/", timeout=3) as response:
                data: Any = json.load(response)
            lat = float(data["latitude"])
            lon = float(data["longitude"])
            return {"lat": lat, "lon": lon, "source": "ip"}
        except Exception:
            pass

    lat, lon = TEST_EMERGENCY_LOCATION
    return {"lat": lat, "lon": lon, "source": "test"}


@dataclass(frozen=True)
class PendingMessage:
    payload: bytes
    transcript: str
    audio_bytes: int
    emergency: bool


class RetryQueue:
    def __init__(self, max_size: int) -> None:
        self._items: deque[PendingMessage] = deque()
        self._condition = Condition()
        self._max_size = max_size

    def put(self, message: PendingMessage) -> bool:
        with self._condition:
            if len(self._items) >= self._max_size:
                non_emergency = next(
                    (
                        index
                        for index, item in enumerate(self._items)
                        if not item.emergency
                    ),
                    None,
                )
                if non_emergency is not None:
                    del self._items[non_emergency]
                elif not message.emergency:
                    return False
            self._items.append(message)
            self._condition.notify()
            return True

    def put_front(self, message: PendingMessage) -> None:
        with self._condition:
            if len(self._items) >= self._max_size:
                non_emergency = next(
                    (
                        index
                        for index, item in enumerate(self._items)
                        if not item.emergency
                    ),
                    None,
                )
                if non_emergency is not None:
                    del self._items[non_emergency]
            self._items.appendleft(message)
            self._condition.notify()

    def get(self, timeout: float | None = None) -> PendingMessage | None:
        with self._condition:
            if not self._items:
                self._condition.wait(timeout)
            if not self._items:
                return None
            return self._items.popleft()

    def get_nowait(self) -> PendingMessage | None:
        with self._condition:
            if not self._items:
                return None
            return self._items.popleft()

    def size(self) -> int:
        with self._condition:
            return len(self._items)


def run_sender(
    settings: Settings,
    stop_event: Event,
    retry_connection: bool = False,
) -> None:
    retry_queue = RetryQueue(MAX_RETRY_QUEUE_SIZE)
    connected = Event()
    location = get_location(settings)
    if location is not None:
        print(
            f"[location] source={location['source']} "
            f"lat={location['lat']} lon={location['lon']}"
        )

    def on_turn(transcript: str, audio_bytes: int) -> None:
        emergency_keyword = find_emergency_keyword(transcript)
        emergency = emergency_keyword is not None
        if emergency:
            print(
                f"[you] {transcript}  "
                f"(emergency: '{emergency_keyword}', location attached)"
            )
        else:
            print(f"[you] {transcript}")
        payload = encode_turn(
            transcript,
            audio_bytes,
            emergency,
            location,
        )
        message = PendingMessage(payload, transcript, audio_bytes, emergency)
        if not retry_queue.put(message):
            print("[link] queue full, dropped new non-emergency message")
        elif not connected.is_set():
            print(f"[link] queued {retry_queue.size()} message(s)")

    def send_turns() -> None:
        connection: socket | None = None
        backoff = 1.0
        flushed = 0
        flushing = False

        def lose_connection() -> None:
            nonlocal connection
            if connection is not None:
                try:
                    connection.close()
                except OSError:
                    pass
            connection = None
            if connected.is_set():
                connected.clear()
                print("[link] lost")

        while True:
            if stop_event.is_set():
                return
            if connection is None:
                try:
                    connection = connect(settings.relay_host, settings.relay_port)
                    connected.set()
                    print("[link] connected")
                    backoff = 1.0
                    flushed = 0
                    flushing = True
                except OSError:
                    delay = min(backoff, MAX_RECONNECT_BACKOFF_SECONDS)
                    delay += random.uniform(0, min(0.25, delay / 4))
                    print(f"[link] retrying in {delay:.1f}s")
                    if stop_event.wait(delay):
                        return
                    backoff = min(backoff * 2, MAX_RECONNECT_BACKOFF_SECONDS)
                    continue

            turn = (
                retry_queue.get_nowait()
                if flushing
                else retry_queue.get(timeout=0.2)
            )
            if turn is None:
                if flushing and flushed:
                    print(f"[link] flushed {flushed} message(s)")
                if flushing:
                    flushed = 0
                    flushing = False
                continue
            try:
                assert connection is not None
                connection.sendall(turn.payload)
                text_bytes = len(turn.transcript.encode("utf-8"))
                print(
                    f"[bytes] audio={turn.audio_bytes} text={text_bytes} "
                    f"network={len(turn.payload)} ratio={turn.audio_bytes / text_bytes:.1f}x"
                )
                if flushing:
                    flushed += 1
            except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
                retry_queue.put_front(turn)
                lose_connection()
                backoff = 1.0
                continue

    worker = Thread(target=send_turns, daemon=True)
    stt: RealtimeSTT | None = None
    try:
        worker.start()
        stt = RealtimeSTT(settings.assemblyai_api_key or "", on_turn, stop_event)
        if not stop_event.is_set():
            stt.connect()
        if not stop_event.is_set():
            stream_microphone(stt.stream, stop_event)
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as error:
        print(f"\nSender error: {error}")
    finally:
        stop_event.set()
        if stt is not None:
            try:
                stt.disconnect()
            except Exception as error:
                print(f"\nAssemblyAI disconnect error: {error}")
        worker.join(timeout=5)


def run_receiver(settings: Settings, stop_event: Event) -> None:
    server: socket | None = None
    connection: socket | None = None
    turns: Queue[
        tuple[
            str,
            int,
            int,
            bool,
            float | None,
            float | None,
            str | None,
        ]
        | None
    ] = Queue()

    def process_turns() -> None:
        while True:
            turn = turns.get()
            if turn is None:
                return
            try:
                (
                    transcript,
                    audio_bytes,
                    network_bytes,
                    emergency,
                    lat,
                    lon,
                    loc_source,
                ) = turn
                text_bytes = len(transcript.encode("utf-8"))
                print(
                    f"[bytes] audio={audio_bytes} text={text_bytes} "
                    f"network={network_bytes} ratio={audio_bytes / text_bytes:.1f}x"
                )
                lang = detect_lang(transcript)
                print(f"[received] ({lang}) {transcript}")
                speak(transcript, lang, settings.tts_engine)
                if emergency and lat is not None and lon is not None:
                    location_description = {
                        "manual": "Location (manually set)",
                        "ip": "Approximate location (IP-based, may be off by several km)",
                        "test": "TEST location, not real",
                    }.get(loc_source, "Location source unknown")
                    print(
                        f"\nEMERGENCY ALERT: {transcript}\n"
                        f"{location_description}\n"
                        f"Location: https://maps.google.com/?q={lat},{lon}"
                    )
            except Exception as error:
                print(f"\nSpeech error: {error}")
                traceback.print_exc()

    worker = Thread(target=process_turns, daemon=True)
    worker.start()
    try:
        server = listen(settings.relay_bind_host, settings.relay_port)
        server.settimeout(1)
        while not stop_event.is_set():
            try:
                connection, _address = server.accept()
            except TimeoutError:
                continue
            try:
                for line in receive_lines(connection):
                    try:
                        message: Any = json.loads(line)
                        if (
                            not isinstance(message, dict)
                            or not isinstance(message.get("transcript"), str)
                            or not message["transcript"]
                            or type(message.get("audio_bytes")) is not int
                            or type(message.get("emergency")) is not bool
                        ):
                            raise ValueError("invalid turn fields")
                        emergency = message["emergency"]
                        lat = message.get("lat")
                        lon = message.get("lon")
                        loc_source = message.get("loc_source")
                        if not isinstance(loc_source, str):
                            loc_source = None
                        if emergency and (
                            not isinstance(lat, (int, float))
                            or not isinstance(lon, (int, float))
                        ):
                            raise ValueError("emergency message is missing location")
                        turns.put(
                            (
                                message["transcript"],
                                message["audio_bytes"],
                                len(line) + 1,
                                emergency,
                                lat,
                                lon,
                                loc_source,
                            )
                        )
                    except (
                        KeyError,
                        TypeError,
                        ValueError,
                        UnicodeDecodeError,
                        json.JSONDecodeError,
                    ) as error:
                        print(f"\nRelay warning: malformed line skipped: {error}")
                    if stop_event.is_set():
                        break
            except OSError as error:
                if not stop_event.is_set():
                    print(f"\nRelay warning: client connection error: {error}")
            finally:
                connection.close()
                connection = None
                if not stop_event.is_set():
                    print("[link] sender disconnected")
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as error:
        print(f"\nReceiver error: {error}")
    finally:
        stop_event.set()
        turns.put(None)
        if connection is not None:
            connection.close()
        if server is not None:
            server.close()
        worker.join(timeout=5)


def run_peer(settings: Settings, stop_event: Event) -> None:
    receiver = Thread(target=run_receiver, args=(settings, stop_event), daemon=True)
    sender = Thread(
        target=run_sender,
        args=(settings, stop_event, True),
        daemon=True,
    )
    receiver.start()
    sender.start()
    try:
        while not stop_event.wait(0.1):
            pass
    except KeyboardInterrupt:
        print("\nStopping...")
        stop_event.set()
    finally:
        stop_event.set()
        receiver.join(timeout=5)
        sender.join(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--role", choices=("sender", "receiver", "peer"), required=True
    )
    role = parser.parse_args().role
    settings = load_settings(role)
    stop_event = Event()
    try:
        if role == "sender":
            run_sender(settings, stop_event)
        elif role == "receiver":
            run_receiver(settings, stop_event)
        else:
            run_peer(settings, stop_event)
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as error:
        print(f"\nRelay startup error: {error}")


if __name__ == "__main__":
    main()
