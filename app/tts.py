import asyncio
import os
import subprocess
import tempfile

import edge_tts


VOICES = {"en": "en-US-AriaNeural", "hi": "hi-IN-SwaraNeural"}


async def _synthesize(text: str, output_path: str, lang: str = "en") -> None:
    await edge_tts.Communicate(text, voice=VOICES[lang]).save(output_path)


def speak(text: str, lang: str = "en") -> None:
    """Synthesize and play a response using macOS's built-in audio player."""

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as audio_file:
        output_path = audio_file.name
    try:
        asyncio.run(_synthesize(text, output_path, lang))
        subprocess.run(["afplay", output_path], check=True)
    finally:
        os.unlink(output_path)
