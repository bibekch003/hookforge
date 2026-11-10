"""Engagement analytics.

Two clearly separated layers, and the difference matters for evaluation:

1. ``predict`` - a *transparent prior*. A hand-set linear model over signals we
   actually measure (thumbnail score, hook energy match, copy strength,
   duration, platform). It exists so a creator gets a ranking before any
   impressions exist. It is a prior, not a measurement, and it is labelled as
   such everywhere it surfaces.
2. ``ingest_telemetry`` - real numbers from the platform (impressions, views,
   average watch time, likes, comments, shares). Once these exist they replace
   the prior, and the app reports measured lift instead of predicted lift.

Nothing here claims to predict YouTube's algorithm. It ranks your own variants
against each other using the signals that the literature and creator practice
agree on.
"""
from __future__ import annotations

import csv
import io

from app.config import PLATFORM_PRIOR

PRIOR_NOTE = (
    "Predicted values are a documented prior over measured signals "
    "(thumbnail score, hook energy match, copy strength, duration, platform). "
    "Upload real telemetry to replace them with measurements."
)


def predict(*, thumb_score: float, energy_match: float, copy_strength: float,
            duration: float, platform: str) -> dict:
    platform_bonus = PLATFORM_PRIOR.get(platform, 0.04)
    dur = max(1.0, float(duration))
    duration_penalty = min(0.08, max(0.0, (dur - 20.0) / 20.0) * 0.06)

    watch_through = (0.22
                     + 0.30 * (thumb_score / 100.0)
                     + 0.18 * float(energy_match)
                     + 0.16 * float(copy_strength)
                     + platform_bonus
                     - duration_penalty)
    watch_through = round(max(0.05, min(0.92, watch_through)), 4)

    thumb_ctr = 0.035 + 0.055 * (thumb_score / 100.0) + 0.020 * float(copy_strength)
    thumb_ctr = round(max(0.01, min(0.18, thumb_ctr)), 4)

    engagement = (0.018 + 0.050 * float(copy_strength) + 0.020 * (1.0 - min(1.0, dur / 60.0)))
    engagement = round(max(0.005, min(0.20, engagement)), 4)

    return {
        "predicted_watch_through": watch_through,
        "predicted_thumb_ctr": thumb_ctr,
        "predicted_engagement_rate": engagement,
        "inputs": {
            "thumb_score": round(float(thumb_score), 1),
            "energy_match": round(float(energy_match), 3),
            "copy_strength": round(float(copy_strength), 3),
            "duration_s": round(dur, 1),
            "platform": platform,
            "platform_bonus": platform_bonus,
            "duration_penalty": round(duration_penalty, 4),
        },
        "note": PRIOR_NOTE,
    }


def rank(variants: list[dict]) -> list[dict]:
    """Sort variants by predicted watch-through, best first, with a rank field."""
    ordered = sorted(variants, key=lambda v: v["prediction"]["predicted_watch_through"], reverse=True)
    for i, v in enumerate(ordered, 1):
        v["rank"] = i
    return ordered


TELEMETRY_COLUMNS = [
    "variant_id", "platform", "impressions", "views",
    "avg_watch_s", "likes", "comments", "shares",
]


def ingest_telemetry(csv_text: str, variants: list[dict]) -> dict:
    """Parse a platform export and compute measured metrics per variant."""
    by_id = {v["variant_id"]: v for v in variants}
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    missing = [c for c in TELEMETRY_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"CSV missing columns: {', '.join(missing)}")

    rows: list[dict] = []
    for raw in reader:
        vid = (raw.get("variant_id") or "").strip()
        if vid not in by_id:
            continue
        v = by_id[vid]
        imp = _num(raw.get("impressions"))
        views = _num(raw.get("views"))
        watch = _num(raw.get("avg_watch_s"))
        likes = _num(raw.get("likes"))
        comments = _num(raw.get("comments"))
        shares = _num(raw.get("shares"))
        duration = float(v.get("duration") or 1.0) or 1.0
        rows.append({
            "variant_id": vid,
            "platform": raw.get("platform") or "",
            "impressions": int(imp),
            "views": int(views),
            "measured_ctr": round(views / imp, 4) if imp else 0.0,
            "measured_watch_through": round(min(1.0, watch / duration), 4) if duration else 0.0,
            "measured_engagement_rate": round((likes + comments + shares) / views, 4) if views else 0.0,
            "predicted_watch_through": v["prediction"]["predicted_watch_through"],
        })

    for r in rows:
        p = r["predicted_watch_through"] or 1e-6
        r["watch_through_lift"] = round(r["measured_watch_through"] / p - 1.0, 4)

    rows.sort(key=lambda r: r["measured_watch_through"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    return {
        "rows": rows,
        "winner": rows[0]["variant_id"] if rows else None,
        "matched": len(rows),
        "unmatched": max(0, len(by_id) - len(rows)),
        "note": "Measured values from uploaded telemetry; these supersede the prior.",
    }


def _num(value) -> float:
    try:
        return float(str(value).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0
