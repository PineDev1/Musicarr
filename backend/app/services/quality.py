from __future__ import annotations

from pathlib import Path

from mutagen import File as MutagenFile


QUALITY_RANK = {"flac": 3, "320": 2, "128": 1, "": 0}


def quality_rank(q: str | None) -> int:
    return QUALITY_RANK.get((q or "").lower(), 0)


def detect_file_quality(path: Path) -> str:
    """Best-effort quality from extension + mutagen bitrate."""
    ext = path.suffix.lower()
    if ext in {".flac", ".wav", ".aiff", ".aif"}:
        return "flac"
    if ext in {".ogg", ".opus"}:
        # Treat as lossy mid unless we can read bitrate
        pass
    try:
        audio = MutagenFile(path)
        if audio is None:
            return "320" if ext == ".mp3" else ""
        br = getattr(audio.info, "bitrate", None) if audio.info else None
        if br:
            # mutagen often reports bits/sec
            kbps = int(br) // 1000 if int(br) > 1000 else int(br)
            if kbps >= 500 or ext == ".flac":
                return "flac"
            if kbps >= 256:
                return "320"
            if kbps > 0:
                return "128"
    except Exception:  # noqa: BLE001
        pass
    if ext == ".mp3":
        return "320"
    if ext in {".m4a", ".aac"}:
        return "320"
    return ""


def needs_upgrade(current: str | None, target: str | None) -> bool:
    return quality_rank(current) < quality_rank(target)
