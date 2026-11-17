from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    assemblyai_api_key: str | None
    groq_model: str
    relay_host: str
    relay_bind_host: str
    relay_port: int
    relay_lat: float | None
    relay_lon: float | None
    location_source: str


def load_settings(role: str) -> Settings:
    load_dotenv()
    needs_key = role in ("sender", "peer")
    missing = ["ASSEMBLYAI_API_KEY"] if needs_key and not os.getenv("ASSEMBLYAI_API_KEY") else []
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    relay_lat_value = os.getenv("RELAY_LAT")
    relay_lon_value = os.getenv("RELAY_LON")
    location_source = os.getenv("LOCATION_SOURCE", "auto").lower()
    if location_source not in ("manual", "ip", "auto"):
        raise ValueError("LOCATION_SOURCE must be manual, ip, or auto")

    return Settings(
        assemblyai_api_key=os.getenv("ASSEMBLYAI_API_KEY"),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        relay_host=os.getenv("RELAY_HOST", "127.0.0.1"),
        relay_bind_host=os.getenv("RELAY_BIND_HOST", "0.0.0.0"),
        relay_port=int(os.getenv("RELAY_PORT", "8765")),
        relay_lat=float(relay_lat_value) if relay_lat_value else None,
        relay_lon=float(relay_lon_value) if relay_lon_value else None,
        location_source=location_source,
    )
