# Architecture notes

Companion to the README. This file records the decisions that are not obvious from
reading the code, and the trade-offs accepted at the 50 % mark.

## 1. Data flow, precisely

```
upload ──▶ UPLOAD_DIR/<hex>.<ext>
            │
            ├─ media.probe()            width, height, fps, frames, duration, has_audio
            ├─ media.extract_audio()    ffmpeg → 16 kHz mono WAV → float32 ndarray
            │    ├─ audio.rms_envelope()   20 ms hops
            │    ├─ audio.timeline()       1 s buckets: energy + speech-band ratio
            │    └─ audio.hook_windows()   top-k 3 s windows by energy × novelty
            ├─ media.scene_cuts()       HSV histogram Bhattacharyya distance at 2 fps
            └─ captions.transcribe()    faster-whisper → sidecar → none
                     │
                     ▼
            hooks.plan_hooks()          topic + archetypes + start offsets + styles
                     │
        for each variant ────────────────┐
            media.extract_frame(start)   │
            thumbs.render_variant()      │  Pillow: cover or blur-pad, scrim, accent bar
            thumbs.score_thumbnail()     │  OpenCV: 5 sub-scores → 0-100 + reasons
            formats.extract_poster()     │  16:9 still for the report
            captions.build_cues()        │  transcript sliced to the clip window
            captions.to_srt / to_vtt     │  sidecars for upload
            formats.export_clip()        │  per platform: filter graph + ASS burn-in
            analytics.predict()          │  linear prior from measured signals
                                         ▼
            analytics.rank() ──▶ SQLite ──▶ report.json + dashboard
```

## 2. Why the hook window search looks like that

The naive approach is "start at 0" or "start where the loudest single frame is". Both are
bad: a single loud frame is usually a transient (a door slam, a clap), and t=0 is exactly
the wind-up creators want to cut.

`audio.hook_windows()` scores every 3-second window on two terms:

- **energy** — mean RMS of the window, normalised against the loudest window in the video.
- **novelty** — window mean ÷ mean of its surrounding neighbourhood (one window either
  side). A window that is much hotter than its surroundings is a moment of emphasis.

`score = 0.65 · (energy / global_mean) + 0.35 · novelty`, then non-maximum suppression at
0.75 × window length so the returned candidates are distinct moments rather than the same
peak sampled four times.

On the bundled sample this finds 16 s and 5 s first — the two passages the generator
deliberately made loud — without being told where they are. That is the property the test
suite asserts.

## 3. Why two copy engines

A demo that requires an API key is a demo that fails on a judge's laptop. A demo that
pretends to use an LLM is dishonest. So:

- `engine="offline"` (default) — six archetypes, subject from the transcript, start offset
  from the hook windows, style round-robined. Deterministic: same input, same output, and
  the test suite pins that.
- `engine="llm"` — posts a strict-JSON prompt to any OpenAI-compatible `/chat/completions`
  endpoint. Any exception (no key, timeout, malformed JSON, refusal) returns `None` and the
  caller falls back to the offline engine. `run_meta.engine_used` always records what
  actually ran, so the report never claims more than it did.

Topic extraction (`hooks.extract_topic`) is deliberately conservative. It removes
stopwords, quantity/time words ("three", "years", "seconds") and a list of common verbs
before scoring adjacent salient pairs, with a bonus when the pair appears verbatim in the
transcript. Ungrammatical hook copy ("Nobody tells you this about three years") damages
credibility more than a generic hook does, so when the transcript is missing or the
filename is just a hash, the planner switches to subject-free templates
(`hooks.TOPICLESS`) rather than putting a hex string in the copy.

## 4. Caption pipeline: three formats, one source of truth

| Consumer | Format | Why |
|---|---|---|
| Platform upload | `.srt` and `.vtt` sidecars | every platform accepts one of these |
| Burned-in render | `.ass` | only format where we control the canvas resolution |
| Dashboard | in-memory `Cue` list | preview of the first cues per variant |

The ASS writer sets `PlayResX/PlayResY` to the export resolution and derives font size
from `width ÷ chars_per_line ÷ 0.58`, so a 28-character TikTok cue and a 42-character
YouTube cue both fit their frame. Line breaks are explicit `\N`, not left to libass:
character counts are not rendered widths, and letting libass wrap produced text running off
the 1080 px edge in testing.

`build_cues()` slices the transcript proportionally to the clip window
(`start/duration` → character offsets) and caps each cue at `max_chars × max_lines × 0.85`
— the 0.85 accounts for the characters lost to word-boundary wrapping.

**Known gap:** proportional timing drifts from the real speech when the speaker pauses.
Word-level timestamps from faster-whisper fix this and are on the roadmap.

## 5. Failure containment

| Failure | Behaviour |
|---|---|
| One platform's ffmpeg render fails | that export records `{"error": ...}`; other platforms and variants continue |
| ffmpeg build lacks libass | captions are not burned; sidecar `.srt`/`.vtt` still produced, warning recorded |
| No audio track | envelope is silence; hook windows fall back to t=0; report shows `has_audio: false` |
| No transcript | subject-free hook templates; report says so in `plan.note` |
| LLM key missing or call fails | deterministic engine runs; `engine_used` says `offline` |
| OpenCV ≥ 5 (no cascade API) | skin-tone salience proxy; `subject_method` records which was used |
| Upload too large | rejected with 413 before any processing |
| Unknown video_id | 404, not a stack trace |

## 6. Storage

One SQLite file, four tables: `videos`, `variants`, `exports`, `telemetry`.

`variants` stores both the queryable columns and `payload_json` (the full variant
document). The columns are for SQL and reporting; the payload is the contract the API and
dashboard read. This exists because the first version of the schema silently dropped fields
the UI needed — storing the document makes that class of drift impossible.

Rendered media lives on disk under `data/` and is served read-only by two static mounts
(`/media/thumbs`, `/media/exports`). `data/` is gitignored; nothing in it is required to
start the app.

## 7. Performance at this stage

Measured on a 2-vCPU container, sample clip, 3 variants × 2 platforms: **57 s** total.
Breakdown: ingest and analysis ~2 s, thumbnails and scoring ~3 s, the remaining ~50 s is
ffmpeg encoding (6 clips, x264 veryfast, loudnorm). That is why the request is synchronous
today and why a job queue is the first item on the roadmap — a 20-minute take would be
minutes of encoding per platform.

Cheap wins available: encode all platforms from one decode (`-filter_complex` split),
lower `crf` cost with `-tune stillimage` for talking heads, and reuse the ASS file per
resolution instead of regenerating it per variant.

## 8. What we would change with more time

1. **Decode once, encode many.** Currently each platform re-opens the source.
2. **Frame-accurate seeking.** `cv2.CAP_PROP_POS_MSEC` seeking on long-GOP files is
   approximate; ffmpeg `-ss` before `-i` (already used for exports) is accurate. Thumbnail
   frames should use the same path.
3. **Learned re-ranking.** The SQLite schema already stores features and outcomes next to
   each other, which is the training set for replacing the prior.
4. **Async job model.** `POST /api/analyze` → job id → SSE progress, so the UI can show
   per-variant completion instead of one spinner.
