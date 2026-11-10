"""Multi-format delivery: one source clip -> platform-ready renders.

Each platform gets its own crop strategy, resolution and (optionally) burned-in
captions. ffmpeg is resolved once in config so the same code runs on a laptop
with system ffmpeg or in a container using the static wheel.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from app.config import PLATFORM_PRESETS, WORK_DIR, ffmpeg_bin, ffmpeg_has


def _filter_graph(width: int, height: int, strategy: str) -> str:
    if strategy == "fit":
        return (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1")
    if strategy == "blur_pad":
        return (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},gblur=sigma=24,eq=brightness=-0.06[bg];"
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    return (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1")


def export_clip(
    src: str | Path,
    out_path: str | Path,
    platform: str = "youtube_shorts",
    start: float = 0.0,
    duration: float | None = None,
    srt_path: str | Path | None = None,
    burn_captions: bool = True,
    loudnorm: bool = True,
    cues: list | None = None,
) -> dict:
    preset = PLATFORM_PRESETS.get(platform)
    if preset is None:
        raise ValueError(f"Unknown platform preset: {platform}")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    w, h = preset["width"], preset["height"]
    vf = _filter_graph(w, h, preset["crop"])
    warnings: list[str] = []

    burned = False
    if burn_captions and cues:
        if ffmpeg_has("subtitles"):
            from app.pipeline.captions import to_ass
            ass_path = WORK_DIR / f"{out_path.stem}.ass"
            ass_path.write_text(
                to_ass(cues, w, h, preset["caption_chars"]), encoding="utf-8"
            )
            ass_escaped = str(ass_path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
            vf = f"{vf},subtitles='{ass_escaped}'"
            burned = True
        else:
            warnings.append("ffmpeg build has no libass; captions exported as sidecar .srt only.")
    elif burn_captions and srt_path:
        warnings.append("No cues supplied; captions exported as sidecar .srt only.")

    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
           "-ss", f"{max(0.0, start):.3f}", "-i", str(src)]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    if loudnorm:
        cmd += ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]
    cmd += ["-filter_complex" if "[0:v]" in vf else "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", str(out_path)]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"ffmpeg export failed for {platform}: {proc.stderr[-500:]}")

    return {
        "platform": platform,
        "label": preset["label"],
        "path": str(out_path),
        "width": w,
        "height": h,
        "size_mb": round(out_path.stat().st_size / 1_048_576, 2),
        "captions_burned": burned,
        "warnings": warnings,
    }


def extract_poster(src: str | Path, t: float, out_path: str | Path,
                   width: int = 1280, height: int = 720) -> dict:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
          f"crop={width}:{height}")
    proc = subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{max(0.0, t):.3f}", "-i", str(src), "-frames:v", "1",
         "-vf", vf, str(out_path)],
        capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"Poster extraction failed: {proc.stderr[-300:]}")
    return {"path": str(out_path)}
