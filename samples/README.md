# Demo assets

`samples/sample_creator_clip.mp4` is **generated**, not downloaded:

```bash
python scripts/make_sample_assets.py
```

It builds a 24-second 1280×720 clip at 12 fps with:

- six scene changes, exactly at 4 s intervals (so cut detection has a real target)
- deliberately loud audio in **4–8 s** and **16–20 s**, quiet elsewhere (so the hook-window
  search has a real target and can be verified)
- a face-like subject that drifts, so the thumbnail scorer has something to measure
- an audio meter and timecode, but **no burned-in captions** — the pipeline burns its own,
  and two competing caption layers make the 9:16 crop look broken

`samples/sample_creator_clip.txt` is the sidecar transcript. Delete it and re-run to see the
no-transcript path: hooks fall back to subject-free templates instead of inventing a topic.

Regenerating is deterministic (seeded), so the audio analysis assertions in
`tests/test_pipeline.py` stay valid.
