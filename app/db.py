"""SQLite persistence. Small on purpose: one file, no ORM, easy to inspect."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id          TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    path        TEXT NOT NULL,
    meta_json   TEXT NOT NULL,
    analysis_json TEXT,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS variants (
    id          TEXT PRIMARY KEY,
    video_id    TEXT NOT NULL,
    archetype   TEXT,
    hook_text   TEXT,
    start_s     REAL,
    duration_s  REAL,
    style       TEXT,
    engine      TEXT,
    thumb_path  TEXT,
    poster_path TEXT,
    scores_json TEXT,
    prediction_json TEXT,
    payload_json TEXT,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (video_id) REFERENCES videos(id)
);
CREATE TABLE IF NOT EXISTS exports (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    variant_id TEXT NOT NULL,
    platform   TEXT NOT NULL,
    path       TEXT NOT NULL,
    meta_json  TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS telemetry (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id   TEXT NOT NULL,
    payload    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_variants_video ON variants(video_id);
CREATE INDEX IF NOT EXISTS idx_exports_variant ON exports(variant_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def insert_video(video_id: str, filename: str, path: str, meta: dict, analysis: dict | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO videos (id, filename, path, meta_json, analysis_json, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (video_id, filename, path, json.dumps(meta),
             json.dumps(analysis) if analysis is not None else None, now()),
        )


def insert_variant(video_id: str, v: dict) -> None:
    """Store the whole variant document alongside the queryable columns.

    The structured columns are for SQL and reporting; payload_json is the
    contract the API and dashboard read, so the two can never drift apart.
    """
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO variants (id, video_id, archetype, hook_text, start_s, duration_s,"
            " style, engine, thumb_path, poster_path, scores_json, prediction_json, payload_json,"
            " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (v["variant_id"], video_id, v.get("archetype"), v.get("text"), v.get("start"),
             v.get("duration"), v.get("style"), v.get("engine"), v.get("thumb_path"),
             v.get("poster_path"), json.dumps(v.get("thumbnail_score")),
             json.dumps(v.get("prediction")), json.dumps(v), now()),
        )


def insert_export(variant_id: str, platform: str, path: str, meta: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO exports (variant_id, platform, path, meta_json, created_at) VALUES (?,?,?,?,?)",
            (variant_id, platform, path, json.dumps(meta), now()),
        )


def get_video(video_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["meta"] = json.loads(d.pop("meta_json") or "{}")
    d["analysis"] = json.loads(d.pop("analysis_json") or "{}")
    return d


def list_videos(limit: int = 25) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, filename, meta_json, created_at FROM videos ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["meta"] = json.loads(d.pop("meta_json") or "{}")
        out.append(d)
    return out


def list_variants(video_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM variants WHERE video_id=? ORDER BY id", (video_id,)
        ).fetchall()
        exports = conn.execute(
            "SELECT variant_id, platform, path FROM exports WHERE variant_id IN"
            " (SELECT id FROM variants WHERE video_id=?)", (video_id,)
        ).fetchall()
    by_variant: dict[str, list] = {}
    for e in exports:
        by_variant.setdefault(e["variant_id"], []).append({"platform": e["platform"], "path": e["path"]})
    out = []
    for r in rows:
        d = dict(r)
        payload = json.loads(d.pop("payload_json", None) or "null")
        if not isinstance(payload, dict):
            # older row without a payload: rebuild the minimum the API promises
            payload = {
                "variant_id": d["id"],
                "video_id": d["video_id"],
                "archetype": d.get("archetype"),
                "text": d.get("hook_text"),
                "start": d.get("start_s"),
                "duration": d.get("duration_s"),
                "style": d.get("style"),
                "engine": d.get("engine"),
                "thumb_path": d.get("thumb_path"),
                "thumbnail_score": json.loads(d.pop("scores_json", None) or "null"),
                "prediction": json.loads(d.pop("prediction_json", None) or "null"),
            }
        payload["variant_id"] = payload.get("variant_id") or d["id"]
        payload["exports"] = by_variant.get(d["id"], [])
        out.append(payload)
    return out


def save_telemetry(video_id: str, payload: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO telemetry (video_id, payload, created_at) VALUES (?,?,?)",
            (video_id, json.dumps(payload), now()),
        )


def latest_telemetry(video_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT payload FROM telemetry WHERE video_id=? ORDER BY id DESC LIMIT 1", (video_id,)
        ).fetchone()
    return json.loads(row["payload"]) if row else None
