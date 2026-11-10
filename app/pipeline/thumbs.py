"""Thumbnail rendering + computer-vision scoring.

Rendering is Pillow. Scoring is OpenCV and is deliberately explainable: five
named sub-scores with fixed weights, so a creator can see *why* variant 3 beat
variant 1 instead of trusting a black box.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

FACE_CASCADE = None
CASCADE_AVAILABLE = hasattr(cv2, "CascadeClassifier")

STYLE_PRESETS = {
    "bold_lower": {"scrim": 0.40, "position": "lower", "accent": (255, 61, 61), "fg": (255, 255, 255)},
    "split_band": {"scrim": 0.34, "position": "middle", "accent": (61, 220, 151), "fg": (12, 14, 18)},
    "top_strip": {"scrim": 0.30, "position": "top", "accent": (255, 214, 61), "fg": (255, 255, 255)},
}


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def _font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    try:  # Pillow >= 10 ships a scalable default
        return ImageFont.load_default(size=size)
    except Exception:  # pragma: no cover
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit_text(draw, text: str, box_w: int, box_h: int, start: int) -> tuple[list[str], ImageFont.FreeTypeFont]:
    size = start
    while size >= 18:
        font = _font(size)
        lines = _wrap(draw, text, font, box_w)
        line_h = int(size * 1.18)
        if len(lines) * line_h <= box_h:
            return lines, font
        size -= 4
    font = _font(18)
    return _wrap(draw, text, font, box_w)[:3], font


def _cover(img: Image.Image, width: int, height: int, bias: float = 0.35) -> Image.Image:
    """Scale to fill the target box, cropping the overflow (face-biased upward)."""
    sw, sh = img.size
    target_ar, src_ar = width / height, sw / sh
    if src_ar > target_ar:
        new_w = int(sh * target_ar)
        x0 = (sw - new_w) // 2
        img = img.crop((x0, 0, x0 + new_w, sh))
    else:
        new_h = int(sw / target_ar)
        y0 = max(0, int((sh - new_h) * bias))
        img = img.crop((0, y0, sw, y0 + new_h))
    return img.resize((width, height), Image.LANCZOS)


def render_variant(frame_bgr: np.ndarray, text: str, style: str,
                   width: int, height: int, out_path: Path,
                   strategy: str = "cover") -> dict:
    """Render one thumbnail. Returns the text box used (needed for legibility).

    ``cover`` fills the frame (best for 16:9 and 1:1). ``blur_pad`` keeps the
    whole source frame over a blurred, darkened fill - the standard move when a
    wide take has to survive a 9:16 crop without decapitating the subject.
    """
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["bold_lower"])
    src_img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))

    if strategy == "blur_pad":
        bg = _cover(src_img, width, height)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=max(8, width * 0.035)))
        bg = ImageEnhance.Brightness(bg).enhance(0.5)
        fg = src_img.copy()
        fg.thumbnail((width, height), Image.LANCZOS)
        img = bg.copy()
        img.paste(fg, ((width - fg.width) // 2, (height - fg.height) // 2))
    else:
        img = _cover(src_img, width, height)

    img = img.convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    margin = int(width * 0.07)
    box_w = width - 2 * margin
    box_h = int(height * 0.30)
    lines, font = _fit_text(draw, text, box_w, box_h, int(width * 0.115))
    line_h = int(font.size * 1.18)
    block_h = line_h * len(lines)

    if preset["position"] == "lower":
        band_top = height - block_h - int(height * 0.14)
    elif preset["position"] == "top":
        band_top = int(height * 0.10)
    else:
        band_top = (height - block_h) // 2

    band_top = max(int(height * 0.04), min(band_top, height - block_h - int(height * 0.04)))

    # scrim for legibility
    scrim_h = int(block_h * (1 + preset["scrim"]))
    scrim_top = max(0, band_top - int(block_h * 0.12))
    for i in range(scrim_h):
        y = scrim_top + i
        if y >= height:
            break
        alpha = int(190 * (1 - abs(i / max(1, scrim_h) - 0.5) * 1.15))
        draw.line([(0, y), (width, y)], fill=(0, 0, 0, max(0, alpha)))

    # accent bar
    draw.rectangle([margin, band_top - int(height * 0.035),
                    margin + int(width * 0.10), band_top - int(height * 0.020)],
                   fill=preset["accent"])

    y = band_top
    for line in lines:
        # drop shadow then fill
        draw.text((margin + 3, y + 3), line, font=font, fill=(0, 0, 0, 170))
        draw.text((margin, y), line, font=font, fill=preset["fg"] + (255,))
        y += line_h

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, "JPEG", quality=92)
    return {
        "path": str(out_path),
        "text_box": [margin, band_top, width - margin, band_top + block_h],
        "lines": len(lines),
        "font_size": font.size,
    }


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------
def _haar_faces(bgr: np.ndarray) -> tuple[float, int] | None:
    """Haar frontal-face detection. Returns None when the build lacks the API."""
    global FACE_CASCADE
    if not CASCADE_AVAILABLE:
        return None
    try:
        if FACE_CASCADE is None:
            path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            FACE_CASCADE = cv2.CascadeClassifier(str(path))
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (0, 0), fx=0.5, fy=0.5)
        faces = FACE_CASCADE.detectMultiScale(small, scaleFactor=1.08, minNeighbors=5,
                                             minSize=(28, 28))
    except Exception:
        return None
    if len(faces) == 0:
        return 0.0, 0
    h, w = gray.shape[:2]
    largest = max(faces, key=lambda f: f[2] * f[3])
    area = (largest[2] * 2) * (largest[3] * 2)
    return float(min(1.0, area / (w * h))), len(faces)


def _skin_salience(bgr: np.ndarray) -> tuple[float, int]:
    """Fallback subject-salience proxy: skin-tone coverage in the centre.

    Used when the OpenCV build has no cascade API (OpenCV >= 5 removed it).
    It answers the question the score actually needs - is there a human
    subject, and how much of the frame do they take - not "is this a face".
    """
    h, w = bgr.shape[:2]
    ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 180, 130))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1:
        return 0.0, 0
    areas = sorted(stats[1:, cv2.CC_STAT_AREA], reverse=True)
    blobs = [a for a in areas if a > (w * h) * 0.002]
    if not blobs:
        return 0.0, 0
    return float(min(1.0, sum(blobs[:3]) / (w * h))), len(blobs)


def _subject_salience(bgr: np.ndarray) -> tuple[float, int, str]:
    """(ratio, count, method) - face area when Haar exists, else skin salience."""
    haar = _haar_faces(bgr)
    if haar is not None:
        return haar[0], haar[1], "haar"
    ratio, count = _skin_salience(bgr)
    return ratio, count, "skin-salience"


def _colorfulness(bgr: np.ndarray) -> float:
    """Hasler-Suesstrunk colourfulness, normalised to 0-1."""
    b, g, r = cv2.split(bgr.astype(np.float32))
    rg, yb = r - g, 0.5 * (r + g) - b
    std = float(np.sqrt(rg.std() ** 2 + yb.std() ** 2))
    mean = float(np.sqrt(rg.mean() ** 2 + yb.mean() ** 2))
    return float(min(1.0, (std + 0.3 * mean) / 110.0))


def _legibility(bgr: np.ndarray, box: list[int]) -> float:
    """Local gradient energy under the text box: busy backgrounds kill text."""
    x0, y0, x1, y1 = [int(v) for v in box]
    h, w = bgr.shape[:2]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return 0.0
    crop = cv2.cvtColor(bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(crop, cv2.CV_32F, ksize=3)
    noise = float(np.mean(np.abs(lap)))
    # clean, low-noise plate under text = high legibility
    return float(max(0.0, min(1.0, 1.0 - noise / 60.0)))


def _subject_term(ratio: float, count: int, method: str) -> float:
    """Subject presence sub-score: detection first, size second.

    A blur-pad vertical render shrinks the subject into a letterboxed band, so its
    area ratio stays tiny even when a face is clearly detected. Scoring on the raw
    ratio alone therefore reported "face present" and "no clear human subject" in
    the same result. Detection now carries most of the weight and area scales the
    rest, which is also what the sub-score actually claims to measure.
    """
    if count <= 0:
        return 0.0
    if method == "haar":
        return float(min(1.0, 0.45 + 0.55 * min(1.0, ratio / 0.18)))
    return float(min(1.0, 0.35 + 0.65 * min(1.0, ratio / 0.30)))


def score_thumbnail(image_path: str | Path, text_box: list[int] | None = None) -> dict:
    bgr = cv2.imread(str(image_path))
    if bgr is None:
        raise ValueError(f"Could not read {image_path}")
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    contrast = float(min(1.0, gray.std() / 68.0))
    colour = _colorfulness(bgr)
    face, n_faces, face_method = _subject_salience(bgr)
    legib = _legibility(bgr, text_box) if text_box else 0.6
    edges = cv2.Canny(gray, 90, 190)
    clutter = float(min(1.0, edges.mean() / 42.0))

    subject = _subject_term(face, n_faces, face_method)

    score = (0.28 * contrast + 0.18 * colour + 0.26 * subject
             + 0.18 * legib + 0.10 * (1.0 - clutter))
    reasons = []
    if contrast > 0.55:
        reasons.append("strong tonal separation")
    if n_faces > 0:
        label = "face" if face_method == "haar" else "human subject"
        reasons.append(f"{label} present ({n_faces} region(s), {face:.1%} of frame)")
    else:
        reasons.append("no clear human subject detected in this frame")
    if colour > 0.5:
        reasons.append("saturated palette")
    if legib > 0.6:
        reasons.append("clean plate under the text")
    if clutter > 0.6:
        reasons.append("busy background may cost legibility")

    return {
        "score": round(score * 100, 1),
        "contrast": round(contrast, 3),
        "colorfulness": round(colour, 3),
        "face_ratio": round(face, 4),
        "faces": n_faces,
        "subject_method": face_method,
        "subject_score": round(subject, 3),
        "legibility": round(legib, 3),
        "clutter": round(clutter, 3),
        "reasons": reasons,
    }
