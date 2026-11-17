import asyncio
import os
import subprocess
import tempfile
import time

import edge_tts


VOICES = {"en": "en-US-AriaNeural", "hi": "hi-IN-SwaraNeural"}
EDGE_FAILURE_COOLDOWN_SECONDS = 60
EDGE_TIMEOUT_SECONDS = 5
_edge_failed_until = 0.0
_hindi_voice_available: bool | None = None


async def _synthesize(text: str, output_path: str, lang: str = "en") -> None:
    await edge_tts.Communicate(text, voice=VOICES[lang]).save(output_path)


async def _synthesize_with_timeout(
    text: str, output_path: str, lang: str
) -> None:
    await asyncio.wait_for(
        _synthesize(text, output_path, lang),
        timeout=EDGE_TIMEOUT_SECONDS,
    )


def _speak_offline(text: str, lang: str) -> None:
    global _hindi_voice_available
    voice: str | None = None
    if lang == "hi":
        if _hindi_voice_available is None:
            try:
                voices = subprocess.run(
                    ["say", "-v", "?"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                _hindi_voice_available = "Lekha" in (
                    voices.stdout + voices.stderr
                )
            except Exception:
                _hindi_voice_available = False
        if _hindi_voice_available:
            voice = "Lekha"
        else:
            print("[tts] Hindi voice Lekha is not installed, using default voice")
    command = ["say"]
    if voice is not None:
        command.extend(["-v", voice])
    command.append(text)
    subprocess.run(command, check=True)


def speak(text: str, lang: str = "en", engine: str = "auto") -> None:
    """Synthesize and play a response using the configured macOS voice."""

    global _edge_failed_until
    if engine == "say" or (
        engine == "auto" and time.monotonic() < _edge_failed_until
    ):
        _speak_offline(text, lang)
        return

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as audio_file:
        output_path = audio_file.name
    try:
        try:
            asyncio.run(_synthesize_with_timeout(text, output_path, lang))
        except Exception:
            if engine == "edge":
                raise
            _edge_failed_until = (
                time.monotonic() + EDGE_FAILURE_COOLDOWN_SECONDS
            )
            print("[tts] edge-tts failed, using offline voice")
            _speak_offline(text, lang)
            return
        subprocess.run(["afplay", output_path], check=True)
    finally:
        os.unlink(output_path)
