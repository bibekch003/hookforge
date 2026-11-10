"""Ingest: probe a video, pull frames, pull audio, detect cuts.

Uses OpenCV for pixel access (no ffprobe dependency) and the resolved ffmpeg
binary for audio extraction.
"""
from __future__ import annotations

import re
import subprocess
import wave
from pathlib import Path

import cv2
import numpy as np

from app.config import WORK_DIR, ffmpeg_bin


def probe(path: str | Path) -> dict:
    """Return width/height/fps/frames/duration/has_audio for a video file."""
    path = Path(path)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {path.name}")
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    if fps <= 0:
        fps = 25.0
    duration = frames / fps if frames else _duration_from_ffmpeg(path)
    return {
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "frames": frames,
        "duration": round(float(duration), 3),
        "aspect": round(width / height, 4) if height else 1.0,
        "has_audio": _has_audio(path),
        "size_mb": round(path.stat().st_size / 1_048_576, 2),
    }


def _ffmpeg_probe_text(path: Path) -> str:
    out = subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-i", str(path)],
        capture_output=True, text=True, timeout=120,
    )
    return (out.stderr or "") + (out.stdout or "")


def _duration_from_ffmpeg(path: Path) -> float:
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", _ffmpeg_probe_text(path))
    if not m:
        return 0.0
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def _has_audio(path: Path) -> bool:
    return "Audio:" in _ffmpeg_probe_text(path)


def extract_frame(path: str | Path, t: float) -> np.ndarray:
    """Grab a single BGR frame at `t` seconds."""
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000.0)
    ok, frame = cap.read()
    if not ok:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, frame = cap.read()
    cap.release()
    if not ok:
        raise ValueError("Could not read a frame from the video")
    return frame


def extract_audio(path: str | Path, sr: int = 16000) -> tuple[np.ndarray, int]:
    """Decode the audio track to mono float32 at `sr`. Returns silence if none."""
    path = Path(path)
    wav_path = WORK_DIR / f"{path.stem}_{sr}.wav"
    proc = subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr),
         "-f", "wav", str(wav_path)],
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0 or not wav_path.exists():
        return np.zeros(sr, dtype=np.float32), sr
    with wave.open(str(wav_path), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        sr = wf.getframerate()
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return audio, sr


def scene_cuts(path: str | Path, sample_fps: float = 2.0) -> list[float]:
    """Histogram-difference cut detection. Cheap, deterministic, no model."""
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(fps / sample_fps)))
    prev_hist = None
    cuts: list[float] = []
    idx = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if ok and frame is not None:
                small = cv2.resize(frame, (96, 54))
                hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
                hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
                cv2.normalize(hist, hist)
                if prev_hist is not None:
                    d = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA))
                    if d > 0.42:
                        cuts.append(round(idx / fps, 3))
                prev_hist = hist
        idx += 1
    cap.release()
    return cuts[:80]


def coverage_score(frames: list[np.ndarray]) -> float:
    """How much visual variety the sampled frames contain (0-1)."""
    if len(frames) < 2:
        return 0.0
    diffs = []
    prev = cv2.cvtColor(cv2.resize(frames[0], (64, 36)), cv2.COLOR_BGR2GRAY).astype(np.float32)
    for f in frames[1:]:
        cur = cv2.cvtColor(cv2.resize(f, (64, 36)), cv2.COLOR_BGR2GRAY).astype(np.float32)
        diffs.append(float(np.mean(np.abs(cur - prev))))
        prev = cur
    return round(min(1.0, float(np.mean(diffs)) / 40.0), 4)
