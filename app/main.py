"""FastAPI surface for Hookforge.

Routes
------
GET  /                          dashboard UI
GET  /api/health                liveness + capability probe
POST /api/analyze               upload a video, run the full pipeline
GET  /api/videos                recent runs
GET  /api/videos/{id}           one run with variants + exports
POST /api/videos/{id}/telemetry upload a platform CSV -> measured lift
GET  /api/demo                  run the pipeline on the bundled sample clip
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import (ALLOWED_EXT, EXPORT_DIR, MAX_UPLOAD_MB, PLATFORM_PRESETS,
                        ROOT, THUMB_DIR, UPLOAD_DIR, ffmpeg_bin, ffmpeg_has)
from app.db import get_video, init_db, latest_telemetry, list_variants, list_videos, save_telemetry
from app.pipeline import analytics
from app.runner import run_pipeline

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Hookforge", version=__version__,
              description="Agentic retention studio for solo creators.",
              lifespan=lifespan)

STATIC_DIR = ROOT / "app" / "static"
SAMPLES_DIR = ROOT / "samples"

app.mount("/media/thumbs", StaticFiles(directory=THUMB_DIR), name="thumbs")
app.mount("/media/exports", StaticFiles(directory=EXPORT_DIR), name="exports")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "ffmpeg": ffmpeg_bin(),
        "captions_burn_in": ffmpeg_has("subtitles"),
        "platforms": list(PLATFORM_PRESETS),
        "llm_adapter": bool(__import__("os").getenv("HOOKFORGE_LLM_API_KEY")
                            or __import__("os").getenv("OPENAI_API_KEY")),
        "max_upload_mb": MAX_UPLOAD_MB,
    }


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    platforms: str = Form("youtube_shorts"),
    n_variants: int = Form(4),
    engine: str = Form("offline"),
    clip_seconds: float = Form(12.0),
    burn_captions: bool = Form(True),
    transcript: str = Form(""),
) -> JSONResponse:
    suffix = Path(file.filename or "clip.mp4").suffix.lower()
    if suffix not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type {suffix}. Allowed: {sorted(ALLOWED_EXT)}")

    dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:10]}{suffix}"
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    size_mb = dest.stat().st_size / 1_048_576
    if size_mb > MAX_UPLOAD_MB:
        dest.unlink(missing_ok=True)
        raise HTTPException(413, f"File is {size_mb:.0f} MB; limit is {MAX_UPLOAD_MB} MB.")

    # A transcript pasted into the dashboard is written as the sidecar the pipeline
    # already knows how to read. Without this the field is silently dropped and the
    # hook planner falls back to subject-free copy.
    if transcript.strip():
        dest.with_suffix(".txt").write_text(transcript.strip(), encoding="utf-8")

    plist = [p.strip() for p in platforms.split(",") if p.strip()]
    try:
        report = run_pipeline(
            dest, platforms=plist, n_variants=max(1, min(8, n_variants)),
            engine=engine, clip_seconds=max(4.0, min(30.0, clip_seconds)),
            burn_captions=burn_captions,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Pipeline failed: {exc}") from exc
    return JSONResponse(report)


@app.post("/api/analyze-with-transcript")
async def analyze_with_transcript(
    file: UploadFile = File(...),
    transcript: str = Form(""),
    platforms: str = Form("youtube_shorts"),
    n_variants: int = Form(4),
    engine: str = Form("offline"),
    clip_seconds: float = Form(12.0),
) -> JSONResponse:
    """Same pipeline, but with a transcript supplied by the user (no ASR needed)."""
    suffix = Path(file.filename or "clip.mp4").suffix.lower()
    if suffix not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type {suffix}")
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:10]}{suffix}"
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    if transcript.strip():
        dest.with_suffix(".txt").write_text(transcript.strip(), encoding="utf-8")
    plist = [p.strip() for p in platforms.split(",") if p.strip()]
    report = run_pipeline(dest, platforms=plist, n_variants=max(1, min(8, n_variants)),
                          engine=engine, clip_seconds=max(4.0, min(30.0, clip_seconds)))
    return JSONResponse(report)


@app.get("/api/videos")
def videos() -> dict:
    return {"videos": list_videos()}


@app.get("/api/videos/{video_id}")
def video_detail(video_id: str) -> dict:
    video = get_video(video_id)
    if not video:
        raise HTTPException(404, "Unknown video_id")
    return {"video": video, "variants": list_variants(video_id),
            "telemetry": latest_telemetry(video_id)}


@app.post("/api/videos/{video_id}/telemetry")
async def telemetry(video_id: str, file: UploadFile = File(...)) -> dict:
    video = get_video(video_id)
    if not video:
        raise HTTPException(404, "Unknown video_id")
    variants = list_variants(video_id)
    text = (await file.read()).decode("utf-8", errors="ignore")
    try:
        result = analytics.ingest_telemetry(text, variants)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    save_telemetry(video_id, result)
    return result


@app.get("/api/demo")
def demo(
    platforms: str = "youtube_shorts",
    n_variants: int = 3,
    clip_seconds: float = 8.0,
    engine: str = "offline",
) -> JSONResponse:
    sample = SAMPLES_DIR / "sample_creator_clip.mp4"
    if not sample.exists():
        raise HTTPException(
            404, "Sample clip missing. Run `python scripts/make_sample_assets.py` first."
        )
    plist = [p.strip() for p in platforms.split(",") if p.strip()]
    report = run_pipeline(sample, platforms=plist, n_variants=max(1, min(6, n_variants)),
                          engine=engine, clip_seconds=clip_seconds, burn_captions=True)
    return JSONResponse(report)
