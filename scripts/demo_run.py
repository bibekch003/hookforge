"""End-to-end CLI run - the same code path the API uses, no server needed.

    python scripts/demo_run.py                       # bundled sample clip
    python scripts/demo_run.py path/to/take.mp4      # your own take
    python scripts/demo_run.py take.mp4 --platforms youtube_shorts,tiktok --variants 4
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.runner import run_pipeline  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the full Hookforge agent chain.")
    ap.add_argument("video", nargs="?", default=str(ROOT / "samples" / "sample_creator_clip.mp4"))
    ap.add_argument("--platforms", default="youtube_shorts")
    ap.add_argument("--variants", type=int, default=4)
    ap.add_argument("--clip", type=float, default=10.0, help="hook clip length in seconds")
    ap.add_argument("--engine", default="offline", choices=["offline", "llm", "auto"])
    ap.add_argument("--no-burn", action="store_true", help="export captions as sidecar only")
    args = ap.parse_args()

    video = Path(args.video)
    if not video.exists():
        print(f"missing video: {video}\nGenerate the sample first: python scripts/make_sample_assets.py")
        return 2

    print(f"\nHookforge · {video.name}")
    print("-" * 78)
    report = run_pipeline(
        video,
        platforms=[p.strip() for p in args.platforms.split(",") if p.strip()],
        n_variants=args.variants,
        engine=args.engine,
        clip_seconds=args.clip,
        burn_captions=not args.no_burn,
        verbose=True,
    )

    m = report["meta"]
    print("-" * 78)
    print(f"source      {m['width']}x{m['height']} @ {m['fps']} fps · {m['duration']}s · "
          f"audio={m['has_audio']}")
    print(f"transcript  {report['analysis']['transcript_source']} "
          f"({(report['analysis']['transcript_preview'] or '')[:70]}…)")
    print(f"engine      {report['analysis']['plan']['engine_used']} · topic "
          f"“{report['analysis']['plan']['topic']}”")
    starts = ", ".join(f"{w['start']}s" for w in report["analysis"]["hook_windows"][:5])
    print(f"hook windows {starts}")

    print("\nRANKED VARIANTS")
    hdr = f"{'#':<3}{'archetype':<16}{'thumb':>6}{'WT':>8}{'CTR':>8}  hook"
    print(hdr)
    print("-" * 78)
    for v in report["variants"]:
        p = v["prediction"]
        print(f"{v['rank']:<3}{v['archetype']:<16}{v['thumbnail_score']['score']:>6}"
              f"{p['predicted_watch_through'] * 100:>7.1f}%"
              f"{p['predicted_thumb_ctr'] * 100:>7.1f}%  {v['text'][:46]}")

    print("\nOUTPUTS")
    for v in report["variants"]:
        print(f"  {v['variant_id']}  thumb={Path(v['thumb_path']).name}  captions={v['caption_count']}")
        for e in v["exports"]:
            if "error" in e:
                print(f"      {e['platform']}: FAILED {e['error'][:80]}")
            else:
                print(f"      {e['platform']:<18} {e['width']}x{e['height']} "
                      f"{e['size_mb']}MB  {e['path']}")

    rec = report["recommendation"]
    print(f"\nRECOMMENDATION  {rec['winner']}  “{rec['hook_text']}”")
    print(f"  {rec['why']}")
    print(f"\nreport: {report['report_path']}")
    print("\nNote:", report["disclaimer"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
