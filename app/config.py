"""Central configuration for Hookforge.

Every path is overridable with an environment variable so the app can run from a
container, a laptop, or CI without code changes.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.getenv("HOOKFORGE_DATA", ROOT / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
WORK_DIR = DATA_DIR / "work"
EXPORT_DIR = DATA_DIR / "exports"
THUMB_DIR = DATA_DIR / "thumbs"

for _d in (DATA_DIR, UPLOAD_DIR, WORK_DIR, EXPORT_DIR, THUMB_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.getenv("HOOKFORGE_DB", DATA_DIR / "hookforge.db"))

# ---------------------------------------------------------------------------
# Platform delivery presets
# ---------------------------------------------------------------------------
# caption_chars / caption_lines drive both the SRT wrapper and the burn-in
# overlay, so a caption that is legal on YouTube can be rejected for Reels.
PLATFORM_PRESETS: dict[str, dict] = {
    "youtube_shorts": {
        "label": "YouTube Shorts",
        "width": 1080, "height": 1920,
        "max_seconds": 60,
        "caption_chars": 32, "caption_lines": 2,
        "safe_top": 0.14, "safe_bottom": 0.20,
        "crop": "center", "thumb_strategy": "blur_pad",
    },
    "instagram_reel": {
        "label": "Instagram Reels",
        "width": 1080, "height": 1920,
        "max_seconds": 90,
        "caption_chars": 30, "caption_lines": 2,
        "safe_top": 0.16, "safe_bottom": 0.22,
        "crop": "center", "thumb_strategy": "blur_pad",
    },
    "tiktok": {
        "label": "TikTok",
        "width": 1080, "height": 1920,
        "max_seconds": 60,
        "caption_chars": 28, "caption_lines": 2,
        "safe_top": 0.10, "safe_bottom": 0.26,
        "crop": "center", "thumb_strategy": "blur_pad",
    },
    "youtube": {
        "label": "YouTube (16:9)",
        "width": 1920, "height": 1080,
        "max_seconds": None,
        "caption_chars": 42, "caption_lines": 2,
        "safe_top": 0.06, "safe_bottom": 0.08,
        "crop": "fit", "thumb_strategy": "cover",
    },
    "linkedin_square": {
        "label": "LinkedIn (1:1)",
        "width": 1080, "height": 1080,
        "max_seconds": 180,
        "caption_chars": 38, "caption_lines": 2,
        "safe_top": 0.08, "safe_bottom": 0.10,
        "crop": "blur_pad", "thumb_strategy": "cover",
    },
}

# Per-platform intercept of the retention prior (documented in analytics.py).
PLATFORM_PRIOR = {
    "youtube_shorts": 0.055,
    "instagram_reel": 0.060,
    "tiktok": 0.075,
    "youtube": 0.040,
    "linkedin_square": 0.030,
}

MAX_UPLOAD_MB = int(os.getenv("HOOKFORGE_MAX_UPLOAD_MB", "200"))
ALLOWED_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


# ---------------------------------------------------------------------------
# ffmpeg resolution: system binary first, then the static wheel.
# ---------------------------------------------------------------------------
def ffmpeg_bin() -> str:
    env = os.getenv("FFMPEG_BIN")
    if env and Path(env).exists():
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - depends on host
        raise RuntimeError(
            "No ffmpeg found. Install ffmpeg or `pip install imageio-ffmpeg`."
        ) from exc


def ffmpeg_has(filter_name: str) -> bool:
    """True when the available ffmpeg build exposes a filter (e.g. 'subtitles')."""
    import subprocess
    try:
        out = subprocess.run(
            [ffmpeg_bin(), "-hide_banner", "-filters"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except Exception:
        return False
    return any(line.split()[1:2] == [filter_name] for line in out.splitlines() if line.strip())
