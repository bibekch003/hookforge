"""Fast, dependency-light test suite. Runs with pytest or plain python.

    pytest -q
    python tests/test_pipeline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.pipeline import analytics, audio, captions, hooks, media, thumbs  # noqa: E402

SAMPLE = ROOT / "samples" / "sample_creator_clip.mp4"


def test_probe_sample():
    assert SAMPLE.exists(), "run scripts/make_sample_assets.py first"
    meta = media.probe(SAMPLE)
    assert meta["width"] == 1280 and meta["height"] == 720
    assert 23.0 <= meta["duration"] <= 25.0
    assert meta["has_audio"] is True


def test_energy_envelope_detects_known_peaks():
    wave, sr = media.extract_audio(SAMPLE)
    assert sr == 16000 and len(wave) > sr * 20
    tl = audio.timeline(wave, sr)
    assert len(tl) >= 20
    by_t = {int(b["t"]): b["energy"] for b in tl}
    # the synth is deliberately loud in 4-8s and 16-20s, quiet elsewhere
    assert by_t[6] > by_t[1] + 0.2
    assert by_t[18] > by_t[11] + 0.2


def test_hook_windows_are_ranked_and_separated():
    wave, sr = media.extract_audio(SAMPLE)
    wins = audio.hook_windows(wave, sr, window_s=3.0, k=4)
    assert wins and all("start" in w for w in wins)
    scores = [w["score"] for w in wins]
    assert scores == sorted(scores, reverse=True)
    for i, a in enumerate(wins):
        for b in wins[i + 1:]:
            assert abs(a["start"] - b["start"]) >= 1.0


def test_copy_strength_rewards_strong_hooks():
    weak = "a video about editing"
    strong = "Stop doing this — it cost me 3 months. Watch before you post."
    assert hooks.copy_strength(strong) > hooks.copy_strength(weak)
    assert 0.0 <= hooks.copy_strength(weak) <= 1.0


def test_topic_extraction_skips_stopwords():
    topic = hooks.extract_topic("I spent three years editing my own videos", "fallback")
    assert topic and topic.split()[0] not in hooks.STOPWORDS


def test_offline_planner_is_deterministic_and_platform_bounded():
    wins = [{"start": 6.0, "energy": 0.9}, {"start": 18.0, "energy": 0.8}]
    a, meta = hooks.plan_hooks(duration=24.0, windows=wins, transcript=None,
                               filename_stem="take_01", n=3, engine="offline",
                               platform="youtube_shorts", clip_seconds=12.0)
    b, _ = hooks.plan_hooks(duration=24.0, windows=wins, transcript=None,
                            filename_stem="take_01", n=3, engine="offline",
                            platform="youtube_shorts", clip_seconds=12.0)
    assert meta["engine_used"] == "offline"
    assert [x.text for x in a] == [x.text for x in b]
    assert len({x.style for x in a}) >= 2
    for v in a:
        assert v.start < 24.0 and 4.0 <= v.duration <= 60.0


def test_thumbnail_render_and_score():
    frame = media.extract_frame(SAMPLE, 6.0)
    out = ROOT / "data" / "thumbs" / "_test.jpg"
    res = thumbs.render_variant(frame, "This cost me three years", "bold_lower",
                               1080, 1920, out)
    assert out.exists() and out.stat().st_size > 5000
    scores = thumbs.score_thumbnail(out, res["text_box"])
    assert 0.0 <= scores["score"] <= 100.0
    for key in ("contrast", "colorfulness", "legibility", "clutter", "reasons"):
        assert key in scores


def test_srt_is_well_formed():
    cues = captions.build_cues("one two three four five six seven eight nine ten",
                               0.0, 6.0, max_chars=20, max_lines=2)
    srt = captions.to_srt(cues)
    assert srt.startswith("1\n")
    assert "-->" in srt and ",000" in srt.splitlines()[1]
    for c in cues:
        assert c.end > c.start
        assert len(c.text) <= 40


def test_prediction_is_monotonic_in_thumbnail_score():
    low = analytics.predict(thumb_score=20, energy_match=0.5, copy_strength=0.4,
                            duration=12, platform="youtube_shorts")
    high = analytics.predict(thumb_score=90, energy_match=0.5, copy_strength=0.4,
                             duration=12, platform="youtube_shorts")
    assert high["predicted_watch_through"] > low["predicted_watch_through"]
    assert high["predicted_thumb_ctr"] > low["predicted_thumb_ctr"]
    assert 0.0 < high["predicted_watch_through"] <= 0.92


def test_telemetry_replaces_prior():
    variants = [{
        "variant_id": "v1-aaa", "duration": 10.0,
        "prediction": {"predicted_watch_through": 0.40},
    }, {
        "variant_id": "v2-bbb", "duration": 10.0,
        "prediction": {"predicted_watch_through": 0.55},
    }]
    csv_text = ("variant_id,platform,impressions,views,avg_watch_s,likes,comments,shares\n"
                "v1-aaa,youtube_shorts,1000,90,6.0,10,2,1\n"
                "v2-bbb,youtube_shorts,1000,50,2.0,3,0,0\n")
    res = analytics.ingest_telemetry(csv_text, variants)
    assert res["winner"] == "v1-aaa"
    assert res["rows"][0]["measured_watch_through"] == 0.6
    assert res["rows"][0]["watch_through_lift"] > 0


def test_full_pipeline_end_to_end():
    """The heavy one: real ffmpeg render through the whole chain."""
    from app.runner import run_pipeline
    report = run_pipeline(SAMPLE, platforms=["linkedin_square"], n_variants=2,
                          clip_seconds=5.0, burn_captions=False)
    assert len(report["variants"]) == 2
    top = report["variants"][0]
    assert top["rank"] == 1
    assert top["thumbnail_score"]["score"] > 0
    rendered = [e for e in top["exports"] if "error" not in e]
    assert rendered, "no export produced"
    assert Path(rendered[0]["path"]).exists()
    assert rendered[0]["width"] == 1080 and rendered[0]["height"] == 1080
    assert report["recommendation"]["winner"] == top["variant_id"]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
