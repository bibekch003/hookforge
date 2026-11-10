"""Build the static showcase (GitHub Pages) from a real pipeline report.

    python scripts/build_showcase.py --report data/exports/<id>/report.json

Writes ./index.html plus ./showcase/assets/*, which is what GitHub Pages serves.
Everything on the page comes from the report, so the site can never claim numbers the
pipeline did not produce. Regenerate it after a fresh run to refresh the numbers.

The page is deliberately explicit that it is a static showcase: GitHub Pages cannot run
Python, ffmpeg or OpenCV, so uploads are not processed here.
"""
from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CSS = """
:root{--bg:#0a0c10;--panel:#12161d;--panel2:#171c25;--line:#232a36;--text:#e7ecf3;
--muted:#8b98ab;--accent:#3ddc97;--accent2:#6c8cff;--warn:#ffd23d}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1100px 560px at 18% -8%,#16202c 0%,var(--bg) 62%);
color:var(--text);font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
a{color:var(--accent)}
.wrap{max-width:1120px;margin:0 auto;padding:0 22px}
.banner{background:#1b2410;border-bottom:1px solid #3b3418;color:#e8e2c0;
font-size:13.5px;padding:10px 0}
.banner b{color:var(--warn)}
header{padding:38px 0 10px}
.logo{width:46px;height:46px;border-radius:13px;display:grid;place-items:center;
font-size:22px;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#06121a}
.brandrow{display:flex;gap:15px;align-items:center}
h1{margin:0;font-size:26px;letter-spacing:-.4px}
.sub{color:var(--muted);font-size:13.5px;margin:3px 0 0}
h2{font-size:17px;margin:34px 0 6px;letter-spacing:-.2px}
.lede{color:var(--muted);font-size:14px;margin:0 0 18px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px 22px}
.meta{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 14px}
.pill{font-size:12px;color:var(--muted);border:1px solid var(--line);background:var(--panel2);
border-radius:999px;padding:5px 11px}
.pill b{color:var(--text);font-weight:600}
svg{width:100%;height:150px;display:block}
.legend{color:var(--muted);font-size:12px;display:flex;justify-content:space-between;margin-top:4px}
.rec{background:linear-gradient(135deg,#10201a,#121a22);border:1px solid #1e3b30;
border-radius:14px;padding:18px 20px;margin-top:18px}
.rec h3{margin:0 0 8px;font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--accent)}
.rec .hook{font-size:19px;font-weight:650;margin:0 0 8px;line-height:1.35}
.rec p{margin:0 0 6px;font-size:14px;color:#c9d3e0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px;margin-top:16px}
.card{background:var(--panel2);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.card.win{border-color:var(--accent);box-shadow:inset 0 0 0 1px #1e3b30}
.vid{background:#05070a;display:flex;justify-content:center}
.vid video{width:100%;max-width:300px;height:auto;display:block}
.cardbody{padding:14px 16px 16px}
.badges{display:flex;gap:7px;margin-bottom:9px;flex-wrap:wrap}
.badge{font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;padding:3px 8px;
border-radius:999px;border:1px solid #1e3b30;color:var(--accent);background:#0e1a15}
.badge.r{border-color:#3b3418;color:var(--warn);background:#1b1810}
.badge.s{border-color:var(--line);color:var(--muted);background:#0e1218}
.hooktxt{font-size:15px;font-weight:620;line-height:1.4;margin:0 0 6px}
.why{font-size:12.5px;color:var(--muted);margin:0 0 12px}
.scores{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}
.sc{background:#0e1218;border:1px solid var(--line);border-radius:9px;padding:7px 9px}
.sc span{display:block;font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
.sc b{font-size:14px}
.bar{height:4px;border-radius:4px;background:#1b2230;margin-top:6px;overflow:hidden}
.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--accent2),var(--accent))}
.dl{display:flex;flex-wrap:wrap;gap:7px}
.dl a{font-size:12px;text-decoration:none;color:var(--text);border:1px solid var(--line);
border-radius:8px;padding:5px 9px;background:#0e1218}
.dl a:hover{border-color:var(--accent);color:var(--accent)}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:12px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em;font-weight:500}
td.n{font-variant-numeric:tabular-nums}
tr.top td{color:var(--accent)}
.tw{overflow-x:auto}
.note{font-size:12.5px;color:var(--muted);margin-top:12px}
.cmds{background:#0b0f14;border:1px solid var(--line);border-radius:10px;padding:14px 16px;
overflow-x:auto;font:13px/1.7 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:#cbd6e4}
.cmds b{color:var(--accent);font-weight:500}
footer{color:var(--muted);font-size:12.5px;padding:36px 0 52px}
@media(max-width:640px){.scores{grid-template-columns:1fr}h1{font-size:21px}}
"""


def esc(v) -> str:
    return html.escape(str(v), quote=True)


def timeline_svg(timeline: list[dict], windows: list[dict], duration: float) -> str:
    W, H, pad = 800, 150, 8
    if not timeline:
        return ""
    max_t = max(duration, timeline[-1]["t"] + 1) or 1.0
    x = lambda t: pad + (t / max_t) * (W - 2 * pad)
    y = lambda e: H - pad - e * (H - 2 * pad)

    area = f"M {pad} {H - pad} " + "".join(
        f"L {x(b['t']):.1f} {y(b['energy']):.1f} " for b in timeline
    ) + f"L {x(timeline[-1]['t']):.1f} {H - pad} Z"
    line = " ".join(
        f"{'M' if i == 0 else 'L'} {x(b['t']):.1f} {y(b['energy']):.1f}"
        for i, b in enumerate(timeline)
    )
    marks = "".join(
        f'<polygon points="{x(w["start"]):.1f},{pad + 10} {x(w["start"]) - 6:.1f},{pad + 24} '
        f'{x(w["start"]) + 6:.1f},{pad + 24}" fill="#ffd23d" opacity="0.95"/>'
        for w in windows[:6]
    )
    ticks = "".join(
        f'<line x1="{x(t):.1f}" y1="{H - pad}" x2="{x(t):.1f}" y2="{H - pad - 7}" '
        f'stroke="#3a4658" stroke-width="1"/>'
        for t in range(0, int(max_t) + 1, max(1, int(max_t // 8)))
    )
    return f"""<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img"
 aria-label="Audio energy across the clip with hook windows marked">
<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
<stop offset="0%" stop-color="#3ddc97" stop-opacity="0.45"/>
<stop offset="100%" stop-color="#3ddc97" stop-opacity="0.02"/></linearGradient></defs>
<path d="{area}" fill="url(#g)"/>
<path d="{line}" fill="none" stroke="#3ddc97" stroke-width="1.8"/>
{ticks}{marks}</svg>"""


def card(v: dict, assets: dict) -> str:
    ts = v.get("thumbnail_score") or {}
    p = v.get("prediction") or {}
    win = " win" if v.get("rank") == 1 else ""
    shorts = assets.get(v["variant_id"], {})
    video_tag = ""
    if shorts.get("mp4"):
        video_tag = (f'<div class="vid"><video controls preload="metadata" playsinline '
                     f'poster="{shorts["thumb"]}"><source src="{shorts["mp4"]}" '
                     f'type="video/mp4">Your browser cannot play this clip.</video></div>')
    dl = "".join(
        f'<a href="{shorts[k]}" download>{esc(lbl)}</a>'
        for k, lbl in (("mp4", "download 9:16"), ("wide", "download 16:9"))
        if shorts.get(k)
    )
    pct = lambda x: "—" if x is None else f"{x * 100:.1f}%"
    return f"""<article class="card{win}">{video_tag}
<div class="cardbody">
  <div class="badges">
    <span class="badge r">rank #{v.get('rank')}</span>
    <span class="badge">{esc(v.get('archetype'))}</span>
    <span class="badge s">{esc(v.get('style'))}</span>
  </div>
  <p class="hooktxt">“{esc(v.get('text'))}”</p>
  <p class="why">{esc(v.get('rationale'))}</p>
  <div class="scores">
    <div class="sc"><span>thumbnail</span><b>{ts.get('score', '—')}/100</b>
      <div class="bar"><i style="width:{ts.get('score', 0)}%"></i></div></div>
    <div class="sc"><span>watch-through</span><b>{pct(p.get('predicted_watch_through'))}</b>
      <div class="bar"><i style="width:{(p.get('predicted_watch_through') or 0) * 100:.0f}%"></i></div></div>
    <div class="sc"><span>hook energy</span><b>{pct(v.get('energy_match'))}</b></div>
    <div class="sc"><span>copy strength</span><b>{pct(v.get('copy_strength'))}</b></div>
  </div>
  <p class="why">starts at <b>{esc(v.get('start'))}s</b> · {esc(v.get('duration'))}s long ·
    {esc(v.get('caption_count'))} caption cues</p>
  <div class="dl">{dl}</div>
</div></article>"""


def build(report_path: Path, out_dir: Path) -> Path:
    rep = json.loads(report_path.read_text(encoding="utf-8"))
    meta = rep["meta"]
    analysis = rep.get("analysis", {})
    variants = rep.get("variants", [])
    rec = rep.get("recommendation", {})

    assets_dir = out_dir / "showcase" / "assets"
    if assets_dir.exists():
        shutil.rmtree(assets_dir)
    assets_dir.mkdir(parents=True)

    assets: dict[str, dict] = {}
    for v in variants:
        entry: dict = {}
        tp = Path(v.get("thumb_path", ""))
        if tp.exists():
            dst = assets_dir / f"{v['variant_id']}_thumb.jpg"
            shutil.copy(tp, dst)
            entry["thumb"] = f"showcase/assets/{dst.name}"
        for e in v.get("exports", []):
            if "error" in e:
                continue
            src = Path(e.get("path", ""))
            if not src.exists():
                continue
            key = "mp4" if e.get("height", 0) > e.get("width", 0) else "wide"
            dst = assets_dir / f"{v['variant_id']}_{e['platform']}.mp4"
            shutil.copy(src, dst)
            entry[key] = f"showcase/assets/{dst.name}"
        assets[v["variant_id"]] = entry

    rows = "".join(
        f"""<tr class="{'top' if v.get('rank') == 1 else ''}">
<td class="n">{esc(v.get('rank'))}</td><td>{esc(v.get('archetype'))}</td>
<td>{esc(v.get('text'))}</td><td class="n">{esc((v.get('thumbnail_score') or {}).get('score'))}</td>
<td class="n">{(v.get('prediction') or {}).get('predicted_watch_through', 0) * 100:.1f}%</td>
<td class="n">{(v.get('prediction') or {}).get('predicted_thumb_ctr', 0) * 100:.1f}%</td>
<td class="n">{esc(v.get('start'))}s</td></tr>"""
        for v in variants
    )

    plan = analysis.get("plan") or {}
    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hookforge — output showcase</title>
<meta name="description" content="Real output from one Hookforge pipeline run: ranked hook
variants, rendered thumbnails, CV scores and platform-ready clips.">
<style>{CSS}</style></head><body>

<div class="banner"><div class="wrap">
<b>Static showcase.</b> Everything below is real output from one pipeline run, generated by
<code>scripts/build_showcase.py</code> from that run's <code>report.json</code>. GitHub Pages
serves files only, so uploads are not processed here — run the app locally
(<code>uvicorn app.main:app</code>) or in a Codespace for the live version.
</div></div>

<header><div class="wrap"><div class="brandrow">
<div class="logo">◈</div>
<div><h1>Hookforge</h1>
<p class="sub">Agentic retention studio for solo creators · GeNarrative Clash, Open Track
(Autonomous Creator Agents) · Team CodeDev#02</p></div></div></div></header>

<div class="wrap">

<h2>1 · What the agents found</h2>
<p class="lede">One raw take in. Hook windows are ranked from measured audio energy, not from
a hunch — then each variant gets a rendered thumbnail, captions cut to the platform's limits,
and real MP4s per aspect ratio.</p>

<div class="panel">
  <div class="meta">
    <span class="pill">source <b>{esc(rep.get('filename'))}</b></span>
    <span class="pill"><b>{meta.get('width')}×{meta.get('height')}</b></span>
    <span class="pill"><b>{meta.get('fps')}</b> fps</span>
    <span class="pill"><b>{meta.get('duration')}s</b></span>
    <span class="pill">transcript <b>{esc(analysis.get('transcript_source'))}</b></span>
    <span class="pill">copy engine <b>{esc(plan.get('engine_used'))}</b></span>
    <span class="pill">topic <b>{esc(plan.get('topic'))}</b></span>
  </div>
  {timeline_svg(analysis.get('energy_timeline') or [], analysis.get('hook_windows') or [], meta.get('duration') or 1)}
  <div class="legend"><span>audio energy across the clip (1 s buckets)</span>
    <span>▲ hook windows ·
    {", ".join(str(w.get("start")) + "s" for w in (analysis.get("hook_windows") or [])[:5])}</span></div>
  <div class="rec">
    <h3>Recommended variant</h3>
    <p class="hook">“{esc(rec.get('hook_text'))}”</p>
    <p>{esc(rec.get('why'))}</p>
    <p style="color:var(--muted);font-size:13px">{esc(rec.get('next_step'))}</p>
  </div>
</div>

<h2>2 · The three variants</h2>
<p class="lede">Each card is a real rendered thumbnail and a real rendered clip — play them.
Scores are five named CV sub-scores with reasons, not a single opaque number.</p>
<div class="grid">{"".join(card(v, assets) for v in variants)}</div>

<h2>3 · Engagement model</h2>
<p class="lede">A documented linear prior over measured signals. Upload a platform CSV to the
running app and these predictions are replaced by measured lift.</p>
<div class="panel"><div class="tw"><table>
<tr><th>#</th><th>archetype</th><th>hook</th><th>thumb</th><th>watch-through</th>
<th>thumb CTR</th><th>starts</th></tr>{rows}</table></div>
<p class="note">{esc(rep.get('disclaimer'))}</p></div>

<h2>4 · Run the real thing</h2>
<p class="lede">This page is a snapshot. The app processes your own uploads.</p>
<div class="cmds"><b>git clone</b> https://github.com/bibekch003/hookforge.git
<br><b>cd</b> hookforge &amp;&amp; <b>pip install</b> -r requirements.txt
<br><b>python</b> scripts/make_sample_assets.py
<br><b>uvicorn</b> app.main:app --port 8000
<br><span style="color:#7d8a9c"># then open http://127.0.0.1:8000</span></div>
<p class="note">No local install? Open the repo → Code → Codespaces → Create codespace:
the devcontainer installs everything, then run the uvicorn line above. Deployment options are
in <a href="https://github.com/bibekch003/hookforge/blob/main/docs/DEPLOY.md">docs/DEPLOY.md</a>.</p>

</div>
<footer><div class="wrap">
Source, architecture and the honest list of what does and does not work yet:
<a href="https://github.com/bibekch003/hookforge">github.com/bibekch003/hookforge</a> ·
Generated from <code>report.json</code> by <code>scripts/build_showcase.py</code>.
</div></footer>
</body></html>"""

    index = out_dir / "index.html"
    index.write_text(page, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    total = sum(f.stat().st_size for f in assets_dir.iterdir())
    print(f"wrote {index} ({index.stat().st_size / 1024:.0f} KB) "
          f"+ {len(list(assets_dir.iterdir()))} assets ({total / 1048576:.2f} MB)")
    return index


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the GitHub Pages showcase.")
    ap.add_argument("--report", required=True, help="path to a run's report.json")
    ap.add_argument("--out", default=str(ROOT), help="output dir (repo root by default)")
    args = ap.parse_args()
    build(Path(args.report), Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
