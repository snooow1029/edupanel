# Teaching-Video Judge

A backbone-swappable, 3-agent LLM evaluator for teaching videos. You drop a
video (+ the course requirement and student persona it was made for) in, and it
returns per-metric scores with timestamped evidence against a fixed pedagogy
rubric. The same pipeline runs under **Gemini, GPT, or Claude** as the judge —
selected with one env var — so you can compare backbones on the same inputs.

```
video + (course_requirement, student_persona)  ─►  3 agents  ─►  scores + evidence JSON
```

## Repository layout

| Path | Role |
|---|---|
| `evaluate.py` | The evaluator. Orchestrates the 3 agents, resolves videos, writes per-task JSON + a summary CSV. Run as a script. |
| `backbones.py` | Backbone abstraction. Selects Gemini / GPT / Claude and handles frame sampling for the non-native backbones. |
| `prompts/` | The four agent prompts (`agent1`, `agent2`, `subjective`, `subjective_text_only`) + a prompts README. |
| `criteria/teaching_video_criteria_v2.json` | The rubric (A–F 24-metric tree) the judge scores against. **Default.** |
| `criteria/teaching_video_criteria_v1.json` | The previous rubric version. **The bundled `outputs/ai_commentary_12.gemini_deployed.json` was scored with v1.** See "Rubric versions" below. |
| `inputs/pool_demo.json` | Demo input: the 12-video golden set with per-video course requirement + persona. |
| `demo_videos/*.mp4` | The 12 demo videos referenced by `pool_demo.json`. |
| `outputs/` | Reference outputs (see below). |
| `config/.env.example` | Key-name template. Copy to `config/.env` and fill in. |

## The three agents

| Agent | Sees | Job |
|---|---|---|
| **Agent 1** — content analyst (VLM) | the **video** | Watches it and produces a content map + a list of potential factual/visual issues (incl. on-screen figure/diagram correctness). |
| **Agent 2** — objective scorer (text-only) | Agent 1's output + rubric | Scores the objective metrics (e.g. A1 content accuracy, A2, C1, F1…). Its content-accuracy reasoning explicitly folds in figure/diagram errors surfaced by Agent 1. |
| **Agent 3** — persona simulator (VLM) | the **video** + persona | Role-plays the target student and scores the experiential/visual-usage metrics (C4 visual explanation power, D2 visual design, engagement…). |

Metric ownership is decided by the rubric's `evaluator` field, not by code — A1/A2
and the objective subset go to Agent 2; C4/D2 and the experiential subset go to
Agent 3.

## Switching the backbone

One env var picks the judge; nothing else changes.

```bash
VIBE_TEACH_VLM_PROVIDER=gemini   # default — native MP4 ingestion
VIBE_TEACH_VLM_PROVIDER=gpt      # VIBE_TEACH_GPT_MODEL    (default gpt-5-mini)
VIBE_TEACH_VLM_PROVIDER=claude   # VIBE_TEACH_CLAUDE_MODEL (default claude-opus-4-8)
```

Gemini ingests the MP4 natively. GPT and Claude can't, so for the video-facing
agents (1 & 3) `backbones.py` samples ~48 evenly-spaced frames with ffmpeg
and sends them as images; Agent 2 is text-only on every backbone. Tunables:
`VIBE_TEACH_VLM_FRAMES` (48), `VIBE_TEACH_VLM_MAXTOK` (8000),
`VIBE_TEACH_VLM_FRAME_WIDTH` (768).

## Rubric versions

The rubric is an **A–F, 24-metric tree** (`A1–A6, B1–B4, C1–C4, D1–D4, E1–E3,
F1–F3`). Two versions are bundled; pick with `TEACHING_CRITERIA_FILE`
(default = v2):

- **v2** (`teaching_video_criteria_v2.json`) — current default. v1 + four
  definition/anchor fixes (F2 deduction-only, C4 decoupled from correctness,
  D2 credits animation craft, F3 judged by pace/density vs Focus Time).
- **v1** (`teaching_video_criteria_v1.json`) — the previous version. **The
  bundled `outputs/ai_commentary_12.gemini_deployed.json` was scored under v1**,
  so v2 scores are not directly comparable to it. Kept for reproducibility.

Both files carry a `crosswalk_old_batch_audit_flags` appendix — a one-to-one map
from the **30 legacy batch_audit flags** (the old flat output schema, e.g.
`critical_fact_error_count`, `monotone_audio_level`) to their single canonical
home in this A–F tree (deduping constructs that used to be double/triple-counted
across dimensions). It documents lineage only; it is not itself a scoring schema.

## Running

Prereqs: `ffmpeg`/`ffprobe` on PATH, deps from `requirements.txt`, and the API
key for whichever backbone you pick. The script does **not** auto-load
`config/.env` — export it yourself.

```bash
cp config/.env.example config/.env      # then fill in the key(s) you need
set -a; . config/.env; set +a           # export keys into the environment

# Gemini (default) over the 12 demo videos, 3 passes averaged downstream:
NUM_RUNS=3 python evaluate.py

# GPT backbone:
VIBE_TEACH_VLM_PROVIDER=gpt NUM_RUNS=3 python evaluate.py

# Claude backbone:
VIBE_TEACH_VLM_PROVIDER=claude NUM_RUNS=3 python evaluate.py
```

Useful env: `INPUT_FILE` (default `inputs/pool_demo.json`), `NUM_RUNS` (passes
per video, average ≥3 — single-pass scores swing ±1–2), `MAX_CONCURRENT` (3),
`TEACHING_CRITERIA_FILE` (override the rubric).

Results land in `eval_results/concurrent_<timestamp>_finegrain_persona/` — one
JSON per (video × pass) plus a summary CSV.

## Input format

`inputs/pool_demo.json` — a pool wrapper. `video_url` may be a **local path**
(relative to repo root, as here) or a YouTube URL.

```json
{
  "videos": [
    {
      "video_url": "demo_videos/bad_mei_2.mp4",
      "title": "bad_mei_2",
      "course_requirement": "Big Concept: … Learning Goal: … Key Learning Points: …",
      "personas": [
        { "student_persona": "Grade: 7th | Focus Time: 15 min | Background Knowledge: Has: … Lacks: …" }
      ]
    }
  ]
}
```

## Outputs (reference results included)

- `outputs/sample_raw_run/*.json` — two raw per-task files straight from a run,
  showing the full agent structure (content map, potential issues, all 24
  metric scores with `[MM:SS]` evidence).
- `outputs/ai_commentary_12.gemini_deployed.json` — the deployed Gemini scoring
  of the 12-video set (curated 10 metrics A1,A2,C1,C4,D2,E1,E2,F1,F2,F3 + 4 dims).
- `outputs/ai_commentary_12.gpt.json` / `ai_commentary_12.gemini.json` — GPT and
  Gemini **3-pass averaged** scorings of the same 12 videos (each metric carries
  `score` = mean, `score_runs` = the 3 raw values, `n_runs` = 3), for
  cross-backbone comparison.

## Paper

This repository accompanies:

> **EduPanel: A Three-Agent LLM Judge for Teaching Videos — Reliability, Complementarity, and Human Trust Calibration**
> Jia-Kai Dong, Yi-Cheng Lin, Hung-yi Lee. National Taiwan University. arXiv:2607.18529 (2026).
> Paper: https://arxiv.org/abs/2607.18529 · Code: https://github.com/snooow1029/edupanel

```bibtex
@article{dong2026edupanel,
  title   = {EduPanel: A Three-Agent LLM Judge for Teaching Videos -- Reliability, Complementarity, and Human Trust Calibration},
  author  = {Dong, Jia-Kai and Lin, Yi-Cheng and Lee, Hung-yi},
  journal = {arXiv preprint arXiv:2607.18529},
  year    = {2026}
}
```
