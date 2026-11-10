"""The Hook Planner agent.

Two interchangeable engines behind one interface:

* ``offline`` - a deterministic copy engine. Reads the audio analysis and the
  transcript and writes hook variants from six archetypes. No API key, no
  network, identical output every run (this is what the demo and tests use).
* ``llm`` - an OpenAI-compatible chat-completions adapter. If a key is present
  it asks a model for the same structured output; any failure silently falls
  back to ``offline`` so the pipeline never breaks mid-demo.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field, asdict

from app.config import PLATFORM_PRESETS

ARCHETYPES: dict[str, dict] = {
    "curiosity_gap": {
        "template": "Nobody tells you this about {topic}",
        "why": "Opens an information gap the viewer wants closed.",
    },
    "contrarian": {
        "template": "Stop doing {topic} like this",
        "why": "Pattern-breaks against the standard advice in the niche.",
    },
    "stakes": {
        "template": "{topic} cost me a month. Watch this first.",
        "why": "Loss framing raises the cost of scrolling past.",
    },
    "result_first": {
        "template": "This is the result. Here's the 12 seconds that made it.",
        "why": "Leads with the payoff, then promises the mechanism.",
    },
    "question": {
        "template": "Why does {topic} always break at the worst moment?",
        "why": "A question the target viewer has literally asked.",
    },
    "demo_first": {
        "template": "Watch what happens when you {verb} {topic}",
        "why": "Motion in the first frame; no talking-head wind-up.",
    },
}

STYLES = ["bold_lower", "split_band", "top_strip"]

# Templates that read correctly with no subject at all. Used when there is no
# transcript and the filename is just a hash - better generic copy than
# "Nobody tells you this about 19360220a5".
TOPICLESS = {
    "curiosity_gap": "Nobody tells you this before you start",
    "contrarian": "Stop doing it like this",
    "stakes": "This cost me a month. Watch this first.",
    "result_first": "This is the result. Here's the 12 seconds that made it.",
    "question": "Why does this always break at the worst moment?",
    "demo_first": "Watch what happens in the first three seconds",
}
GENERIC_TOPICS = {"this", "that", "it", "clip", "video", "take", "raw", "untitled", "movie"}
CURIOSITY_WORDS = ("nobody", "stop", "why", "secret", "wrong", "mistake",
                   "never", "actually", "truth", "before", "watch", "here's")

STOPWORDS = set("""a an the and or but if then than that this these those i you he she it we they
is are was were be been being do does did doing have has had having of to in on for with at by from
as not no so just about into over after before your my our their his her its me us them what which
who whom when where how very really quite more most much many few some any all can could will would
should may might must shall like get got make made own same other another each every
here there now also even still yet because while since both either neither
around through across without within against between during toward onto upon per via plus minus
off out up down back away again ever once twice instead rather almost enough
""".split())

# Quantity and time words make terrible hook subjects ("about three years").
WEAK_SUBJECTS = set("""one two three four five six seven eight nine ten eleven twelve twenty thirty forty
fifty hundred thousand million billion first second third last next time times year years month months
week weeks day days hour hours minute minutes second seconds thing things stuff way ways bit lot lots
something anything everything nothing someone anyone everyone people person kind sort
""".split())

# Common verbs: a hook subject built from these reads as broken grammar.
WEAK_VERBS = set("""spent spend go goes went going gone make makes made making take takes took taken taking
put puts putting pull pulls pulled pullin build builds built building render renders rendered rendering
stop stops stopped stopping start starts started starting open opens opened opening lose loses lost losing
post posts posted posting get gets got gotten getting give gives gave given giving use uses used using
want wants wanted wanting need needs needed keep keeps kept keeping come comes came coming see sees saw
seen look looks looked looking say says said saying tell tells told telling know knows knew known
double doubles doubled doubling change changes changed changing break breaks broke broken breaking
rewrite rewrites rewritten writing write writes wrote written edit edits edited editing
""".split())


@dataclass
class HookVariant:
    variant_id: str
    archetype: str
    text: str
    start: float
    duration: float
    style: str
    rationale: str
    engine: str
    topic: str = ""
    copy_strength: float = 0.0
    energy_match: float = 0.0
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# copy helpers
# ---------------------------------------------------------------------------
def extract_topic(transcript: str | None, fallback: str) -> str:
    """Pick a short noun-ish subject phrase from the transcript.

    Deliberately conservative: a hook that reads as broken grammar is worse than
    a generic one, so weak subjects (numbers, time words) and common verbs are
    dropped before a two-word phrase is chosen. The LLM adapter replaces this
    heuristic entirely when a key is configured.
    """
    if not transcript:
        return fallback
    tokens = re.findall(r"[A-Za-z][A-Za-z'\-]+", transcript)
    salient = [w for w in tokens
               if len(w) > 3
               and w.lower() not in STOPWORDS
               and w.lower() not in WEAK_SUBJECTS
               and w.lower() not in WEAK_VERBS
               and not w.lower().endswith("ing")]
    if not salient:
        salient = [w for w in tokens if len(w) > 3 and w.lower() not in STOPWORDS] or []
    if not salient:
        return fallback

    freq: dict[str, int] = {}
    for w in salient:
        freq[w.lower()] = freq.get(w.lower(), 0) + 1

    best, best_score = None, -1.0
    for i in range(len(salient) - 1):
        a, b = salient[i], salient[i + 1]
        score = float(freq[a.lower()] + freq[b.lower()])
        # adjacent in the original text reads better than a stitched pair
        if re.search(rf"\b{re.escape(a)}\s+{re.escape(b)}\b", transcript, re.IGNORECASE):
            score += 2.0
        if score > best_score:
            best, best_score = (a, b), score

    phrase = " ".join(best) if best else salient[0]
    return phrase.lower()


def clean_stem(stem: str) -> str:
    """Turn a filename into a usable subject, or fall back to 'this'.

    Uploads arrive as random hex names; using one as a hook subject is the kind
    of detail that makes a demo look broken.
    """
    s = re.sub(r"[0-9a-f]{8,}", " ", stem, flags=re.IGNORECASE)
    s = re.sub(r"[^A-Za-z ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s if len(s) >= 4 else "this"


def is_generic(topic: str) -> bool:
    return topic.strip().lower() in GENERIC_TOPICS or len(topic.strip()) < 4


def copy_strength(text: str) -> float:
    """Heuristic 0-1 score for hook copy. Rewards the things that move CTR."""
    if not text:
        return 0.0
    score = 0.30
    low = text.lower()
    if re.search(r"\d", text):
        score += 0.16
    if "?" in text:
        score += 0.10
    if re.search(r"\byou\b|\byour\b", low):
        score += 0.14
    if any(w in low for w in CURIOSITY_WORDS):
        score += 0.14
    if 18 <= len(text) <= 64:
        score += 0.16
    elif len(text) > 90:
        score -= 0.14
    return round(max(0.0, min(1.0, score)), 4)


def _plan_offline(topic: str, windows: list[dict], duration: float, n: int,
                  clip_seconds: float) -> list[dict]:
    order = ["curiosity_gap", "contrarian", "result_first", "question", "stakes", "demo_first"]
    generic = is_generic(topic)
    out: list[dict] = []
    for i in range(n):
        arch = order[i % len(order)]
        win = windows[i % len(windows)] if windows else {"start": 0.0, "energy": 0.0, "speech": 0.0}
        text = (TOPICLESS[arch] if generic
                else ARCHETYPES[arch]["template"].format(topic=topic, verb="you"))
        out.append({
            "archetype": arch,
            "text": text,
            "start": round(min(max(0.0, win.get("start", 0.0)), max(0.0, duration - 1.0)), 2),
            "duration": round(min(clip_seconds, max(4.0, duration)), 2),
            "style": STYLES[i % len(STYLES)],
            "rationale": ARCHETYPES[arch]["why"],
        })
    return out


def _plan_llm(topic: str, transcript: str | None, windows: list[dict], n: int,
              duration: float, clip_seconds: float, platform: str) -> list[dict] | None:
    """Ask an OpenAI-compatible model for hook variants. Returns None on any issue."""
    key = os.getenv("HOOKFORGE_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    base = os.getenv("HOOKFORGE_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("HOOKFORGE_LLM_MODEL", "gpt-4o-mini")
    prompt = (
        "You are a short-form video hook writer. Return STRICT JSON only: "
        '{"variants":[{"archetype":"...","text":"...","start":0.0,"duration":12.0,'
        '"style":"bold_lower|split_band|top_strip","rationale":"..."}]}\n'
        f"Count: {n}. Platform: {platform}. Topic: {topic}. Max clip seconds: {clip_seconds}.\n"
        f"Transcript: {(transcript or '')[:2000]}\n"
        f"Candidate start offsets with energy 0-1: {json.dumps(windows[:6])}\n"
        "Each hook text must be under 70 characters, first person or second person, no emojis."
    )
    try:
        import httpx
        resp = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.8,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=45.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        variants = data.get("variants") or []
        clean: list[dict] = []
        for v in variants[:n]:
            if not v.get("text"):
                continue
            clean.append({
                "archetype": str(v.get("archetype", "curiosity_gap"))[:40],
                "text": str(v["text"])[:120],
                "start": float(max(0.0, min(float(v.get("start", 0.0)), max(0.0, duration - 1.0)))),
                "duration": float(min(clip_seconds, max(4.0, float(v.get("duration", clip_seconds))))),
                "style": v.get("style") if v.get("style") in STYLES else "bold_lower",
                "rationale": str(v.get("rationale", ""))[:200],
            })
        return clean or None
    except Exception:
        return None


def plan_hooks(
    *,
    duration: float,
    windows: list[dict],
    transcript: str | None,
    filename_stem: str,
    n: int = 4,
    engine: str = "offline",
    platform: str = "youtube_shorts",
    clip_seconds: float = 15.0,
) -> tuple[list[HookVariant], dict]:
    """Return (variants, run_meta). run_meta records which engine actually ran."""
    topic = extract_topic(transcript, fallback=clean_stem(filename_stem))
    preset = PLATFORM_PRESETS.get(platform, {})
    if preset.get("max_seconds"):
        clip_seconds = min(clip_seconds, float(preset["max_seconds"]))
    clip_seconds = min(clip_seconds, max(4.0, duration))

    raw = None
    used = "offline"
    if engine in ("llm", "auto"):
        raw = _plan_llm(topic, transcript, windows, n, duration, clip_seconds, platform)
        used = "llm" if raw else "offline"
    if not raw:
        raw = _plan_offline(topic, windows, duration, n, clip_seconds)

    variants: list[HookVariant] = []
    for i, v in enumerate(raw):
        variants.append(HookVariant(
            variant_id=f"v{i + 1}-{uuid.uuid4().hex[:6]}",
            archetype=v["archetype"],
            text=v["text"],
            start=v["start"],
            duration=v["duration"],
            style=v["style"],
            rationale=v["rationale"],
            engine=used,
            topic=topic,
            copy_strength=copy_strength(v["text"]),
        ))
    meta = {
        "engine_requested": engine,
        "engine_used": used,
        "topic": topic,
        "count": len(variants),
        "generic_topic": is_generic(topic),
        "note": (
            "No transcript available: hooks use subject-free templates. "
            "Install faster-whisper or supply a transcript for topic-aware copy."
            if is_generic(topic) else
            "LLM adapter unavailable or returned nothing; deterministic engine used."
            if engine in ("llm", "auto") and used == "offline" else
            "Deterministic copy engine (no API key required)."
        ),
    }
    return variants, meta
