"""Audio intelligence: energy envelope, speech band activity, hook windows.

Everything here is plain DSP on the decoded waveform, so it runs offline and
gives the same answer on every machine.
"""
from __future__ import annotations

import numpy as np


def rms_envelope(audio: np.ndarray, sr: int, hop_s: float = 0.05) -> tuple[np.ndarray, float]:
    hop = max(1, int(sr * hop_s))
    n = len(audio) // hop
    if n == 0:
        return np.zeros(1, dtype=np.float32), hop_s
    trimmed = audio[: n * hop].reshape(n, hop)
    env = np.sqrt(np.mean(trimmed.astype(np.float32) ** 2, axis=1))
    return env.astype(np.float32), hop_s


def speech_band_ratio(audio: np.ndarray, sr: int, start: float, end: float) -> float:
    """Share of energy in 300-3400 Hz (the intelligible speech band)."""
    a = int(max(0, start) * sr)
    b = int(min(len(audio) / sr, end) * sr)
    seg = audio[a:b]
    if len(seg) < 256:
        return 0.0
    seg = seg * np.hanning(len(seg))
    spec = np.abs(np.fft.rfft(seg)) ** 2
    freqs = np.fft.rfftfreq(len(seg), 1.0 / sr)
    total = spec.sum() or 1.0
    band = spec[(freqs >= 300) & (freqs <= 3400)].sum()
    return float(band / total)


def timeline(audio: np.ndarray, sr: int, bucket_s: float = 1.0) -> list[dict]:
    """Per-bucket energy + speech-band activity, normalised 0-1."""
    env, hop = rms_envelope(audio, sr)
    per_bucket = max(1, int(round(bucket_s / hop)))
    out: list[dict] = []
    peak = float(env.max()) if len(env) else 0.0
    for i in range(0, len(env), per_bucket):
        chunk = env[i: i + per_bucket]
        t = round(i * hop, 2)
        e = float(chunk.mean()) if len(chunk) else 0.0
        out.append({
            "t": t,
            "energy": round(min(1.0, e / peak) if peak else 0.0, 4),
            "speech": round(speech_band_ratio(audio, sr, t, t + bucket_s), 4),
        })
    return out


def hook_windows(audio: np.ndarray, sr: int, window_s: float = 3.0, k: int = 6) -> list[dict]:
    """Rank candidate opening windows by energy x novelty.

    The insight: viewers decide in the first ~3 seconds, so we surface the
    densest, most speech-like 3s windows as hook candidates instead of always
    using t=0.
    """
    env, hop = rms_envelope(audio, sr)
    if len(env) == 0:
        return [{"start": 0.0, "score": 0.0, "energy": 0.0}]
    win = max(1, int(window_s / hop))
    total = len(env)
    mean_env = float(env.mean()) or 1e-6
    candidates: list[dict] = []
    stride = max(1, win // 3)
    for start in range(0, max(1, total - win + 1), stride):
        chunk = env[start:start + win]
        e = float(chunk.mean())
        # novelty: how much the window stands out from the rolling neighbourhood
        lo = max(0, start - win)
        hi = min(total, start + 2 * win)
        neighbourhood = float(env[lo:hi].mean()) or 1e-6
        novelty = e / neighbourhood
        score = (e / mean_env) * 0.65 + novelty * 0.35
        t0 = start * hop
        candidates.append({
            "start": round(t0, 2),
            "energy": round(min(1.0, e / (float(env.max()) or 1e-6)), 4),
            "speech": round(speech_band_ratio(audio, sr, t0, t0 + window_s), 4),
            "score": round(float(score), 4),
        })
    candidates.sort(key=lambda c: c["score"], reverse=True)
    # keep windows that are not on top of each other
    picked: list[dict] = []
    for c in candidates:
        if all(abs(c["start"] - p["start"]) >= window_s * 0.75 for p in picked):
            picked.append(c)
        if len(picked) >= k:
            break
    return picked


def energy_match(hook: dict, tl: list[dict]) -> float:
    """How much hotter the hook window is than the video's own average."""
    if not tl:
        return 0.5
    avg = float(np.mean([b["energy"] for b in tl])) or 1e-6
    return round(float(min(1.0, hook.get("energy", 0.0) / avg)), 4)
