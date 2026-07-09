#!/usr/bin/env python3
"""
VLM provider abstraction for the batch audit pipeline.

The production evaluator (`evaluate.py`) was Gemini-only: Agent 1 and
Agent 3 watch the video natively (`files.upload` + per-part `fps`), Agent 2 is
text-only. This module lets the SAME pipeline run under Claude or GPT as the judge
so the WATCH-family over-scoring can be tested across backbones (the Stage-1 model
sweep).

Gemini ingests MP4 natively; Claude and OpenAI do not — so for the video-facing
agents we sample N evenly-spaced stills with ffmpeg and send them as images.
Agent 2 (text-only) works on any backend unchanged.

Selection is by env var, so nothing in the pipeline needs per-provider code beyond
one dispatch point:

    VIBE_TEACH_VLM_PROVIDER = gemini (default) | claude | gpt
    VIBE_TEACH_CLAUDE_MODEL = claude-opus-4-8   (default)
    VIBE_TEACH_GPT_MODEL    = gpt-5-mini        (default)
    VIBE_TEACH_VLM_FRAMES   = 48                (frames sampled per video)
    VIBE_TEACH_VLM_MAXTOK   = 8000              (max output tokens)

`generate()` returns a small shim with `.text` / `.parsed` / `.usage_metadata`
so it drops into the existing `response.parsed → text-clean` handling untouched
(for claude/gpt, `.parsed` is always None → the JSON-cleaning fallback runs).

The gemini branch is intentionally NOT routed through here — the caller keeps its
native genai calls, so the Gemini production path is untouched (zero regression).
"""

import base64
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional


PROVIDER = os.environ.get("VIBE_TEACH_VLM_PROVIDER", "gemini").strip().lower()
CLAUDE_MODEL = os.environ.get("VIBE_TEACH_CLAUDE_MODEL", "claude-opus-4-8").strip()
GPT_MODEL = os.environ.get("VIBE_TEACH_GPT_MODEL", "gpt-5-mini").strip()
N_FRAMES = int(os.environ.get("VIBE_TEACH_VLM_FRAMES", "48"))
MAX_TOKENS = int(os.environ.get("VIBE_TEACH_VLM_MAXTOK", "8000"))
FRAME_MAX_WIDTH = int(os.environ.get("VIBE_TEACH_VLM_FRAME_WIDTH", "768"))


class _Shim:
    """Mimics the fields the pipeline reads off a genai response."""

    def __init__(self, text: str):
        self.text = text
        self.parsed = None            # forces the existing JSON-cleaning fallback
        self.usage_metadata = None    # _log_gemini_usage prints "null" harmlessly


# --------------------------------------------------------------------------- #
# Frame sampling (ffmpeg)
# --------------------------------------------------------------------------- #

def _ffprobe_duration(video_path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    try:
        return float(out.stdout.strip())
    except (ValueError, TypeError):
        return 0.0


def sample_frames(video_path: Path, n: int = N_FRAMES) -> List[bytes]:
    """Extract ~n evenly-spaced JPEG frames, downscaled to FRAME_MAX_WIDTH.

    Returns a list of JPEG byte strings (at most n).
    """
    video_path = Path(video_path)
    dur = _ffprobe_duration(video_path)
    with tempfile.TemporaryDirectory() as td:
        outdir = Path(td)
        if dur and dur > 0:
            fps = max(0.01, n / dur)           # ~n frames across the whole video
            vf = f"fps={fps:.6f},scale='min({FRAME_MAX_WIDTH},iw)':-2"
        else:
            vf = f"scale='min({FRAME_MAX_WIDTH},iw)':-2"
        subprocess.run(
            ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(video_path),
             "-vf", vf, "-q:v", "4", str(outdir / "f%05d.jpg")],
            check=True,
        )
        frames = sorted(outdir.glob("f*.jpg"))
        if len(frames) > n:
            # even downselect to exactly n
            step = len(frames) / n
            frames = [frames[int(i * step)] for i in range(n)]
        return [f.read_bytes() for f in frames]


# --------------------------------------------------------------------------- #
# Claude (Anthropic)
# --------------------------------------------------------------------------- #

_anthropic_client = None


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    return _anthropic_client


def _claude_generate(system: str, prompt: str, frames: Optional[List[bytes]]) -> str:
    client = _get_anthropic()
    content = []
    for jpg in (frames or []):
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.standard_b64encode(jpg).decode("ascii"),
            },
        })
    content.append({"type": "text", "text": prompt})
    # opus-4-8 rejects temperature/top_p; omit them. Thinking left off (scorer).
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


# --------------------------------------------------------------------------- #
# GPT (OpenAI)
# --------------------------------------------------------------------------- #

_openai_client = None


def _get_openai():
    global _openai_client
    if _openai_client is None:
        import openai
        _openai_client = openai.OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY")
        )
    return _openai_client


def _gpt_generate(system: str, prompt: str, frames: Optional[List[bytes]]) -> str:
    client = _get_openai()
    user_content = []
    for jpg in (frames or []):
        b64 = base64.standard_b64encode(jpg).decode("ascii")
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })
    user_content.append({"type": "text", "text": prompt})
    # gpt-5 family: reasoning model → no temperature, use max_completion_tokens.
    # response_format json_object forces valid JSON (prompts already say "JSON").
    resp = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        max_completion_tokens=MAX_TOKENS,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or ""


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

def generate(*, role: str, system: str, prompt: str,
             video_path: Optional[Path] = None) -> _Shim:
    """Provider-agnostic generation. Only called for claude/gpt (gemini keeps its
    native path). If ``video_path`` is given, frames are sampled and sent as images.
    """
    frames = None
    if video_path is not None:
        frames = sample_frames(Path(video_path), N_FRAMES)
        print(f"      [{role}] {PROVIDER}: sampled {len(frames)} frames")
    if PROVIDER == "claude":
        text = _claude_generate(system, prompt, frames)
    elif PROVIDER == "gpt":
        text = _gpt_generate(system, prompt, frames)
    else:
        raise ValueError(f"backbones.generate called for provider={PROVIDER!r}")
    return _Shim(text)
