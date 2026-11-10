"""Captions: transcript in, platform-legal SRT/VTT out.

The ASR layer is an adapter chain so the pipeline never hard-depends on a model
download: faster-whisper if installed, otherwise a sidecar transcript file next
to the video, otherwise nothing (captions are then skipped, not faked).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Cue:
    start: float
    end: float
    text: str


def _fmt(t: float, sep: str = ",") -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def words_per_second(cues: list[Cue]) -> float:
    """Readability check surfaced in the report."""
    if not cues:
        return 0.0
    span = max(0.1, cues[-1].end - cues[0].start)
    return round(sum(len(c.text.split()) for c in cues) / span, 2)


def to_srt(cues: list[Cue]) -> str:
    blocks = []
    for i, c in enumerate(cues, 1):
        blocks.append(f"{i}\n{_fmt(c.start)} --> {_fmt(c.end)}\n{c.text}\n")
    return "\n".join(blocks)


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


# libass lays SRT out on a 384x288 virtual canvas, which is why force_style
# FontSize values blow up on a 1080x1920 render. Writing a real ASS file with
# PlayResX/PlayResY set to the export resolution is the fix.
ASS_TEMPLATE = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,DejaVu Sans,{fs},&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,{outline},1,2,{ml},{mr},{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{events}"""


def wrap_ass(text: str, chars_per_line: int) -> str:
    """Word-wrap a cue and join with ASS hard line breaks (\\N).

    The cue text is already capped at chars_per_line * lines, but that cap counts
    characters, not rendered width - so the break has to be explicit or libass
    lets the line run off a 1080px frame.
    """
    lines: list[str] = []
    cur = ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if len(trial) <= chars_per_line or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return r"\N".join(lines)


def to_ass(cues: list[Cue], width: int, height: int,
           chars_per_line: int = 32) -> str:
    """ASS subtitle file sized for a specific render resolution.

    Font size is derived from the width and the platform's characters-per-line,
    so a 32-character Reels cue and a 42-character YouTube cue both fit.
    """
    fs = int(width / max(12, chars_per_line) / 0.58)
    outline = max(2, fs // 18)
    margin_v = int(height * 0.13)
    margin_h = int(width * 0.06)
    events = "\n".join(
        f"Dialogue: 0,{_ass_time(c.start)},{_ass_time(c.end)},Hook,,0,0,0,,"
        f"{wrap_ass(c.text, chars_per_line)}"
        for c in cues
    )
    return ASS_TEMPLATE.format(w=width, h=height, fs=fs, outline=outline,
                               ml=margin_h, mr=margin_h, mv=margin_v, events=events)


def to_vtt(cues: list[Cue]) -> str:
    blocks = ["WEBVTT\n"]
    for c in cues:
        blocks.append(f"{_fmt(c.start, '.')} --> {_fmt(c.end, '.')}\n{c.text}\n")
    return "\n".join(blocks)


# ---------------------------------------------------------------------------
# ASR adapters
# ---------------------------------------------------------------------------
def transcribe(video_path: str | Path) -> tuple[str | None, str]:
    """Return (transcript, source). source is 'faster-whisper' | 'sidecar' | 'none'."""
    video_path = Path(video_path)

    try:  # optional heavyweight path
        from faster_whisper import WhisperModel  # type: ignore
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(video_path), vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        if text:
            return text, "faster-whisper"
    except Exception:
        pass

    for ext in (".txt", ".srt", ".vtt"):
        sidecar = video_path.with_suffix(ext)
        if sidecar.exists():
            raw = sidecar.read_text(encoding="utf-8", errors="ignore")
            if ext == ".srt":
                raw = " ".join(
                    line for line in raw.splitlines()
                    if line.strip() and "-->" not in line and not line.strip().isdigit()
                )
            elif ext == ".vtt":
                raw = " ".join(
                    line for line in raw.splitlines()
                    if line.strip() and "-->" not in line and not line.startswith("WEBVTT")
                )
            return re.sub(r"\s+", " ", raw).strip(), "sidecar"

    return None, "none"


# ---------------------------------------------------------------------------
# cue building
# ---------------------------------------------------------------------------
def _slice_transcript(transcript: str, start: float, duration: float,
                      video_duration: float) -> str:
    """Take the part of the transcript that belongs to this clip window.

    Proportional alignment on character offsets. It is an approximation - real
    alignment needs word timestamps, which is what the faster-whisper adapter
    provides when it is installed - and it is labelled as such in the docs.
    """
    n = len(transcript)
    a = int(max(0.0, start / video_duration) * n)
    b = int(min(1.0, (start + duration) / video_duration) * n)
    if b <= a:
        b = min(n, a + max(1, int(n * 0.12)))
    seg = transcript[a:b]
    if a > 0 and not transcript[a - 1].isspace():
        seg = seg.split(" ", 1)[-1] if " " in seg else seg
    if b < n and not transcript[b].isspace():
        seg = seg.rsplit(" ", 1)[0] if " " in seg else seg
    return seg.strip()


def build_cues(transcript: str | None, start: float, duration: float,
               max_chars: int = 32, max_lines: int = 2,
               speech_timeline: list[dict] | None = None,
               video_duration: float | None = None) -> list[Cue]:
    """Chunk the transcript into platform-legal cues across the clip window.

    Timing is proportional to character length. The number of cues is bounded by
    a readable pace (~2.6 words/sec), so a 10s hook never gets a 40-cue wall.
    """
    if not transcript:
        return []
    if video_duration and video_duration > 0:
        sliced = _slice_transcript(transcript, start, duration, video_duration)
        if sliced:
            transcript = sliced
    # Word-boundary wrapping loses a few characters per line, so the chunk cap
    # sits below the raw max_chars * max_lines budget. Without this a "2 line"
    # cue wraps to 3 and breaks the platform contract.
    limit = max(12, int(max_chars * max_lines * 0.85))
    words = transcript.split()
    chunks: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if len(trial) <= limit:
            cur = trial
        else:
            if cur:
                chunks.append(cur)
            cur = w
    if cur:
        chunks.append(cur)

    # Re-split into cues sized for reading, not for line length: roughly one cue
    # every 2.5s, which is the range captions are actually comfortable at.
    words = transcript.split()
    if not words:
        return []
    n_cues = max(1, min(8, int(round(duration / 2.5))))
    per_cue = max(1, -(-len(words) // n_cues))  # ceil
    chunks = []
    cur: list[str] = []
    for w in words:
        trial = " ".join(cur + [w])
        if cur and (len(trial) > limit or len(cur) >= per_cue):
            chunks.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        chunks.append(" ".join(cur))
    chunks = chunks[:8]

    total_chars = sum(len(c) for c in chunks) or 1
    cues: list[Cue] = []
    t = start
    for c in chunks:
        span = duration * (len(c) / total_chars)
        cues.append(Cue(round(t, 3), round(t + span, 3), c))
        t += span
    return cues
