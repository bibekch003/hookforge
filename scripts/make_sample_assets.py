"""Generate the demo assets: a synthetic 24s "raw take" + its transcript.

Why synthetic: the repo must be runnable by a judge with no media lying around.
The clip is built to exercise the pipeline honestly - it has real scene changes,
real audio energy peaks in specific windows, and a face-like subject, so the
audio and CV stages have something genuine to detect.

    python scripts/make_sample_assets.py
"""
from __future__ import annotations

import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import ffmpeg_bin  # noqa: E402
from app.pipeline.thumbs import _font  # noqa: E402

SAMPLES = ROOT / "samples"
FPS = 12
DURATION = 24.0
W, H = 1280, 720
SR = 16000

LINES = [
    "I spent three years editing my own videos",
    "and losing the first thousand viewers in the first three seconds.",
    "Then I stopped starting with the intro.",
    "Now I open with the result, the mess, or the mistake.",
    "Here is the workflow I actually use now.",
    "I pull the loudest thirty seconds out of the raw take",
    "and I build the hook around that moment.",
    "Then I render the same hook in three aspect ratios",
    "so I can post it everywhere without re-editing.",
    "The captions get rewritten for each platform",
    "because a forty two character line breaks on a reel.",
    "And the thumbnail is the last thing I make, not the first.",
    "That single change doubled my watch time in six weeks.",
]

SCENE_COLOURS = [
    ((16, 26, 38), (30, 58, 74)),
    ((28, 20, 38), (62, 34, 66)),
    ((14, 32, 28), (28, 70, 56)),
    ((38, 28, 14), (78, 54, 22)),
    ((18, 24, 44), (34, 48, 92)),
    ((40, 16, 22), (86, 30, 40)),
]


def gradient(c0, c1) -> Image.Image:
    """Cached-per-scene vertical gradient with a vignette."""
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    x = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    base = np.zeros((H, W, 3), dtype=np.float32)
    for ch in range(3):
        base[:, :, ch] = c0[ch] * (1 - y) + c1[ch] * y
    vig = 1.0 - 0.45 * (((x - 0.5) ** 2 + (y - 0.5) ** 2) ** 0.5)
    base *= vig[:, :, None]
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")


def draw_frame(bg: Image.Image, idx: int, total: int, line: str, loud: bool) -> Image.Image:
    """`line` is kept for call-site symmetry; captions are the pipeline's job."""
    img = bg.copy()
    d = ImageDraw.Draw(img, "RGBA")

    t = idx / FPS
    # subject: soft ellipse "presenter" with a face, gently drifting
    cx = W // 2 + int(26 * np.sin(t * 0.9))
    cy = int(H * 0.56)
    d.ellipse([cx - 190, cy - 60, cx + 190, cy + 300], fill=(24, 28, 36, 235))
    d.ellipse([cx - 96, cy - 250, cx + 96, cy - 40], fill=(206, 168, 138, 255))
    d.ellipse([cx - 44, cy - 176, cx - 20, cy - 152], fill=(32, 30, 34, 255))
    d.ellipse([cx + 20, cy - 176, cx + 44, cy - 152], fill=(32, 30, 34, 255))
    d.arc([cx - 34, cy - 130, cx + 34, cy - 78], start=10, end=170, fill=(120, 70, 70, 255), width=5)

    # hard cut flash: each new scene gets a bright bar for one frame
    if idx % (FPS * 4) == 0:
        d.rectangle([0, 0, W, 6], fill=(61, 220, 151, 255))

    # label + timecode
    small = _font(20)
    d.text((28, 24), "RAW TAKE  ·  4K  ·  unedited", font=small, fill=(150, 168, 190, 255))
    d.text((W - 150, 24), f"{int(t) // 60:02d}:{int(t) % 60:02d}", font=small, fill=(150, 168, 190, 255))

    # No burned-in captions here on purpose: the pipeline burns its own, and two
    # competing caption layers make the 9:16 crop look broken in a demo.
    # A soft audio meter stands in for the speech, so the clip still reads as a
    # take with quiet and loud passages.
    meter_w = int(W * 0.16)
    level = 0.85 if loud else 0.32
    d.rectangle([W - meter_w - 28, 60, W - 28, 74], fill=(255, 255, 255, 40))
    d.rectangle([W - meter_w - 28, 60, W - 28 - int(meter_w * (1 - level)), 74],
                fill=(255, 210, 61, 235) if loud else (61, 220, 151, 200))

    if loud:
        d.rectangle([0, H - 4, W, H], fill=(255, 210, 61, 255))
    return img


def make_audio(path: Path) -> None:
    """Speech-ish synth: syllable bursts, hot in 4-8s and 16-20s."""
    n = int(SR * DURATION)
    audio = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(7)
    t = 0.35
    while t < DURATION - 0.3:
        loud = (4.0 <= t <= 8.0) or (16.0 <= t <= 20.0)
        dur = float(rng.uniform(0.12, 0.22))
        f0 = float(rng.uniform(108, 186))
        amp = 0.55 if loud else 0.20
        a = int(t * SR)
        b = min(n, a + int(dur * SR))
        seg_t = np.arange(b - a) / SR
        span = max(1e-6, float(seg_t[-1]) if len(seg_t) else 1.0)
        # clip before the fractional power: sin(pi) can land a hair below zero
        env = np.clip(np.sin(np.pi * seg_t / span), 0.0, None) ** 0.7
        sig = (np.sin(2 * np.pi * f0 * seg_t)
               + 0.45 * np.sin(2 * np.pi * 2 * f0 * seg_t)
               + 0.25 * np.sin(2 * np.pi * 3 * f0 * seg_t)
               + 0.10 * rng.normal(0, 1, len(seg_t)))
        audio[a:b] += (amp * env * sig).astype(np.float32)
        t += dur + float(rng.uniform(0.05, 0.13))
    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    audio = np.clip(audio / max(1e-6, float(np.abs(audio).max())) * 0.92, -1, 1)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((audio * 32767).astype(np.int16).tobytes())


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    frames_dir = SAMPLES / "_frames"
    frames_dir.mkdir(exist_ok=True)

    total = int(FPS * DURATION)
    print(f"rendering {total} frames at {W}x{H}…")
    scene_len = DURATION / len(SCENE_COLOURS)
    bgs = [gradient(*c) for c in SCENE_COLOURS]

    for i in range(total):
        t = i / FPS
        scene = min(len(bgs) - 1, int(t // scene_len))
        line_idx = min(len(LINES) - 1, int(t / DURATION * len(LINES)))
        loud = (4.0 <= t <= 8.0) or (16.0 <= t <= 20.0)
        frame = draw_frame(bgs[scene], i, total, LINES[line_idx], loud)
        frame.save(frames_dir / f"f_{i:04d}.png", "PNG", compress_level=1)
        if i % 48 == 0:
            print(f"  frame {i}/{total}")

    wav = SAMPLES / "_audio.wav"
    make_audio(wav)
    print("audio synthesised")

    out = SAMPLES / "sample_creator_clip.mp4"
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
           "-framerate", str(FPS), "-i", str(frames_dir / "f_%04d.png"),
           "-i", str(wav),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg failed: {proc.stderr[-800:]}")

    (SAMPLES / "sample_creator_clip.txt").write_text(" ".join(LINES), encoding="utf-8")

    # keep the repo small: frames and wav are intermediates
    for f in frames_dir.glob("*.png"):
        f.unlink()
    frames_dir.rmdir()
    wav.unlink()

    print(f"wrote {out} ({out.stat().st_size / 1048576:.1f} MB) + sidecar transcript")


if __name__ == "__main__":
    main()
