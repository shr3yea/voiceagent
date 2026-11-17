from collections.abc import Callable
from threading import Event

import sounddevice as sd


SAMPLE_RATE = 16_000
CHANNELS = 1
BLOCK_SIZE = 800


def stream_microphone(send_audio: Callable[[bytes], None], stop_event: Event) -> None:
    """Capture signed 16-bit mono PCM and forward blocks to AssemblyAI."""

    def on_audio(indata, _frames, _time, status) -> None:
        if status:
            print(f"\nMicrophone warning: {status}", flush=True)
        if not stop_event.is_set():
            send_audio(bytes(indata))

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=BLOCK_SIZE,
        channels=CHANNELS,
        dtype="int16",
        callback=on_audio,
    ):
        print("Listening... speak into your microphone. Press Ctrl+C to stop.")
        while not stop_event.wait(0.1):
            pass

