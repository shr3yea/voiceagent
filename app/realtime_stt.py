from collections.abc import Callable
from threading import Event, Lock

from assemblyai.streaming.v3 import (
    BeginEvent,
    Encoding,
    RealTimeError,
    RealTimeEvents,
    RealTimeParameters,
    RealTimeTranscriber,
    RealTimeTranscriberOptions,
    TerminationEvent,
    TurnEvent,
)

from .microphone import SAMPLE_RATE


class RealtimeSTT:
    def __init__(
        self,
        api_key: str,
        on_final_turn: Callable[[str, int], None],
        stop_event: Event,
    ) -> None:
        self._on_final_turn = on_final_turn
        self._stop_event = stop_event
        self._last_partial = ""
        self._audio_bytes = 0
        self._audio_lock = Lock()
        self._connected = False
        self._client = RealTimeTranscriber(
            RealTimeTranscriberOptions(terminate_timeout=30.0),
            api_key=api_key,
        )
        self._client.on(RealTimeEvents.Begin, self._on_begin)
        self._client.on(RealTimeEvents.Turn, self._on_turn)
        self._client.on(RealTimeEvents.Termination, self._on_termination)
        self._client.on(RealTimeEvents.Error, self._on_error)

    def connect(self) -> None:
        self._client.connect(
            RealTimeParameters(
                sample_rate=SAMPLE_RATE,
                speech_model="universal-3-5-pro",
                encoding=Encoding.pcm_s16le,
                format_turns=True,
            )
        )
        self._connected = True

    def stream(self, audio: bytes) -> None:
        with self._audio_lock:
            self._audio_bytes += len(audio)
        self._client.stream(audio)

    def disconnect(self) -> None:
        if not self._connected:
            return
        try:
            self._client.disconnect(terminate=True)
        finally:
            self._connected = False

    def _on_begin(self, _client: RealTimeTranscriber, event: BeginEvent) -> None:
        print(f"AssemblyAI session started: {event.id}")

    def _on_turn(self, _client: RealTimeTranscriber, event: TurnEvent) -> None:
        if not event.transcript:
            return

        if event.end_of_turn:
            print("\r" + " " * (len(self._last_partial) + 12) + "\r", end="", flush=True)
            self._last_partial = ""
            with self._audio_lock:
                audio_bytes = self._audio_bytes
                try:
                    self._on_final_turn(event.transcript, audio_bytes)
                finally:
                    self._audio_bytes = 0
        else:
            self._last_partial = event.transcript
            print(f"\rYou (live): {event.transcript}", end="", flush=True)

    def _on_termination(
        self, _client: RealTimeTranscriber, event: TerminationEvent
    ) -> None:
        print(
            f"AssemblyAI session terminated "
            f"({event.audio_duration_seconds:.1f}s of audio)"
        )

    def _on_error(self, _client: RealTimeTranscriber, error: RealTimeError) -> None:
        print(f"\nAssemblyAI error: {error}")
        self._stop_event.set()
