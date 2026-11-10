# Submission — every field, filled

Copy each block into the hackathon form. Items marked `<< … >>` need a link you create.

---

## a. Team Name & Team Size

```
Team name: CodeDev#02
Team size: 3
```

## b. Team Leader Name, Email & WhatsApp Number

```
Name:     Bibek Chakraborty
Email:    bibekchakraborty58@gmail.com
WhatsApp: +91 9875615461
```

## c. Chosen Challenge Track

```
Open Track — Empowering the Creative Artist
Challenge area: Content Strategy & Distribution → Autonomous Creator Agents
```

**Project name:** Hookforge — agentic retention studio for solo creators

**One-line pitch:**
One raw take in, ranked platform-ready hook variants out — hook windows found from the
audio, hooks written per archetype, thumbnails rendered and CV-scored, captions cut to each
platform's limits, and a recommendation that explains itself.

**Why this challenge area:** the track's own brief says solo creators lose most of their
creative hours to thumbnail variations, multi-platform cutdowns, semantic tagging and
engagement analytics. Hookforge attacks all four in one pass, and its highest-value output
is the one a creator cannot buy today: *where the first three seconds should start*, chosen
from measured audio energy instead of a hunch.

## d. GitHub Repository Link (Public)

```
https://github.com/bibekch003/hookforge
```

The repository contains the working ~50 % codebase and the full `README.md` breakdown of
concept, problem statement, architecture and technology stack (required, since there is no
PPT submission).

**What a reviewer should open first**

| Read | Where | Covers |
|---|---|---|
| README §1–2 | `README.md` | problem statement and concept |
| README §3 | `README.md` | exactly what is working vs. not — the 50 % claim |
| README §4 | `README.md` | architecture diagram + module map + design decisions |
| README §5 | `README.md` | technology stack and why each choice |
| README §8 | `README.md` | how every score is computed (no black boxes) |
| README §10 | `README.md` | verified output on the bundled sample, with real numbers |
| Deeper notes | `docs/ARCHITECTURE.md` | data flow, trade-offs, failure containment |
| Proof it runs | `tests/test_pipeline.py`, `scripts/smoke_api.py` | 11 pipeline tests + 10 API checks |

**To verify it yourself in three commands**

```bash
pip install -r requirements.txt
python scripts/make_sample_assets.py     # builds a synthetic 24s demo take
python scripts/demo_run.py               # runs the whole chain, prints the ranked table
```

No API key, no model download, no network needed.

## e. Live Demo Video Link (Public)

```
<< https://youtu.be/<id>   (or Drive / Loom / Vimeo public link) >>
```

~3 min 30 s walkthrough of the working prototype. Shot-by-shot script and recording
checklist: `docs/DEMO_SCRIPT.md`.

---

## Repo status

Already pushed: **https://github.com/bibekch003/hookforge** — public, `main` branch, MIT
licence, 36 files. Verified by cloning it fresh and running `python tests/test_pipeline.py`
(11/11 pass) plus `python scripts/demo_run.py` (renders real MP4s).

To update it later:

```bash
git clone https://github.com/bibekch003/hookforge.git
# ... edit files ...
git add -A && git commit -m "describe the change" && git push
```

> If the repo must stay private until judging closes, add the organisers as collaborators
> instead — the form explicitly requires *Public*.

## Pre-submit checklist

- [ ] Repo is **public** and the link opens in an incognito window
- [ ] `README.md` renders: mermaid diagram draws, `docs/assets/thumbnail-9x16.jpg` loads
- [ ] `requirements.txt` installs clean on a fresh machine (Python 3.11+)
- [ ] `python scripts/make_sample_assets.py && python scripts/demo_run.py` works from a
      clean clone
- [ ] `python tests/test_pipeline.py` → 11/11 pass
- [ ] Demo video is **public**, plays with audio, and shows the app actually running
- [ ] Video link added to `README.md` §16 **and** the form (field e)
- [ ] Team name, size, leader name/email/WhatsApp match exactly: CodeDev#02 · 3 ·
      Bibek Chakraborty · bibekchakraborty58@gmail.com · +91 9875615461
- [ ] Track selected: Open Track → Autonomous Creator Agents
- [ ] `.gitignore` keeps `data/`, `.venv/`, `__pycache__/` out of the repo
- [ ] No secrets in the repo (`grep -r "sk-" .` returns nothing)

## Notes on honesty (worth keeping in the repo)

Two claims are deliberately not made anywhere in the project:

1. **"Predicts the algorithm."** The engagement model is a documented linear prior over
   measured signals, labelled as such in the API, the dashboard and the README. Real
   numbers replace it via CSV upload.
2. **"Fully working."** The README §3 table lists what works and what does not, including
   that the faster-whisper ASR path and the LLM copy adapter are implemented but not on the
   demo path, and that publishing to platforms is not built.

Judges tend to reward a 50 % claim that is exactly true over a 100 % claim that is not.
