def detect_lang(text: str) -> str:
    """Return Hindi for Devanagari text, otherwise return English."""
    return "hi" if any("\u0900" <= char <= "\u097f" for char in text) else "en"

