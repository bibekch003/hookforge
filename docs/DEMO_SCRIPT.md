# Demo video script

Target length **3 min 30 s** (the form asks for a public walkthrough of the ~50 % prototype).
Read at a normal pace — the narration below is timed for that.

---

## Before you hit record (10 minutes of prep)

1. Fresh terminal, repo root, venv activated:
   ```bash
   cd hookforge && source .venv/bin/activate
   python scripts/make_sample_assets.py      # ~40 s, builds the demo clip
   python scripts/demo_run.py                # warm the caches once, then clear the screen
   ```
2. Start the dashboard in a second terminal **before** recording:
   ```bash
   uvicorn app.main:app --port 8000
   ```
3. Browser: open `http://127.0.0.1:8000`, zoom to 110 %, close every other tab.
4. Have `README.md` open in the editor at §10 (the verified-output table) — you will show
   it for three seconds at the end.
5. Record at 1080p, mic on, notifications off. Cursor size large.
6. Do one full dry run. The first run pays ffmpeg's cold start and looks slow.

> Timing note: a full run is ~20 s for 3 variants on one platform. **Do not** sit in
> silence — keep talking over it, and cut the dead air in the edit if it drags.

---

## 0:00 – 0:20 · Cold open (the problem)

**On screen:** the dashboard, idle. Nothing running.

**Narration:**
> "One good take. Four jobs before it can be posted: find the hook, cut it for four
> platforms, caption it four different ways, and guess which thumbnail will work. That is
> the same work four times, and the most important decision — where the first three seconds
> start — is still made by scrubbing a timeline and hoping."

## 0:20 – 0:45 · What Hookforge is

**On screen:** scroll the README architecture diagram (or show the mermaid block).

**Narration:**
> "This is Hookforge. It is not another video generator — it is the decision layer around a
> take you already shot. One upload goes through four agents: audio intelligence finds the
> moments worth opening on, a hook planner writes variants against those moments, a visual
> scorer renders and scores a thumbnail for each, and a delivery stage renders every
> platform with captions that actually fit. Then it ranks them and tells you why."

## 0:45 – 1:35 · The chain, from the terminal

**On screen:** terminal. Type the command live.

```bash
python scripts/demo_run.py --platforms youtube_shorts,youtube --variants 3 --clip 10
```

**Narration (over the log lines):**
> "The log is the pipeline in order: probe, audio intelligence, transcript, hook planner,
> then per variant the thumbnail, captions and exports."

**On screen:** when the table prints, stop and point at the hook windows line.

**Narration:**
> "This is the part I care about. The clip has loud passages at four-to-eight seconds and
> sixteen-to-twenty. The analyser was never told that — it ranked every three-second window
> by energy times novelty, and returned sixteen and five first. Scene cuts landed exactly on
> the four-second boundaries too. That is real DSP, not a mock."

**On screen:** scroll to the ranked table.

**Narration:**
> "Three variants, ranked. Curiosity gap at seventy-four percent predicted watch-through,
> result-first second, contrarian third. Look at where they start: sixteen seconds, two
> seconds, five seconds. Those are the three hottest audio windows, not arbitrary offsets.
> And watch-through is not the thumbnail score — it also weighs hook energy match, copy
> strength and duration, so the columns do not have to agree."

## 1:35 – 2:30 · The dashboard

**On screen:** browser. Click **Run on the sample clip**.

**Narration:**
> "Same code path, through the API. I pick three variants and two targets."

**On screen:** while it runs, keep talking.

**Narration:**
> "Under the hood it is one function — run_pipeline — called by the API, the CLI and the
> tests, so what you are watching is exactly what the test suite covers."

**On screen:** results appear. Point at the energy curve first.

**Narration:**
> "That is the audio envelope for the whole take, with the hook windows marked in yellow.
> Below it, the recommendation, and the reason it won: thumbnail score, which signals fired,
> and how hot the hook window is against the video's own average."

**On screen:** hover a variant card, then the score bars.

**Narration:**
> "Each card is a real rendered JPEG — not a placeholder. Bold-lower, split-band, top-strip
> styles, and for vertical targets it uses blur-pad framing so a sixteen-by-nine take does
> not get decapitated by a centre crop. The score is five weighted sub-scores: contrast,
> colourfulness, subject presence, legibility under the text, and clutter. It prints reasons,
> so you can argue with it."

## 2:30 – 3:00 · The actual files

**On screen:** click a Shorts download, play 5 s. Then click the 16:9 one.

**Narration:**
> "These are the files it produced. Ten-eighty by nineteen-twenty, loudness normalised to
> minus fourteen LUFS, captions burned in from a per-resolution ASS file — which matters,
> because libass lays SRT out on a three-eighty-four by two-eighty-eight canvas and blows up
> the font on a vertical render. Each variant also writes SRT and VTT sidecars for upload,
> and here is the same hook as sixteen-by-nine for the main channel."

## 3:00 – 3:20 · Analytics, and honesty about it

**On screen:** scroll to the engagement table, then upload `app/static/telemetry_template.csv`.

**Narration:**
> "The engagement model is deliberately a documented linear prior over signals we actually
> measure — not a black box pretending to know the algorithm. Once you have real numbers,
> you upload the platform CSV and it swaps prediction for measurement and shows the lift.
> The app always tells you which one you are looking at."

## 3:20 – 3:40 · Status, roadmap, close

**On screen:** README §3 table (what's working), then §12 roadmap.

**Narration:**
> "At the halfway mark: ingest, audio intelligence, hook planning with an optional LLM
> adapter, thumbnail render and scoring, captions in three formats, five delivery presets,
> persistence, API and this dashboard are all working and tested — eleven pipeline tests and
> ten API checks. What is not built yet is publishing to the platforms, per-word caption
> alignment, and replacing the prior with a model trained on your own telemetry. Those are
> the next three items, and the schema is already storing the features they need. Thanks for
> watching."

---

## 45-second version (if a short clip is needed)

1. `python scripts/demo_run.py` → stop on the ranked table.
2. "Audio peaks found at 16 s and 5 s, no hints. Three hooks ranked, thumbnails rendered and
   scored, six platform-ready MP4s with burned captions."
3. Cut to the dashboard variant cards, then one playing vertical export.
4. "Fifty percent done, tested, and every number is explainable."

---

## Recording checklist

- [ ] `python scripts/make_sample_assets.py` has run (clip exists in `samples/`)
- [ ] `data/` cleared so the run looks fresh: `rm -rf data`
- [ ] `uvicorn app.main:app --port 8000` running, dashboard loads
- [ ] Browser zoom 110 %, notifications off, no personal tabs
- [ ] Terminal font ≥ 14 pt, window ≥ 100 columns (the ranked table is 78 wide)
- [ ] One dry run completed
- [ ] Video uploaded as **public** (or unlisted-with-link); link pasted into
      `README.md` §16 and into the submission form
- [ ] Check the upload plays back with audio at the link, in an incognito window

## If something breaks mid-recording

| Symptom | Fix |
|---|---|
| `No ffmpeg found` | `pip install imageio-ffmpeg` (the app auto-detects it) |
| `Sample clip missing` | `python scripts/make_sample_assets.py` |
| Dashboard shows "engine unreachable" | uvicorn not running, or wrong port |
| A run takes >60 s | first run pays cold start; do a warm-up run before recording |
| Port 8000 busy | `uvicorn app.main:app --port 8010` |
