"""The orchestrator: one function that runs the whole agent chain.

    probe -> audio intelligence -> transcript -> hook planner
          -> thumbnail render + score -> captions -> multi-format export
          -> engagement prior -> persist + report

Called by the API, by the CLI demo, and by the tests. Keeping it in one place
means the demo video and the test suite exercise exactly the same code path.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.config import EXPORT_DIR, PLATFORM_PRESETS, THUMB_DIR, WORK_DIR
from app.db import insert_export, insert_variant, insert_video, init_db
from app.pipeline import analytics, audio, captions, formats, hooks, media, thumbs


def run_pipeline(
    video_path: str | Path,
    *,
    video_id: str | None = None,
    platforms: list[str] | None = None,
    n_variants: int = 4,
    engine: str = "offline",
    clip_seconds: float = 12.0,
    burn_captions: bool = True,
    verbose: bool = False,
) -> dict:
    video_path = Path(video_path)
    video_id = video_id or f"{video_path.stem[:20]}-{uuid.uuid4().hex[:8]}"
    platforms = platforms or ["youtube_shorts"]
    platforms = [p for p in platforms if p in PLATFORM_PRESETS] or ["youtube_shorts"]
    primary = platforms[0]
    preset = PLATFORM_PRESETS[primary]

    def log(msg: str) -> None:
        if verbose:
            print(f"  [hookforge] {msg}")

    init_db()
    log(f"probing {video_path.name}")
    meta = media.probe(video_path)
    duration = float(meta["duration"]) or 1.0

    log("audio intelligence")
    wave, sr = media.extract_audio(video_path)
    tl = audio.timeline(wave, sr)
    windows = audio.hook_windows(wave, sr)
    cuts = media.scene_cuts(video_path)

    log("transcript")
    transcript, transcript_source = captions.transcribe(video_path)

    log("hook planner")
    variants, plan_meta = hooks.plan_hooks(
        duration=duration, windows=windows, transcript=transcript,
        filename_stem=video_path.stem, n=n_variants, engine=engine,
        platform=primary, clip_seconds=clip_seconds,
    )

    insert_video(video_id, video_path.name, str(video_path), meta, {
        "timeline": tl, "hook_windows": windows, "cuts": cuts,
        "transcript": transcript, "transcript_source": transcript_source,
        "plan": plan_meta,
    })

    out_variants: list[dict] = []
    for v in variants:
        log(f"variant {v.variant_id}: thumb + captions + {len(platforms)} export(s)")
        nearest = min(windows, key=lambda w: abs(w["start"] - v.start)) if windows else {"energy": 0.5}
        v.energy_match = audio.energy_match(nearest, tl)

        # --- thumbnail ---------------------------------------------------
        frame = media.extract_frame(video_path, v.start + min(0.6, v.duration / 3))
        thumb_path = THUMB_DIR / video_id / f"{v.variant_id}_{v.style}.jpg"
        rendered = thumbs.render_variant(
            frame, v.text, v.style, preset["width"], preset["height"], thumb_path,
            strategy=preset.get("thumb_strategy", "cover"),
        )
        thumb_scores = thumbs.score_thumbnail(thumb_path, rendered["text_box"])

        # --- poster (16:9, for the report) -------------------------------
        poster_path = THUMB_DIR / video_id / f"{v.variant_id}_poster.jpg"
        try:
            formats.extract_poster(video_path, v.start + 0.6, poster_path)
        except Exception:
            poster_path = thumb_path

        # --- captions ----------------------------------------------------
        cues = captions.build_cues(
            transcript, v.start, v.duration,
            max_chars=preset["caption_chars"], max_lines=preset["caption_lines"],
            speech_timeline=tl, video_duration=duration,
        )
        srt_path = WORK_DIR / f"{v.variant_id}.srt"
        srt_path.write_text(captions.to_srt(cues), encoding="utf-8")
        vtt_path = WORK_DIR / f"{v.variant_id}.vtt"
        vtt_path.write_text(captions.to_vtt(cues), encoding="utf-8")

        # --- exports -----------------------------------------------------
        exports: list[dict] = []
        for platform in platforms:
            ext = PLATFORM_PRESETS[platform]
            out = EXPORT_DIR / video_id / f"{v.variant_id}_{platform}.mp4"
            try:
                res = formats.export_clip(
                    video_path, out, platform=platform, start=v.start,
                    duration=v.duration, srt_path=srt_path, burn_captions=burn_captions,
                    cues=cues,
                )
                res["download_url"] = f"/media/exports/{video_id}/{out.name}"
                insert_export(v.variant_id, platform, str(out), res)
                exports.append(res)
            except Exception as exc:  # one bad render must not kill the run
                exports.append({"platform": platform, "label": ext["label"],
                                "error": str(exc)[:300]})

        prediction = analytics.predict(
            thumb_score=thumb_scores["score"], energy_match=v.energy_match,
            copy_strength=v.copy_strength, duration=v.duration, platform=primary,
        )

        record = v.to_dict()
        record.update({
            "thumb_path": str(thumb_path),
            "thumb_url": f"/media/thumbs/{video_id}/{thumb_path.name}",
            "poster_path": str(poster_path),
            "thumbnail_score": thumb_scores,
            "caption_count": len(cues),
            "caption_wps": captions.words_per_second(cues),
            "caption_files": {"srt": str(srt_path), "vtt": str(vtt_path)},
            "caption_preview": [c.text for c in cues[:4]],
            "exports": exports,
            "prediction": prediction,
            "energy_match": v.energy_match,
        })
        out_variants.append(record)

    # rank before persisting so the stored payload carries its rank
    ranked = analytics.rank(out_variants)
    for record in ranked:
        insert_variant(video_id, record)

    report = {
        "video_id": video_id,
        "filename": video_path.name,
        "meta": meta,
        "analysis": {
            "energy_timeline": tl,
            "hook_windows": windows,
            "scene_cuts": cuts,
            "transcript_source": transcript_source,
            "transcript_preview": (transcript or "")[:600] or None,
            "plan": plan_meta,
        },
        "platforms": platforms,
        "variants": ranked,
        "recommendation": _recommendation(ranked),
        "disclaimer": analytics.PRIOR_NOTE,
    }

    report_path = EXPORT_DIR / video_id / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    report["report_url"] = f"/media/exports/{video_id}/report.json"
    log("done")
    return report


def _recommendation(ranked: list[dict]) -> dict:
    if not ranked:
        return {"winner": None, "why": "No variants were produced."}
    top = ranked[0]
    return {
        "winner": top["variant_id"],
        "hook_text": top["text"],
        "archetype": top["archetype"],
        "why": (
            f"Highest predicted watch-through ({top['prediction']['predicted_watch_through']:.1%}). "
            f"Thumbnail scored {top['thumbnail_score']['score']}/100 "
            f"({', '.join(top['thumbnail_score']['reasons'][:2]) or 'balanced composition'}), "
            f"and the hook window sits at {top['energy_match']:.0%} of the video's average audio energy."
        ),
        "next_step": "Ship it, then upload the platform CSV to this video to replace the prior with measured lift.",
    }
