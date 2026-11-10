"""API smoke test - exercises the real routes in-process, no server to babysit.

    python scripts/smoke_api.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
from httpx import ASGITransport  # noqa: E402

from app.main import app  # noqa: E402

SAMPLE = ROOT / "samples" / "sample_creator_clip.mp4"


def check(label: str, cond: bool, extra: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'}  {label}{'  ' + extra if extra else ''}")
    if not cond:
        raise SystemExit(1)


async def main() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=280.0) as c:
        r = await c.get("/api/health")
        h = r.json()
        check("GET /api/health", r.status_code == 200 and h["status"] == "ok",
              f"captions_burn_in={h['captions_burn_in']}")

        r = await c.get("/")
        check("GET / (dashboard html)", r.status_code == 200 and "Hookforge" in r.text)

        r = await c.get("/api/demo", params={"platforms": "youtube_shorts",
                                            "n_variants": 2, "clip_seconds": 6})
        rep = r.json()
        check("GET /api/demo runs the chain", r.status_code == 200 and len(rep["variants"]) == 2)
        vid = rep["video_id"]
        top = rep["variants"][0]
        check("variants are ranked", top["rank"] == 1)
        check("thumbnail file served", (await c.get(top["thumb_url"])).status_code == 200)

        rendered = [e for e in top["exports"] if "download_url" in e]
        check("clip export served", bool(rendered) and
              (await c.get(rendered[0]["download_url"])).status_code == 200,
              f"{rendered[0]['size_mb']}MB" if rendered else "none")

        r = await c.get(f"/api/videos/{vid}")
        check("GET /api/videos/{id}", r.status_code == 200 and len(r.json()["variants"]) == 2)

        r = await c.get("/api/videos")
        check("GET /api/videos", r.status_code == 200 and len(r.json()["videos"]) >= 1)

        csv_text = ("variant_id,platform,impressions,views,avg_watch_s,likes,comments,shares\n"
                    + "".join(f"{v['variant_id']},youtube_shorts,5000,{600 - i * 150},"
                              f"{4.5 - i},40,5,2\n"
                              for i, v in enumerate(rep["variants"])))
        r = await c.post(f"/api/videos/{vid}/telemetry",
                         files={"file": ("t.csv", csv_text.encode(), "text/csv")})
        t = r.json()
        check("POST telemetry replaces the prior", r.status_code == 200 and t["matched"] == 2,
              f"winner={t['winner']}")

        if SAMPLE.exists():
            with SAMPLE.open("rb") as fh:
                r = await c.post("/api/analyze",
                                 files={"file": ("take.mp4", fh, "video/mp4")},
                                 data={"platforms": "linkedin_square", "n_variants": "1",
                                       "clip_seconds": "5"})
            check("POST /api/analyze (upload)", r.status_code == 200 and r.json()["variants"],
                  r.json().get("detail", "")[:80] if r.status_code != 200 else "")

    print("\nall API checks passed")


if __name__ == "__main__":
    asyncio.run(main())
