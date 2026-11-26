"""Optional Thai text-to-speech via edge-tts (pip install edge-tts). Returns mp3 path or None."""
from __future__ import annotations

import hashlib
from pathlib import Path

VOICE = "th-TH-PremwadeeNeural"
OUT = Path(__file__).parent / "overlay" / "audio"


async def speak(text: str) -> str | None:
    try:
        import edge_tts
    except ImportError:
        return None
    try:
        OUT.mkdir(exist_ok=True)
        name = hashlib.sha1(text.encode()).hexdigest()[:12] + ".mp3"
        await edge_tts.Communicate(text, VOICE).save(str(OUT / name))
        return f"/audio/{name}"
    except Exception as e:
        print(f"[tts] failed: {e}")
        return None
