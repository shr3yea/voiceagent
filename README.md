# Hindi + English Voice Relay

## What it does

This project is a two-person Hindi + English voice relay for communicating
over a poor-connectivity link. Each finalized microphone turn is transcribed
by AssemblyAI Universal-3.5 Pro, sent as compact UTF-8 JSON over a TCP
connection, and spoken aloud on the other machine with `edge-tts`.

The relay does not put an LLM in the critical path. It keeps a bytes-per-turn
log for raw audio, transcript text, and the complete newline-framed network
message.

## Architecture

```text
Person A                         Person B
Microphone                       TCP receiver
    │                                  │
    ▼                                  ▼
AssemblyAI STT ── JSON/TCP ──► detect_lang ──► edge-tts ──► speaker
```

Run the same application in `peer` mode on both machines for bidirectional
communication:

```text
Person A: mic/STT ──► TCP ──► TTS
           TTS ◄──── TCP ◄──── mic/STT
Person B: mic/STT ──► TCP ──► TTS
           TTS ◄──── TCP ◄──── mic/STT
```

## Setup

Requires Python 3.10+ and macOS audio input access.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Set the AssemblyAI key and relay settings in `.env`:

```dotenv
ASSEMBLYAI_API_KEY=your_assemblyai_api_key_here
RELAY_HOST=192.168.1.42
RELAY_BIND_HOST=0.0.0.0
RELAY_PORT=8765
```

- `RELAY_HOST` is the remote machine's address for a sender or peer.
- `RELAY_BIND_HOST` is the local address for the receiver or peer.
- `RELAY_PORT` must match on both machines.

The receiver role does not need an AssemblyAI key. A peer or sender does.
Never commit real API keys; `.env` is ignored by Git.

## How to run

From the project root, with the virtual environment activated:

### One-way demo

On Person B's machine, start the receiver first:

```bash
python3 -m app.main --role receiver
```

On Person A's machine, set `RELAY_HOST` to Person B's LAN address and run:

```bash
python3 -m app.main --role sender
```

### Bidirectional peer demo

On each machine, set `RELAY_HOST` to the other machine's LAN address and run:

```bash
python3 -m app.main --role peer
```

Each peer process runs one sender thread and one receiver thread, so one
terminal per person is enough.

Press `Ctrl+C` to stop the microphone, queue workers, sockets, and AssemblyAI
connection cleanly.

## Supported languages

- English
- Hindi

The receiving side routes a transcript to Hindi when it contains Devanagari
characters; otherwise it uses English speech.

## Emergency messages

Transcripts containing a whole-word emergency keyword (case-insensitive) are
marked as emergency messages. Supported keywords include English/Hinglish
(`help`, `emergency`, `danger`, `fire`, `accident`, `ambulance`, `police`,
`madad`, `bachao`, `khatra`, `aag`) and Devanagari (`मदद`, `बचाओ`, `खतरा`,
`आग`, `पुलिस`, `एम्बुलेंस`). Location precedence is:

1. `RELAY_LAT` and `RELAY_LON`, when both are set (`manual`).
2. IP geolocation from `https://ipapi.co/json/` when `LOCATION_SOURCE=ip` or
   `auto` (`ip`).
3. Hardcoded test coordinates (`test`).

Set `LOCATION_SOURCE=manual`, `ip`, or `auto` in `.env`; `auto` is the default.
The optional `RELAY_LAT` and `RELAY_LON` values are decimal coordinates. The
sender resolves and caches one location at startup, and the receiver prints a
Google Maps link after speaking the transcript.

## Bytes-per-turn log

Each finalized turn logs:

```text
[bytes] audio=<n> text=<n> network=<n> ratio=<n.x>x
```

`audio` is raw microphone audio passed to the STT stream, `text` is the
transcript's UTF-8 byte length, and `network` is the complete encoded JSON
message including its newline delimiter. Emergency messages are larger because
they include `lat` and `lon`.

## Known limitations

- AssemblyAI, `edge-tts`, and the relay link require network connectivity.
- Audio playback depends on macOS's `afplay` command.
- Language routing is based only on Devanagari detection. Mixed-language turns
  and languages other than Hindi and English may be routed as English.
- TCP delivery is reliable and ordered, but this demo has no offline queue,
  persistence, acknowledgements, automatic reconnection, or encryption.
- IP geolocation is approximate and may be off by several kilometres.
- If IP lookup fails, the relay uses the hardcoded test coordinates. Production
  deployments should replace them with real device GPS.

## Inspiration

This project is inspired by SIH problem statement **26173** and the goal of
building a low-bitrate, multilingual voice interface for real-world
communication.
