#!/usr/bin/env python3
"""
Batch Video Audit Processor
使用 Gemini Batch API 大量處理影片評估任務
"""

import asyncio
import csv
import json
import logging
import os
import re
import shutil
import subprocess
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from google import genai
from google.genai import types

import backbones as vlm

# from video_aesthetics import (
#     computational_aesthetics_enabled_from_env,
#     get_computational_aesthetics_summary,
# )


def _quiet_http_loggers() -> None:
    """Suppress noisy INFO lines (e.g. httpx 'HTTP Request') from SDK / dependencies."""
    for name in (
        "httpx",
        "httpcore",
        "urllib3",
        "urllib3.connectionpool",
        "requests",
        "google.auth.transport.requests",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)


_quiet_http_loggers()


# ----- Gemini 多模態參數（請直接改這裡；不讀環境變數）-----
# 影片取樣 FPS：None = API 預設（約 1 FPS）；可設 0.5、2、6 等（會 clamp 至 0.05–30）
AGENT1_VIDEO_INPUT_FPS: Optional[float] = 0.5
AGENT3_VIDEO_INPUT_FPS: Optional[float] = 0.33
# Agent 2 僅文字；多數情況維持 None。若需指定：types.MediaResolution.MEDIA_RESOLUTION_*
AGENT2_MEDIA_RESOLUTION: Optional[types.MediaResolution] = None


def _gemini_generation_seed() -> Optional[int]:
    """
    固定解碼 seed，讓相同提示與 temperature 下盡可能可重現。
    環境變數 VIBE_TEACH_GEMINI_SEED：預設 \"42\"；設為 none/off 或空字串則不傳 seed（由 API 決定）。
    """
    raw = os.environ.get("VIBE_TEACH_GEMINI_SEED", "42").strip().lower()
    if raw in ("", "none", "off"):
        return None
    try:
        return int(raw)
    except ValueError:
        return 42


GEMINI_GENERATION_SEED: Optional[int] = _gemini_generation_seed()


def _agent3_text_only_from_env() -> bool:
    """若為 True：Agent 3 不上傳影片，只根據 Agent 1/2 的 JSON 證據打分。"""
    return os.environ.get("VIBE_TEACH_AGENT3_TEXT_ONLY", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _clamp_gemini_video_fps(fps: Optional[float]) -> Optional[float]:
    if fps is None:
        return None
    return max(0.05, min(30.0, float(fps)))


def _gemini_video_text_contents(
    video_file: types.File,
    text_prompt: str,
    *,
    video_fps: Optional[float] = None,
):
    """Pass video + prompt; use ``VideoMetadata(fps=…)`` when ``video_fps`` is set."""
    fps = video_fps
    if fps is None:
        return [video_file, text_prompt]
    mime = video_file.mime_type or "video/mp4"
    uri = video_file.uri
    if not uri:
        return [video_file, text_prompt]
    return [
        types.Content(
            role="user",
            parts=[
                types.Part(
                    file_data=types.FileData(file_uri=uri, mime_type=mime),
                    video_metadata=types.VideoMetadata(fps=fps),
                ),
                types.Part(text=text_prompt),
            ],
        )
    ]


def _gemini_generate_config(**kwargs) -> types.GenerateContentConfig:
    """Pass ``media_resolution=`` per call; if omitted, use ``AGENT2_MEDIA_RESOLUTION``."""
    skip_mr = kwargs.pop("skip_media_resolution", False)
    mr = kwargs.pop("media_resolution", None)
    if not skip_mr:
        if mr is None:
            mr = AGENT2_MEDIA_RESOLUTION
        if mr is not None:
            kwargs["media_resolution"] = mr
    elif mr is not None:
        kwargs["media_resolution"] = mr
    if GEMINI_GENERATION_SEED is not None and "seed" not in kwargs:
        kwargs["seed"] = GEMINI_GENERATION_SEED
    return types.GenerateContentConfig(**kwargs)


def _log_gemini_usage(agent_label: str, response) -> None:
    """Print token usage from generate_content (prompt / output / cache)."""
    um = getattr(response, "usage_metadata", None)
    if um is None:
        print(f"      [{agent_label}] usage_metadata: null")
        return
    try:
        data = um.model_dump(exclude_none=True)
        print(f"      [{agent_label}] usage_metadata: {json.dumps(data, ensure_ascii=False, default=str)}")
    except Exception:
        print(f"      [{agent_label}] usage_metadata: {um}")


# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).parent
PERSONA_CSV_FILE = PROJECT_ROOT / "persona" / "merged_course_units_with_personas_sub.csv"
EVAL_RESULTS_DIR = PROJECT_ROOT / "eval_results"
TEMP_DOWNLOAD_DIR = Path("temp_videos")
BATCH_WORK_DIR = Path("batch_work")
PROMPTS_DIR = Path(__file__).parent / "prompts"

# Create directories
TEMP_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
BATCH_WORK_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class VideoTask:
    """單個影片評估任務"""
    video_url: str
    title: str
    persona: str  # Simplified: just the student_persona string
    big_concept: str = ""
    blooms_level: str = ""
    learning_goal: str = ""
    key_learning_points: str = ""
    video_id: Optional[str] = None
    video_path: Optional[Path] = None
    file_uri: Optional[str] = None
    agent1_request_id: Optional[str] = None
    agent3_request_id: Optional[str] = None

# ============================================================================
# Helper Functions
# ============================================================================

def load_prompt(filename: str) -> str:
    """從 prompts 目錄讀取 prompt 模板"""
    prompt_path = PROMPTS_DIR / filename
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    with open(prompt_path, encoding="utf-8") as f:
        return f.read()


# ============================================================================
# Canonical criteria (single source of truth — shared with rubric_coverage_check)
# 24-metric A–F tree. v2 = v1 + 2026-06-27 fixes (F2 deduction-only, C4 decoupled
# from correctness, D2 credits animation craft, F3 pace-not-duration). v1 kept intact
# for comparison with the frozen ai_commentary_12.json. Override via TEACHING_CRITERIA_FILE.
# ============================================================================

CRITERIA_FILE = Path(os.environ.get(
    "TEACHING_CRITERIA_FILE",
    str(Path(__file__).parent / "criteria" / "teaching_video_criteria_v2.json"),
))

_CRITERIA_CACHE: Optional[Dict] = None


def load_criteria() -> Dict:
    global _CRITERIA_CACHE
    if _CRITERIA_CACHE is None:
        with open(CRITERIA_FILE, encoding="utf-8") as f:
            _CRITERIA_CACHE = json.load(f)
    return _CRITERIA_CACHE


def iter_metrics():
    """Yield (code, metric_dict) for all 24 metrics in dimension order."""
    crit = load_criteria()
    for dim in crit["dimensions"].values():
        for code, m in dim["metrics"].items():
            yield code, m


def metrics_for(evaluator: str) -> List[str]:
    """Metric codes owned by a given batch_audit agent ('objective' or 'subjective')."""
    return [c for c, m in iter_metrics() if m["evaluator"] == evaluator]


def tm_dim_groups() -> Dict[str, List[str]]:
    """{teaching-monster dim -> [metric codes]} for final 4-dim aggregation."""
    groups: Dict[str, List[str]] = {}
    for code, m in iter_metrics():
        groups.setdefault(m["tm_dim"], []).append(code)
    return groups


def render_metric_block(evaluator: str) -> str:
    """Render the markdown rubric block (definitions + 1/3/5 anchors) for a given
    agent, straight from the canonical criteria so the prompts never drift."""
    crit = load_criteria()
    lines: List[str] = []
    for dkey, dim in crit["dimensions"].items():
        sel = [(c, m) for c, m in dim["metrics"].items() if m["evaluator"] == evaluator]
        if not sel:
            continue
        lines.append(f"### Dimension {dkey}: {dim['title']}")
        for code, m in sel:
            lines.append(f"- **{code}**: {m['definition']}")
            a = m.get("anchors", {})
            if a:
                anchor_txt = "  ".join(f"[{k}] {a[k]}" for k in ("1", "3", "5") if k in a)
                lines.append(f"  - Anchors: {anchor_txt}")
        lines.append("")
    return "\n".join(lines).strip()


def render_metric_scores_skeleton(evaluator: str) -> str:
    """Render the `metric_scores` JSON skeleton for a given agent straight from
    the criteria file, so the prompt's output example always matches the active
    rubric (v1 or tier-2) — no hardcoded code list."""
    codes = metrics_for(evaluator)
    lines = []
    for i, c in enumerate(codes):
        comma = "," if i < len(codes) - 1 else ""
        lines.append(f'    "{c}": {{ "score": 3, "evidence": "..." }}{comma}')
    return "{\n" + "\n".join(lines) + "\n  }"


def aggregate_tm_dims(metric_scores: Dict[str, float]) -> Dict[str, float]:
    """Mean the 1–5 metric scores into the 4 Teaching-Monster reporting dims.
    Missing metrics are skipped (a dim with no scored metric defaults to 3.0)."""
    groups = tm_dim_groups()
    out: Dict[str, float] = {}
    for tm in ("accuracy", "pedagogical_logic", "adaptation", "engagement"):
        vals = [float(metric_scores[c]) for c in groups.get(tm, []) if isinstance(metric_scores.get(c), (int, float))]
        out[tm] = round(sum(vals) / len(vals), 2) if vals else 3.0
    # Legacy CSV/key names: pedagogical_logic->logic, adaptation->adaptability
    return {
        "accuracy": out["accuracy"],
        "logic": out["pedagogical_logic"],
        "adaptability": out["adaptation"],
        "engagement": out["engagement"],
    }

def _get_written_text_legibility_audit(agent1_result: Dict) -> Dict:
    """Agent 1 text-legibility audit: under presentation_analysis, with legacy key fallback."""
    if not isinstance(agent1_result, dict):
        return {}
    pres = agent1_result.get("presentation_analysis") or {}
    if isinstance(pres, dict):
        aud = pres.get("written_text_legibility_audit") or pres.get("visual_accessibility_audit")
        if isinstance(aud, dict):
            return aud
    top = agent1_result.get("written_text_legibility_audit") or agent1_result.get("visual_accessibility_audit")
    return top if isinstance(top, dict) else {}


def normalize_adaptability_flags_inplace(adaptability_flags: Dict) -> None:
    """Copy legacy Agent 3 adaptability keys to current names (mutates dict in place)."""
    if not isinstance(adaptability_flags, dict):
        return
    if "written_text_legibility_level" not in adaptability_flags and "visual_accessibility_level" in adaptability_flags:
        adaptability_flags["written_text_legibility_level"] = adaptability_flags.get("visual_accessibility_level", 0)
    if "written_text_legibility_evidence" not in adaptability_flags and "accessibility_evidence" in adaptability_flags:
        adaptability_flags["written_text_legibility_evidence"] = adaptability_flags.get("accessibility_evidence", "")
    if "visual_pairing_level" not in adaptability_flags and "ineffective_visual_representation_level" in adaptability_flags:
        adaptability_flags["visual_pairing_level"] = adaptability_flags.get("ineffective_visual_representation_level", 0)
    if "visual_pairing_evidence" not in adaptability_flags and "ineffective_visual_evidence" in adaptability_flags:
        adaptability_flags["visual_pairing_evidence"] = adaptability_flags.get("ineffective_visual_evidence", "")


def format_agent3_narration_slide_claim(presentation: Dict) -> str:
    """
    Single narration–slide alignment summary for Agent 3 / subjective_prompt.
    Prefers structured visual_content_alignment; falls back to legacy video_audio_alignment string.
    """
    if not isinstance(presentation, dict):
        return "Not specified"
    vca = presentation.get("visual_content_alignment")
    if isinstance(vca, dict):
        score = (vca.get("score") or "").strip()
        obs = (vca.get("observation") or "").strip()
        if score and obs:
            return f"{score} — {obs}"
        if obs:
            return obs
        if score:
            return score
    legacy = presentation.get("video_audio_alignment")
    if legacy is not None and str(legacy).strip():
        return str(legacy).strip()
    return "Not specified"


def normalize_title(s: str) -> str:
    """Normalize Unicode quotes and whitespace for robust matching"""
    return (s.strip()
            .replace("\u2019", "'")  # Unicode right single quote (U+2019) → ASCII
            .replace("\u2018", "'")  # Unicode left single quote (U+2018) → ASCII
            .replace("\u201d", '"')  # Unicode right double quote (U+201D) → ASCII
            .replace("\u201c", '"')  # Unicode left double quote (U+201C) → ASCII
            .replace("\u2013", "-")  # En dash (U+2013) → hyphen
            .replace("\u2014", "-")) # Em dash (U+2014) → hyphen


def clip_score_1_5(score: float) -> float:
    """Final reported scores must lie in [1, 5]."""
    if not isinstance(score, (int, float)):
        return 3.0
    return round(max(1.0, min(5.0, float(score))), 2)


# Severity level fields that participate in +1 bonus counting (one point toward 5.0, split 1/N each).
# Must match agent2_prompt.md +1 anchors: (1) scaffolding failure, (2) pure calc bias,
# (3) content completeness, (4) explanatory depth; accuracy also (6) visual_alignment_issue_level (figure correctness from Agent 2; Agent 1: on_screen_figure_diagram_correctness).
# Excluded from bonus: title mismatch (still penalizes normally; level==1 does not add bonus).
N_BONUS_FIELDS_ACCURACY = 5
N_BONUS_FIELDS_LOGIC = 4
# Subjective: only flags with meaningful "beyond expectation" can contribute +1 toward 5.0 (each +1 adds 1/N before headroom cap).
# Excluded from +1: jargon_overload, written_text_legibility, ai_generated_fatigue, visual_clutter, slide_layout, decorative_eye_candy.
N_BONUS_FIELDS_ADAPTABILITY = 4  # prereq, pacing, scaffolding, visual_pairing_level
N_BONUS_FIELDS_ENGAGEMENT = 4    # monotone, disconnect, visual_signaling, speech_intelligibility


def _apply_bonus_toward_five(score: float, num_plus_one: int, n_fields: int) -> float:
    """
    Add bonus from agent-rated +1 (beyond expectation) flags toward 5.0.
    Each +1 contributes 1/n_fields on the 4→5 band; total raw bonus is min(1.0, num_plus_one/n_fields).
    Then capped by remaining headroom (5 - score). Result is clipped to [1, 5].
    """
    if num_plus_one <= 0 or n_fields <= 0:
        return clip_score_1_5(score)
    s = float(score)
    headroom = max(0.0, 5.0 - s)
    raw_bonus = min(1.0, float(num_plus_one) / float(n_fields))
    bonus = min(headroom, raw_bonus)
    return clip_score_1_5(s + bonus)


def _count_agent_plus_one_levels(*values) -> int:
    """Count INTEGER 1 (beyond expectation on agent scale 1, 0, -1, -2, -3)."""
    n = 0
    for v in values:
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)) and int(v) == 1:
            n += 1
    return n


# ============================================================================
# Video Download (Async)
# ============================================================================

async def download_video_async(url: str, task_idx: int, total: int) -> Tuple[str, Path]:
    """異步取得影片：本地檔則複製進 temp_videos；否則用 yt-dlp 下載 YouTube。"""
    output_tmpl = str(TEMP_DOWNLOAD_DIR / "%(id)s.%(ext)s")

    # --- Local-file support: if `url` is an existing local path (or a
    # file:// URI), copy it into TEMP_DOWNLOAD_DIR and skip yt-dlp. We copy
    # (not symlink) so the PHASE 5 cleanup deletes the temp copy, never the
    # caller's original file. ---
    local_candidate = url[7:] if url.startswith("file://") else url
    if os.path.isfile(local_candidate):
        src = Path(local_candidate)
        video_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", src.stem) or "local_video"
        TEMP_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        dest = TEMP_DOWNLOAD_DIR / f"{video_id}.mp4"
        if not dest.exists():
            shutil.copy2(src, dest)
        print(f"[{task_idx}/{total}] Using local video: {src} -> {dest.name}")
        return video_id, dest

    print(f"[{task_idx}/{total}] Downloading video: {url}")

    try:
        # Get video ID first
        cmd_id = ["yt-dlp", "--get-id", url]
        proc_id = await asyncio.create_subprocess_exec(
            *cmd_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc_id.communicate()

        if proc_id.returncode != 0:
            error_msg = stderr.decode().strip()
            raise RuntimeError(f"Failed to get video ID: {error_msg}")

        video_id = stdout.decode().strip()

        if not video_id:
            raise RuntimeError("Empty video ID returned")

        # Check if already downloaded
        video_path = TEMP_DOWNLOAD_DIR / f"{video_id}.mp4"
        if video_path.exists():
            print(f"   ✓ Video already exists: {video_id}")
            return video_id, video_path

        # Download video
        cmd_dl = [
            "yt-dlp",
            "-f", "best[height<=720][ext=mp4]",
            "--output", output_tmpl,
            url
        ]
        proc_dl = await asyncio.create_subprocess_exec(
            *cmd_dl,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout_dl, stderr_dl = await proc_dl.communicate()
        
        if proc_dl.returncode != 0:
            error_msg = stderr_dl.decode().strip()
            raise RuntimeError(f"Failed to download video: {error_msg}")
        
        if not video_path.exists():
            raise RuntimeError(f"Video file not found after download: {video_path}")
        
        print(f"   ✓ Downloaded: {video_id}")
        return video_id, video_path
        
    except Exception as e:
        print(f"   ✗ Error downloading {url}: {e}")
        raise

# ============================================================================
# Curriculum / Persona Parsing (raw text → structured fields)
# ============================================================================

# Mapping of possible label variations → canonical field name
# Order matters: longer labels first so "Key Knowledge Points" matches before "Key"
_COURSE_FIELD_MAP = [
    ("key learning points", "key_learning_points"),
    ("key knowledge points", "key_learning_points"),
    ("bloom's taxonomy", "blooms_level"),
    ("blooms taxonomy", "blooms_level"),
    ("learning goal", "learning_goal"),
    ("big concept", "big_concept"),
    ("topic", "title"),
    ("bloom", "blooms_level"),
]

_PERSONA_FIELD_LABELS = [
    "background knowledge",
    "focus time",
    "grade",
]


def _split_inline_fields(text: str, field_map: list) -> list:
    """Split a single string into (label, value) pairs by scanning for known labels.

    Works whether fields are separated by newlines, pipes, or just spaces.
    Handles quotes and colons inside values correctly because we only split
    at positions where a known label + ':' appears.
    """
    # Build a list of (position, label_text, field_key) for all labels found
    lower = text.lower()
    hits = []
    for label, field in field_map:
        search_from = 0
        while True:
            pos = lower.find(label + ":", search_from)
            if pos == -1:
                break
            hits.append((pos, label, field))
            search_from = pos + len(label) + 1
    # Sort by position
    hits.sort(key=lambda x: x[0])
    # Extract values
    pairs = []
    for i, (pos, label, field) in enumerate(hits):
        val_start = pos + len(label) + 1  # skip "Label:"
        val_end = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        value = text[val_start:val_end].strip().rstrip("|").strip()
        pairs.append((field, value))
    return pairs


def parse_course_requirement(text: str) -> Dict[str, str]:
    """Parse a course requirement block into structured fields.

    Accepts BOTH multi-line and single-line (all fields concatenated) formats.
    Handles quotes inside values.

    Returns dict with keys: title, big_concept, blooms_level, learning_goal,
    key_learning_points.  Missing fields default to "".
    """
    result: Dict[str, str] = {
        "title": "",
        "big_concept": "",
        "blooms_level": "",
        "learning_goal": "",
        "key_learning_points": "",
    }
    if not text or not text.strip():
        return result

    for field, value in _split_inline_fields(text, _COURSE_FIELD_MAP):
        result[field] = value
    return result


def parse_student_persona(text: str) -> str:
    """Normalise a student persona block into a single pipe-separated string.

    Accepts BOTH multi-line and single-line formats:
        "Grade: 8th grade Focus Time: 10 minutes Background Knowledge: ..."
        or
        "Grade: 8th grade\\nFocus Time: 10 minutes\\nBackground Knowledge: ..."

    Returns: "Grade: 8th grade | Focus Time: 10 minutes | Background Knowledge: ..."
    If already pipe-separated, return as-is.
    """
    if not text or not text.strip():
        return ""
    # Already pipe-separated → passthrough
    if "|" in text:
        return text.strip()
    # Build field map for persona labels
    persona_map = [(label, label) for label in _PERSONA_FIELD_LABELS]
    pairs = _split_inline_fields(text, persona_map)
    if not pairs:
        return text.strip()
    # Reconstruct as "Label: value | Label: value | ..."
    parts = []
    for label, value in pairs:
        # Capitalise label nicely
        nice_label = label.title()
        parts.append(f"{nice_label}: {value}")
    return " | ".join(parts)


# ============================================================================
# Persona Loading
# ============================================================================

def load_personas_by_title(title_en: str) -> List[str]:
    """從 CSV 載入匹配的 personas（只返回 student_persona 字符串）"""
    personas = []
    
    if not PERSONA_CSV_FILE.exists():
        print(f"Error: Persona CSV file not found: {PERSONA_CSV_FILE}")
        return personas
    
    search_title = normalize_title(title_en)
    
    try:
        with open(PERSONA_CSV_FILE, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                csv_title_raw = row.get("title_en", "")
                csv_title = normalize_title(csv_title_raw)
                
                if csv_title == search_title:
                    student_persona = row.get("student_persona", "").strip()
                    if student_persona:
                        personas.append(student_persona)
    
    except Exception as e:
        print(f"Error reading CSV: {e}")
        traceback.print_exc()
    
    return personas

# ============================================================================
# Async Concurrent Processor Class
# ============================================================================

class AsyncConcurrentProcessor:
    """使用 asyncio 並發處理多個影片"""
    
    def __init__(
        self,
        api_key: str,
        max_concurrent: int = 3,
        num_runs: int = 1,
    ):
        self.client = genai.Client(api_key=api_key)
        self.max_concurrent = max_concurrent
        self.num_runs = num_runs  # 每個任務運行的次數（用於計算一致性）
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        # Load prompt templates
        print("Loading prompt templates...")
        self.agent1_prompt_template = load_prompt("agent1_prompt.md")
        self.agent2_prompt_template = load_prompt("agent2_prompt.md")
        self.agent3_text_only = _agent3_text_only_from_env()
        _subj_file = (
            "subjective_prompt_text_only.md"
            if self.agent3_text_only
            else "subjective_prompt.md"
        )
        self.subjective_prompt_template = load_prompt(_subj_file)
        if self.agent3_text_only:
            print(
                "✓ Agent 3 TEXT-ONLY mode: ",
                _subj_file,
                " (set VIBE_TEACH_AGENT3_TEXT_ONLY=0 to use video)\n",
                sep="",
            )
        else:
            print("✓ Prompts loaded successfully\n")
        
        # System instructions
        self.agent1_system_instruction = """You are a METICULOUS EDUCATIONAL CONTENT ANALYST with expertise in Senior High School (AP/IB level) science and math education. 
Your dual role:
1. MAP what is taught: Document every concept, formula, or definition chronologically with its level of detail
2. IDENTIFY potential issues: Log errors or gaps based ONLY on High School standards

Do NOT assign final scores - that is Agent 2's job.

KNOWLEDGE BOUNDARY:
- Use the standard curriculum for students aged 15-18 (e.g., AP Physics/Biology, IB Science).
- DO NOT use university-level rigor or advanced theories (e.g., Quantum Electrodynamics, Molecular Orbital Theory) to invalidate correct high school level simplifications. 
- A simplified model (like the Bohr model in chemistry or Newtonian mechanics in physics) is considered CORRECT if it is standard at the High School level."""
    
    async def prepare_tasks(self, input_config: List[Dict]) -> List[VideoTask]:
        """
        準備所有任務
        input_config: [{"video_url": "...", "title": "..."}, ...]
        """
        print("=" * 80)
        print("PHASE 1: TASK PREPARATION")
        print("=" * 80)
        
        tasks = []
        
        # Group by video URL to avoid duplicate downloads
        url_to_tasks = {}
        
        for idx, config in enumerate(input_config, 1):
            video_url = config["video_url"]

            # --- Curriculum fields: support 3 input modes ---
            # Mode A: raw "course_requirement" text block → parse into fields
            # Mode B: pre-split structured fields (title, big_concept, ...)
            # Mode C: legacy (title only)
            if "course_requirement" in config and config["course_requirement"]:
                parsed = parse_course_requirement(config["course_requirement"])
                title = parsed["title"] or config.get("title", "")
                big_concept = parsed["big_concept"]
                blooms_level = parsed["blooms_level"]
                learning_goal = parsed["learning_goal"]
                key_learning_points = parsed["key_learning_points"]
            else:
                title = config.get("title", "")
                big_concept = config.get("big_concept", "")
                blooms_level = config.get("blooms_level", "")
                learning_goal = config.get("learning_goal", "")
                key_learning_points = config.get("key_learning_points", "")

            # --- Persona: support raw text or pre-formatted list ---
            if "student_persona" in config and config["student_persona"]:
                # Single raw persona text → normalise and wrap in list
                personas = [parse_student_persona(config["student_persona"])]
            elif "personas" in config and config["personas"]:
                personas = [parse_student_persona(p) for p in config["personas"]]
            else:
                # Legacy: load from CSV by title
                personas = load_personas_by_title(title)
                if not personas:
                    print(f"⚠️  [{idx}] No personas found for: {title}")
                    continue

            print(f"[{idx}] {title}")
            print(f"    Personas: {len(personas)}")

            # Create task for each persona
            for persona in personas:
                task = VideoTask(
                    video_url=video_url,
                    title=title,
                    persona=persona,
                    big_concept=big_concept,
                    blooms_level=blooms_level,
                    learning_goal=learning_goal,
                    key_learning_points=key_learning_points,
                )
                tasks.append(task)
                
                # Group by URL
                if video_url not in url_to_tasks:
                    url_to_tasks[video_url] = []
                url_to_tasks[video_url].append(task)
        
        print(f"\n✓ Total tasks prepared: {len(tasks)}")
        print(f"✓ Unique videos: {len(url_to_tasks)}\n")
        
        # Download all unique videos asynchronously
        print("=" * 80)
        print("PHASE 2: VIDEO DOWNLOAD (Async)")
        print("=" * 80)
        
        download_tasks = []
        urls = list(url_to_tasks.keys())
        
        for idx, url in enumerate(urls, 1):
            download_tasks.append(download_video_async(url, idx, len(urls)))
        
        # Execute all downloads in parallel
        download_results = await asyncio.gather(*download_tasks, return_exceptions=True)
        
        # Map results back to tasks
        for url, result in zip(urls, download_results):
            if isinstance(result, Exception):
                print(f"✗ Failed to download {url}: {result}")
                continue
            
            video_id, video_path = result
            
            # Update all tasks with this URL
            for task in url_to_tasks[url]:
                task.video_id = video_id
                task.video_path = video_path
        
        print(f"\n✓ Downloaded {len([r for r in download_results if not isinstance(r, Exception)])} videos\n")
        
        return tasks
    
    def run_agent1_sync(self, video_path: Path, title: str,
                        big_concept: str = "", blooms_level: str = "",
                        learning_goal: str = "", key_learning_points: str = "") -> Dict:
        """Agent 1: 內容分析（同步）"""
        try:
            agent1_prompt = self.agent1_prompt_template.format(
                video_title=title,
                big_concept=big_concept or "(not provided)",
                blooms_level=blooms_level or "(not provided)",
                learning_goal=learning_goal or "(not provided)",
                key_learning_points=key_learning_points or "(not provided)",
            )

            if vlm.PROVIDER != "gemini":
                # Claude / GPT: frames sampled from the video, sent as images.
                response = vlm.generate(
                    role="Agent 1",
                    system=self.agent1_system_instruction,
                    prompt=agent1_prompt,
                    video_path=video_path,
                )
            else:
                # Upload video (Gemini native path — unchanged)
                video_file = self.client.files.upload(
                    file=str(video_path),
                    config={"mime_type": "video/mp4"}
                )

                # Wait for processing
                while video_file.state.name == "PROCESSING":
                    time.sleep(2)
                    video_file = self.client.files.get(name=video_file.name)

                if video_file.state.name == "FAILED":
                    raise ValueError(f"Video upload failed: {video_path}")

                response = self.client.models.generate_content(
                    model="gemini-3-flash-preview",
                    contents=_gemini_video_text_contents(
                        video_file,
                        agent1_prompt,
                        video_fps=_clamp_gemini_video_fps(AGENT1_VIDEO_INPUT_FPS),
                    ),
                    config=_gemini_generate_config(
                        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
                        system_instruction=self.agent1_system_instruction,
                        temperature=0.0,
                        response_mime_type="application/json",
                    ),
                )
                _log_gemini_usage("Agent 1", response)

                # Clean up
                self.client.files.delete(name=video_file.name)

            result = response.parsed
            if result is None and response.text:
                try:
                    # Clean response text: remove markdown code blocks, leading/trailing whitespace
                    cleaned_text = response.text.strip()
                    if cleaned_text.startswith("```json"):
                        cleaned_text = cleaned_text[7:]  # Remove ```json
                    if cleaned_text.startswith("```"):
                        cleaned_text = cleaned_text[3:]  # Remove ```
                    if cleaned_text.endswith("```"):
                        cleaned_text = cleaned_text[:-3]  # Remove trailing ```
                    cleaned_text = cleaned_text.strip()
                    
                    result = json.loads(cleaned_text)
                except json.JSONDecodeError as je:
                    print(f"      ⚠️  Agent 1 JSON parse error: {str(je)}")
                    print(f"      First 200 chars: {response.text[:200]}")
                    result = {"error": "JSON parse failed", "raw": response.text[:500]}
            
            # Gemini occasionally wraps the object in a list — unwrap if needed
            if isinstance(result, list):
                result = result[0] if result else {"error": "Empty list response"}

            return result or {"error": "Empty response"}

        except Exception as e:
            print(f"      ✗ Agent 1 error: {e}")
            return {"error": str(e)}

    def run_agent2_sync(self, title: str, agent1_output: Dict,
                        blooms_level: str = "", key_learning_points: str = "") -> Dict:
        """Agent 2: 評分判斷（同步）"""
        agent1_text = json.dumps(agent1_output, indent=2, ensure_ascii=False)

        prompt = self.agent2_prompt_template.format(
            video_title=title,
            agent1_output=agent1_text,
            blooms_level=blooms_level or "(not provided)",
            key_learning_points=key_learning_points or "(not provided)",
            metric_block=render_metric_block("objective"),
            metric_scores_skeleton=render_metric_scores_skeleton("objective"),
        )

        # # DEBUG: print full Agent 2 prompt
        # print("\n" + "=" * 60 + " AGENT 2 PROMPT START " + "=" * 60)
        # print(prompt)
        # print("=" * 60 + " AGENT 2 PROMPT END " + "=" * 60 + "\n")

        try:
            if vlm.PROVIDER != "gemini":
                response = vlm.generate(
                    role="Agent 2",
                    system="You are a strict scoring judge.",
                    prompt=prompt,
                )
            else:
                response = self.client.models.generate_content(
                    model="gemini-3-flash-preview",
                    contents=[prompt],
                    config=_gemini_generate_config(
                        system_instruction="You are a strict scoring judge.",
                        temperature=0.0,
                        response_mime_type="application/json",
                    ),
                )
                _log_gemini_usage("Agent 2", response)

            result = response.parsed
            if result is None and response.text:
                try:
                    # Clean response text: remove markdown code blocks, leading/trailing whitespace
                    cleaned_text = response.text.strip()
                    if cleaned_text.startswith("```json"):
                        cleaned_text = cleaned_text[7:]  # Remove ```json
                    if cleaned_text.startswith("```"):
                        cleaned_text = cleaned_text[3:]  # Remove ```
                    if cleaned_text.endswith("```"):
                        cleaned_text = cleaned_text[:-3]  # Remove trailing ```
                    cleaned_text = cleaned_text.strip()
                    
                    result = json.loads(cleaned_text)
                except json.JSONDecodeError as je:
                    print(f"      ⚠️  Agent 2 JSON parse error: {str(je)}")
                    print(f"      First 200 chars: {response.text[:200]}")
                    result = {"error": "JSON parse failed", "raw": response.text[:500]}

            if isinstance(result, list):
                result = result[0] if result else {"error": "Empty list response"}

            return self._calculate_agent2_scores(result or {"error": "Empty response"})

        except Exception as e:
            print(f"      ✗ Agent 2 error: {e}")
            return {"error": str(e)}
    
    def _extract_metric_scores(self, result: Dict, evaluator: str) -> Dict[str, int]:
        """Flatten an agent's `metric_scores` block into {code: int 1-5} for its
        owned metrics, defaulting missing/invalid to 3 (Adequate)."""
        ms = result.get("metric_scores", {}) or {}
        flat: Dict[str, int] = {}
        for code in metrics_for(evaluator):
            v = ms.get(code)
            if isinstance(v, dict):
                v = v.get("score")
            try:
                flat[code] = max(1, min(5, int(round(float(v)))))
            except (TypeError, ValueError):
                flat[code] = 3
        return flat

    def _extract_objective_scores(self, result: Dict) -> Dict:
        """New (canonical-criteria) objective path: store the 9 objective metric
        scores and apply the A1 hard floors (critical errors / non-English)."""
        flat = self._extract_metric_scores(result, "objective")
        lang = str(result.get("primary_language", "english")).strip().lower()
        crit = int(result.get("critical_fact_error_count", 0) or 0)
        if "A1_factual_accuracy" in flat:
            if lang in ("mixed", "non_english"):
                flat["A1_factual_accuracy"] = 1
            elif crit >= 1:
                flat["A1_factual_accuracy"] = min(flat["A1_factual_accuracy"], 2)
        result["objective_metric_scores"] = flat
        return result

    def _extract_subjective_scores(self, result: Dict) -> Dict:
        """New (canonical-criteria) subjective path: store the 15 experiential metric scores."""
        result["subjective_metric_scores"] = self._extract_metric_scores(result, "subjective")
        return result

    def _calculate_agent2_scores(self, result: Dict) -> Dict:
        """
        Canonical-criteria path (24-metric A–F). If Agent 2 returned `metric_scores`,
        flatten + floor them. (Legacy flag-penalty engine below kept only as fallback
        for old-format responses that still carry pedagogical_depth/etc.)
        """
        if isinstance(result.get("metric_scores"), dict):
            return self._extract_objective_scores(result)
        try:
            def sev_penalty(level, p1=0.5, p2=1.0, p3=2.0):
                """1 = bonus only (no penalty). 0 = none. -1/-2/-3 = penalties. Legacy +2/+3 still supported."""
                level = int(level) if isinstance(level, (int, float)) else 0
                if level == 0:
                    return 0.0
                if level == 1:
                    return 0.0
                if level > 1:
                    idx = min(level, 3)
                    return [0, p1, p2, p3][idx]
                idx = abs(level)
                return [0, p1, p2, p3][min(idx, 3)]

            ped  = result.get("pedagogical_depth", {})
            comp = result.get("completeness", {})
            acc  = result.get("accuracy_flags", {})
            log  = result.get("logic_flags", {})

            # ── ACCURACY SCORE ──────────────────────────────────────────
            accuracy = 4.0
            acc_steps = ["Base: 4.0"]
            score_cap = 4.0

            # Pedagogical depth (shared with logic)
            fd = sev_penalty(ped.get("scaffolding_failure_level", 0),   0.5, 1, 1.5)
            pc = sev_penalty(ped.get("pure_calculation_bias_level", 0), 0.3, 0.6, 1)
            for name, pen in [("Scaffolding Failure", fd), ("Pure Calc Bias", pc)]:
                if pen:
                    accuracy -= pen
                    acc_steps.append(f"{name}: -{pen:.1f}")
            if abs(int(ped.get("pure_calculation_bias_level", 0))) >= 2:
                score_cap = min(score_cap, 2.5)

            cc_level = int(comp.get("content_completeness_level", 0))
            # if abs(cc_level) == 3:
            #     score_cap = min(score_cap, 1.0)
            cc = sev_penalty(cc_level,                                           0.5, 1.0, 1.5)
            ed = sev_penalty(comp.get("explanatory_depth_level", 0),            0.5, 1.5, 2.0)
            for name, pen in [("Content Completeness", cc), ("Explanatory Depth", ed)]:
                if pen:
                    accuracy -= pen
                    acc_steps.append(f"{name}: -{pen:.1f}")

            tm = sev_penalty(acc.get("title_depth_mismatch_level", 0), 0.5, 2, 4)
            va = sev_penalty(acc.get("visual_alignment_issue_level", 0), 0.0, 0.5, 1.0)
            for name, pen in [("Title/Depth Mismatch", tm), ("Visual Alignment Issue", va)]:
                if pen:
                    accuracy -= pen
                    acc_steps.append(f"{name}: -{pen:.1f}")

            crit_errors = int(acc.get("critical_fact_error_count", 0))
            minor_slips  = int(acc.get("minor_slip_count", 0))
            if crit_errors:
                pen = crit_errors * 0.3
                accuracy -= pen
                acc_steps.append(f"Critical Errors x{crit_errors}: -{pen:.1f}")
            if minor_slips:
                pen = minor_slips * 0.2
                accuracy -= pen
                acc_steps.append(f"Minor Slips x{minor_slips}: -{pen:.1f}")

            accuracy = round(min(score_cap, max(0.0, accuracy)), 2)
            n_acc_bonus = _count_agent_plus_one_levels(
                ped.get("scaffolding_failure_level", 0),
                ped.get("pure_calculation_bias_level", 0),
                comp.get("content_completeness_level", 0),
                comp.get("explanatory_depth_level", 0),
                acc.get("visual_alignment_issue_level", 0),
            )
            accuracy = _apply_bonus_toward_five(accuracy, n_acc_bonus, N_BONUS_FIELDS_ACCURACY)
            acc_steps.append(f"= {accuracy:.2f}" + (f" (+1×{n_acc_bonus})" if n_acc_bonus else ""))

            # ── LOGIC SCORE ─────────────────────────────────────────────
            logic = 4.0
            log_steps = ["Base: 4.0"]
            logic_cap = 4.0

            if int(ped.get("scaffolding_failure_level", 0)) <= -3:
                logic_cap = 2.0
                log_steps.append("Scaffolding Failure Cap: max 2.0")

            if abs(int(ped.get("pure_calculation_bias_level", 0))) >= 2:
                logic_cap = min(logic_cap, 2.5)

            if abs(cc_level) == 3:
                logic_cap = min(logic_cap, 1.0)

            for name, pen in [("Scaffolding Failure", fd), ("Pure Calc Bias", pc),
                               ("Content Completeness", cc), ("Explanatory Depth", ed)]:
                if pen:
                    logic -= pen
                    log_steps.append(f"{name}: -{pen:.1f}")

            ci = int(log.get("causal_inconsistency_count", 0))
            io = int(log.get("information_overload_count", 0))
            so = int(log.get("sequence_disorder_count", 0))
            for name, count, unit in [("Causal Inconsistency", ci, 0.4), ("Info Overload", io, 0.2),
                                       ("Sequence Disorder", so, 0.4)]:
                if count:
                    pen = count * unit
                    logic -= pen
                    log_steps.append(f"{name} x{count}: -{pen:.1f}")

            # A4 — explicit learning objectives (level-based, like completeness)
            lo = sev_penalty(log.get("learning_objectives_level", 0), 0.3, 0.6, 1.0)
            if lo:
                logic -= lo
                log_steps.append(f"Learning Objectives: -{lo:.1f}")

            logic = round(min(logic_cap, max(0.0, logic)), 2)
            n_log_bonus = _count_agent_plus_one_levels(
                ped.get("scaffolding_failure_level", 0),
                ped.get("pure_calculation_bias_level", 0),
                comp.get("content_completeness_level", 0),
                comp.get("explanatory_depth_level", 0),
            )
            logic = _apply_bonus_toward_five(logic, n_log_bonus, N_BONUS_FIELDS_LOGIC)
            log_steps.append(f"= {logic:.2f}" + (f" (+1×{n_log_bonus})" if n_log_bonus else ""))

            # ── LANGUAGE HARD RULE ──────────────────────────────────────
            # If Agent detected non-English content, force accuracy to 1.0
            # (overrides all other flag-based calculations). Logic is unaffected.
            primary_lang = str(result.get("primary_language", "english")).strip().lower()
            if primary_lang in ("mixed", "non_english"):
                accuracy = 1.0
                acc_steps.append(f"Language Hard Rule ({primary_lang}): accuracy forced to 1.0")

            result["accuracy_score"] = clip_score_1_5(accuracy)
            result["logic_score"]    = clip_score_1_5(logic)
            result["score_breakdown"] = {
                "accuracy_steps": " → ".join(acc_steps),
                "logic_steps":    " → ".join(log_steps),
            }
            return result

        except Exception as e:
            print(f"      ⚠️  Agent 2 score calculation error: {e}")
            result.setdefault("accuracy_score", clip_score_1_5(2.0))
            result.setdefault("logic_score",    clip_score_1_5(2.0))
            return result
    
    def _calculate_deterministic_scores(self, result: Dict) -> Dict:
        """
        Canonical-criteria path (24-metric A–F). If Agent 3 returned `metric_scores`,
        flatten them. (Legacy flag-penalty engine below kept only as fallback.)
        """
        if isinstance(result.get("metric_scores"), dict):
            return self._extract_subjective_scores(result)
        try:
            audit_log = result.setdefault("audit_log", {})

            adaptability_flags = audit_log.get("adaptability_flags")
            if not isinstance(adaptability_flags, dict):
                adaptability_flags = {}
            engagement_flags = audit_log.get("engagement_flags")
            if not isinstance(engagement_flags, dict):
                engagement_flags = {}

            # Fallback: LLM often flattens flags onto audit_log top level — hoist into nested dicts
            # and use pop() so we do not leave duplicate keys. Must re-assign nested dicts below so
            # merges are visible to _check_agent3_scores_valid (previously a fresh {} was not
            # attached to audit_log when adaptability_flags was missing).
            _adaptability_keys = [
                "jargon_overload_level", "prerequisite_gap_level",
                "pacing_mismatch_level",
                "written_text_legibility_level", "visual_accessibility_level",
                "missing_scaffolding_level",
                "visual_pairing_level", "ineffective_visual_representation_level",
            ]
            _adaptability_evidence = [
                "jargon_evidence", "prerequisite_evidence", "pacing_evidence",
                "written_text_legibility_evidence", "accessibility_evidence",
                "scaffolding_evidence", "visual_pairing_evidence", "ineffective_visual_evidence",
            ]
            for _k in _adaptability_keys:
                if _k not in adaptability_flags and _k in audit_log:
                    adaptability_flags[_k] = audit_log.pop(_k)
                    print(f"      ⚠️  Fallback: moved audit_log.{_k} → adaptability_flags")
            for _k in _adaptability_evidence:
                if _k not in adaptability_flags and _k in audit_log:
                    adaptability_flags[_k] = audit_log.pop(_k)
                    print(f"      ⚠️  Fallback: moved audit_log.{_k} → adaptability_flags")

            _engagement_keys = [
                "monotone_audio_level", "audio_continuity_level", "speech_intelligibility_level",
                "ai_generated_fatigue_level",
                "visual_clutter_level", "slide_layout_level", "disconnect_level",
                "decorative_eye_candy_level",
                "active_learning_level", "narrative_agency_level", "segmenting_level",
            ]
            _engagement_evidence = [
                "monotone_evidence", "audio_continuity_evidence", "speech_intelligibility_evidence",
                "ai_fatigue_evidence", "clutter_evidence", "slide_layout_evidence",
                "disconnect_evidence", "decorative_eye_candy_evidence",
                "active_learning_evidence", "narrative_agency_evidence", "segmenting_evidence",
            ]
            for _k in _engagement_keys:
                if _k not in engagement_flags and _k in audit_log:
                    engagement_flags[_k] = audit_log.pop(_k)
                    print(f"      ⚠️  Fallback: moved audit_log.{_k} → engagement_flags")
            for _k in _engagement_evidence:
                if _k not in engagement_flags and _k in audit_log:
                    engagement_flags[_k] = audit_log.pop(_k)
                    print(f"      ⚠️  Fallback: moved audit_log.{_k} → engagement_flags")

            if "ai_generated_fatigue" in audit_log and "ai_generated_fatigue" not in engagement_flags:
                engagement_flags["ai_generated_fatigue"] = audit_log.get("ai_generated_fatigue", False)
                engagement_flags["ai_fatigue_evidence"] = audit_log.get("ai_fatigue_evidence", "")

            audit_log["adaptability_flags"] = adaptability_flags
            audit_log["engagement_flags"] = engagement_flags

            normalize_adaptability_flags_inplace(adaptability_flags)

            for lk, ek in (
                ("jargon_overload_level", "jargon_evidence"),
                ("prerequisite_gap_level", "prerequisite_evidence"),
                ("pacing_mismatch_level", "pacing_evidence"),
                ("written_text_legibility_level", "written_text_legibility_evidence"),
                ("missing_scaffolding_level", "scaffolding_evidence"),
                ("visual_pairing_level", "visual_pairing_evidence"),
            ):
                adaptability_flags.setdefault(lk, 0)
                adaptability_flags.setdefault(ek, "")

            for lk, ek in (
                ("monotone_audio_level", "monotone_evidence"),
                ("audio_continuity_level", "audio_continuity_evidence"),
                ("speech_intelligibility_level", "speech_intelligibility_evidence"),
                ("ai_generated_fatigue_level", "ai_fatigue_evidence"),
                ("visual_clutter_level", "clutter_evidence"),
                ("slide_layout_level", "slide_layout_evidence"),
                ("disconnect_level", "disconnect_evidence"),
                ("decorative_eye_candy_level", "decorative_eye_candy_evidence"),
                ("visual_signaling_level", "visual_signaling_evidence"),
                ("active_learning_level", "active_learning_evidence"),
                ("narrative_agency_level", "narrative_agency_evidence"),
                ("segmenting_level", "segmenting_evidence"),
            ):
                engagement_flags.setdefault(lk, 0)
                engagement_flags.setdefault(ek, "")
            
            def _sev_idx(severity):
                """Penalty tier: 1 = bonus (no penalty). 0 = none. -1/-2/-3 or legacy 2/3."""
                if isinstance(severity, bool):
                    return 2 if severity else 0
                if isinstance(severity, int):
                    if severity == 1:
                        return 0
                    if severity == 0:
                        return 0
                    if severity < 0:
                        return abs(severity)
                    if severity >= 2:
                        return min(severity, 3)
                return 0

            def calculate_penalty(severity):
                idx = _sev_idx(severity)
                return {0: 0, 1: 0.3, 2: 0.6, 3: 1.0}.get(idx, 1.0 if idx >= 3 else 0)
            
            def calculate_penalty_monotone(severity):
                idx = _sev_idx(severity)
                return {0: 0, 1: 0.4, 2: 0.8, 3: 1.2}.get(idx, 1.5 if idx >= 3 else 0)
            
            # Adaptability Score Calculation (Base: 4.0)
            adaptability_score = 4.0
            adaptability_calc_steps = ["Base: 4.0"]
            
            # Define adaptability flags and their penalties
            adaptability_penalties = [
                ("jargon_overload_level", "jargon_overload", calculate_penalty, "Jargon Overload"),
                ("prerequisite_gap_level", "prerequisite_gap", calculate_penalty, "Prerequisite Gap"),
                ("pacing_mismatch_level", "pacing_mismatch", calculate_penalty, "Pacing Mismatch"),
                ("missing_scaffolding_level", "missing_scaffolding", calculate_penalty, "Missing Scaffolding"),
                ("visual_pairing_level", "ineffective_visual_representation", calculate_penalty, "Visual pairing with content"),
            ]
            
            for level_key, legacy_key, penalty_fn, flag_name in adaptability_penalties:
                severity = adaptability_flags.get(level_key, adaptability_flags.get(legacy_key, 0))
                penalty = penalty_fn(severity)
                if penalty > 0:
                    adaptability_score -= penalty
                    adaptability_calc_steps.append(f"{flag_name}: -{penalty:.1f}")
            
            # Visual Accessibility Issue
            visual_issue_count = adaptability_flags.get(
                "written_text_legibility_level",
                adaptability_flags.get("visual_accessibility_level", adaptability_flags.get("visual_accessibility_issue", 0)),
            )
            if isinstance(visual_issue_count, bool):
                # Legacy bool: treat as a problem tier, not agent-scale +1 (bonus)
                visual_issue_count = -1 if visual_issue_count else 0
            elif isinstance(visual_issue_count, str):
                visual_issue_count = 0
            
            if isinstance(visual_issue_count, int) and visual_issue_count == 1:
                # INTEGER 1 = beyond expectation (bonus), not a single-issue penalty tier
                pass
            elif isinstance(visual_issue_count, int) and visual_issue_count != 0:
                idx = abs(visual_issue_count)
                if idx == 1:
                    penalty = 0.3
                elif idx == 2:
                    penalty = 0.6
                else:
                    penalty = 1.0
                
                issue_type = adaptability_flags.get("accessibility_issue_type", "contrast")
                if "signaling" in str(issue_type).lower():
                    penalty = min(1.0, penalty + 0.5)
                
                adaptability_score -= penalty
                adaptability_calc_steps.append(f"Illegible text (written-text legibility): -{penalty:.1f}")
            elif adaptability_flags.get("accessibility_issue_type", "").lower() == "signaling":
                penalty = 0.5
                adaptability_score -= penalty
                adaptability_calc_steps.append(f"Low Signaling Cues: -{penalty:.1f}")
            
            n_adapt_bonus = _count_agent_plus_one_levels(
                adaptability_flags.get("prerequisite_gap_level", 0),
                adaptability_flags.get("pacing_mismatch_level", 0),
                adaptability_flags.get("missing_scaffolding_level", 0),
                adaptability_flags.get("visual_pairing_level", 0),
            )
            adaptability_score = max(0.0, min(4.0, adaptability_score))
            adaptability_score = _apply_bonus_toward_five(
                adaptability_score, n_adapt_bonus, N_BONUS_FIELDS_ADAPTABILITY
            )
            adaptability_calc_steps.append(f"= {adaptability_score:.2f}" + (f" (+1×{n_adapt_bonus})" if n_adapt_bonus else ""))
            
            # Engagement Score Calculation (Base: 4.0)
            engagement_score = 4.0
            engagement_calc_steps = ["Base: 4.0"]
            
            # Define engagement flags and their penalties
            engagement_penalties = [
                ("monotone_audio_level", "monotone_audio", calculate_penalty_monotone, "Monotone Audio"),
                ("audio_continuity_level", "audio_continuity", calculate_penalty, "Audio Continuity"),
                ("speech_intelligibility_level", "speech_intelligibility", calculate_penalty, "Speech Intelligibility"),
                ("ai_generated_fatigue_level", "ai_generated_fatigue", calculate_penalty, "AI Generated Fatigue"),
                ("visual_clutter_level", "visual_clutter", calculate_penalty, "Visual Clutter"),
                ("slide_layout_level", "slide_layout", calculate_penalty, "Slide layout & composition"),
                ("disconnect_level", "disconnect", calculate_penalty, "Visual/Audio Disconnect"),
                ("decorative_eye_candy_level", "decorative_eye_candy", calculate_penalty, "Decorative Eye-Candy"),
                ("visual_signaling_level", "visual_signaling", calculate_penalty, "Visual Signaling"),
                ("active_learning_level", "active_learning", calculate_penalty, "Active Learning"),
                ("narrative_agency_level", "narrative_agency", calculate_penalty, "Narrative & Agency"),
                ("segmenting_level", "segmenting", calculate_penalty, "Segmenting"),
            ]
            
            for level_key, legacy_key, penalty_fn, flag_name in engagement_penalties:
                severity = engagement_flags.get(level_key, engagement_flags.get(legacy_key, 0))
                penalty = penalty_fn(severity)
                if penalty > 0:
                    engagement_score -= penalty
                    engagement_calc_steps.append(f"{flag_name}: -{penalty:.1f}")
            
            n_engage_bonus = _count_agent_plus_one_levels(
                engagement_flags.get("monotone_audio_level", 0),
                engagement_flags.get("disconnect_level", 0),
                engagement_flags.get("visual_signaling_level", 0),
                engagement_flags.get("speech_intelligibility_level", 0),
            )
            engagement_score = max(0.0, min(4.0, engagement_score))
            engagement_score = _apply_bonus_toward_five(
                engagement_score, n_engage_bonus, N_BONUS_FIELDS_ENGAGEMENT
            )
            engagement_calc_steps.append(f"= {engagement_score:.2f}" + (f" (+1×{n_engage_bonus})" if n_engage_bonus else ""))
            
            # Update result with calculated scores
            if "subjective_scores" not in result:
                result["subjective_scores"] = {}
            
            result["subjective_scores"]["adaptability"] = {
                "score": clip_score_1_5(adaptability_score),
                "calculation": " → ".join(adaptability_calc_steps),
            }
            
            result["subjective_scores"]["engagement"] = {
                "score": clip_score_1_5(engagement_score),
                "calculation": " → ".join(engagement_calc_steps),
            }
            
            # Fix audit_log structure if needed (move misplaced flags)
            if "ai_generated_fatigue" in audit_log and "ai_generated_fatigue" not in result.get("audit_log", {}).get("engagement_flags", {}):
                if "audit_log" not in result:
                    result["audit_log"] = {}
                if "engagement_flags" not in result["audit_log"]:
                    result["audit_log"]["engagement_flags"] = {}
                result["audit_log"]["engagement_flags"]["ai_generated_fatigue"] = audit_log.get("ai_generated_fatigue", False) 
                result["audit_log"]["engagement_flags"]["ai_fatigue_evidence"] = audit_log.get("ai_fatigue_evidence", "")
                # Remove from wrong location
                if "ai_generated_fatigue" in result["audit_log"]:
                    del result["audit_log"]["ai_generated_fatigue"]
                if "ai_fatigue_evidence" in result["audit_log"]:
                    del result["audit_log"]["ai_fatigue_evidence"]
            
            return result
            
        except Exception as e:
            # If calculation fails, return original result
            print(f"      ⚠️  Score calculation error: {e}, using original scores")
            return result
    
    def _check_agent3_scores_valid(self, result: Dict) -> bool:
        """Validate Agent 3 output. Canonical path: require that the 15 subjective
        metric scores were extracted and are not a degenerate all-equal vector."""
        if "subjective_metric_scores" in result or isinstance(result.get("metric_scores"), dict):
            flat = result.get("subjective_metric_scores") or self._extract_metric_scores(result, "subjective")
            required = set(metrics_for("subjective"))
            missing = required - set(flat.keys())
            if missing:
                print(f"      ⚠️  Structure: subjective metric_scores missing: {missing}")
                return False
            # reject a degenerate response where the model emitted nothing varied
            if len(set(flat.values())) == 1 and next(iter(flat.values())) in (0,):
                print("      ⚠️  All subjective metric scores are 0 — invalid")
                return False
            return True
        REQUIRED_ADAPTABILITY = {
            "jargon_overload_level", "prerequisite_gap_level",
            "pacing_mismatch_level", "written_text_legibility_level",
            "missing_scaffolding_level",
            "visual_pairing_level",
        }
        REQUIRED_ENGAGEMENT = {
            "monotone_audio_level", "audio_continuity_level", "speech_intelligibility_level",
            "ai_generated_fatigue_level",
            "visual_clutter_level", "slide_layout_level", "disconnect_level",
            "decorative_eye_candy_level", "visual_signaling_level",
        }

        try:
            audit_log = result.get("audit_log", {})
            adapt_flags = audit_log.get("adaptability_flags", {})
            engage_flags = audit_log.get("engagement_flags", {})

            # Check all required keys exist (after fallback merge already ran)
            missing_adapt = REQUIRED_ADAPTABILITY - set(adapt_flags.keys())
            missing_engage = REQUIRED_ENGAGEMENT - set(engage_flags.keys())

            if missing_adapt:
                print(f"      ⚠️  Structure: adaptability_flags missing keys: {missing_adapt}")
                return False
            if missing_engage:
                print(f"      ⚠️  Structure: engagement_flags missing keys: {missing_engage}")
                return False

            return True
        except Exception as e:
            print(f"      ⚠️  Structure check error: {e}, treating as invalid → retry")
            return False
    
    @staticmethod
    def _agent3_structured_evidence_json(agent1_result: Dict, agent2_result: Dict) -> str:
        """Agent 3 純文字模式：餵給模型的唯一結構化證據。"""
        payload = {
            "instruction": (
                "These objects are the ONLY source for topics, timestamps, alignment, "
                "accessibility issues, and depth claims. If a detail is missing, treat as unknown "
                "and prefer level 0 / -1 over severe penalties."
            ),
            "agent1": {
                "teaching_mode": agent1_result.get("teaching_mode"),
                "content_map": agent1_result.get("content_map", []),
                "potential_issues": agent1_result.get("potential_issues", []),
                "presentation_analysis": agent1_result.get("presentation_analysis", {}),
                "written_text_legibility_audit": _get_written_text_legibility_audit(agent1_result),
                "observation_summary": agent1_result.get("observation_summary", ""),
            },
            "agent2": {
                "accuracy_score": agent2_result.get("accuracy_score"),
                "logic_score": agent2_result.get("logic_score"),
                "score_breakdown": agent2_result.get("score_breakdown", {}),
                "pedagogical_depth": agent2_result.get("pedagogical_depth", {}),
                "completeness": agent2_result.get("completeness", {}),
                "accuracy_flags": agent2_result.get("accuracy_flags", {}),
                "logic_flags": agent2_result.get("logic_flags", {}),
                "content_overview": agent2_result.get("content_overview", {}),
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
    
    def run_agent3_sync(self, video_path: Path, persona: str, agent1_result: Dict, agent2_result: Dict) -> Dict:
        """
        Agent 3: 主觀模擬（同步）
        如果分數都是 0，自動重試一次
        若 ``VIBE_TEACH_AGENT3_TEXT_ONLY=1``：不上傳影片，只根據 Agent1+2 JSON 與主觀 prompt 作答。
        """
        max_retries = 2  # 最多嘗試2次
        
        for attempt in range(1, max_retries + 1):
            try:
                video_file = None
                if not self.agent3_text_only and vlm.PROVIDER == "gemini":
                    # Upload video (Gemini native path)
                    video_file = self.client.files.upload(
                        file=str(video_path),
                        config={"mime_type": "video/mp4"}
                    )

                    # Wait for processing
                    while video_file.state.name == "PROCESSING":
                        time.sleep(2)
                        video_file = self.client.files.get(name=video_file.name)

                    if video_file.state.name == "FAILED":
                        raise ValueError(f"Video upload failed: {video_path}")
                
                # Extract presentation analysis from Agent 1
                presentation = agent1_result.get("presentation_analysis", {})
                visual_style = presentation.get("visual_style", "Not specified")
                audio_pacing = presentation.get("audio_pacing", "Not specified")
                # ai_slop_detected: new format = array ["Description with timestamps"], legacy = boolean
                ai_slop_raw = presentation.get("ai_slop_detected", False)
                if isinstance(ai_slop_raw, list):
                    ai_slop_detected = "Yes: " + "; ".join(ai_slop_raw) if ai_slop_raw else "No"
                else:
                    ai_slop_detected = "Yes" if ai_slop_raw else "No"
                
                # Extract audio transition audit
                audio_transition = presentation.get("audio_transition_audit", {})
                vocal_consistency = audio_transition.get("vocal_consistency", "Not assessed")
                audio_glitches = audio_transition.get("glitches", [])
                
                video_audio_alignment = format_agent3_narration_slide_claim(presentation)
                
                # Format audio glitches for prompt (items may be strings or dicts with "description")
                def _glitch_str(g):
                    return g.get("description", str(g)) if isinstance(g, dict) else str(g)
                audio_glitches_str = "; ".join(_glitch_str(g) for g in audio_glitches) if audio_glitches else "None"
                
                # Extract visual accessibility audit: now nested in presentation_analysis (new format), fallback to top-level (legacy)
                vis_audit = (
                    presentation.get("written_text_legibility_audit")
                    or presentation.get("visual_accessibility_audit")
                    or _get_written_text_legibility_audit(agent1_result)
                )
                # New unified "issues" field; fallback to legacy "contrast_issues"
                accessibility_issues = vis_audit.get("issues") or vis_audit.get("contrast_issues", [])

                # Format visual accessibility summary for Agent 3
                if accessibility_issues:
                    # Format: "[timestamp] (type) issue (severity)"
                    formatted_issues = []
                    for item in accessibility_issues[:5]:  # Limit to first 5 issues
                        timestamp = item.get("timestamp", "??:??")
                        issue_type = item.get("type", "contrast")
                        issue = item.get("issue", "Unspecified issue")
                        severity = item.get("severity", "Unknown")
                        formatted_issues.append(f"[{timestamp}] ({issue_type}) {issue} ({severity})")
                    visual_accessibility_summary = f"On-screen text legibility issues (Agent 1): {'; '.join(formatted_issues)}"
                    contrast_issues_detected = True
                else:
                    visual_accessibility_summary = "No on-screen text legibility issues reported by Agent 1"
                    contrast_issues_detected = False
                
                # comp_aesthetics = get_computational_aesthetics_summary(
                #     video_path,
                #     enabled=self.computational_aesthetics,
                # )
                # print(f"      [Agent 3] computational_aesthetics (full):\n{comp_aesthetics}\n")
                
                # Generate content with presentation style parameters
                # Split prompt: persona section → system_instruction, rest → user message
                _split_marker = "# INPUT CONTEXT"
                _parts = self.subjective_prompt_template.split(_split_marker, 1)
                agent3_system = _parts[0].format(student_persona=persona)
                agent3_user = (_split_marker + _parts[1]).format(
                    visual_style=visual_style,
                    audio_pacing=audio_pacing,
                    ai_slop_detected=str(ai_slop_detected),
                    video_audio_alignment=video_audio_alignment,
                    vocal_consistency=vocal_consistency,
                    audio_glitches=audio_glitches_str,
                    visual_accessibility_summary=visual_accessibility_summary,
                    contrast_issues_detected=str(contrast_issues_detected),
                    metric_block=render_metric_block("subjective"),
                    metric_scores_skeleton=render_metric_scores_skeleton("subjective"),
                )
                
                if self.agent3_text_only:
                    agent3_user += (
                        "\n\n---\n\n# STRUCTURED EVIDENCE (SOLE SOURCE)\n"
                        "You do **not** have access to the video. For every flag, cite evidence using "
                        "**only** timestamps or descriptions that appear in the JSON below. "
                        "Do not invent new timestamps.\n\n"
                        + self._agent3_structured_evidence_json(agent1_result, agent2_result)
                    )
                
                # Add retry hint if this is a retry
                if attempt > 1:
                    agent3_user += (
                        "\n\nCRITICAL RETRY INSTRUCTION: Your previous response was REJECTED because it was missing required keys. "
                        "You MUST include ALL of the following keys — set them to 0 if no issue, but do NOT omit them:\n"
                        "audit_log.adaptability_flags: jargon_overload_level, jargon_evidence, prerequisite_gap_level, prerequisite_evidence, "
                        "pacing_mismatch_level, pacing_evidence, written_text_legibility_level, written_text_legibility_evidence, missing_scaffolding_level, scaffolding_evidence, "
                        "visual_pairing_level, visual_pairing_evidence\n"
                        "audit_log.engagement_flags: monotone_audio_level, monotone_evidence, "
                        "audio_continuity_level, audio_continuity_evidence, "
                        "speech_intelligibility_level, speech_intelligibility_evidence, "
                        "ai_generated_fatigue_level, ai_fatigue_evidence, "
                        "visual_clutter_level, clutter_evidence, slide_layout_level, slide_layout_evidence, disconnect_level, disconnect_evidence, "
                        "decorative_eye_candy_level, decorative_eye_candy_evidence, "
                        "visual_signaling_level, visual_signaling_evidence, "
                        "active_learning_level, active_learning_evidence, "
                        "narrative_agency_level, narrative_agency_evidence, "
                        "segmenting_level, segmenting_evidence\n"
                        "Output ONLY valid JSON with ALL keys present."
                    )
                
                if vlm.PROVIDER != "gemini":
                    # Claude / GPT: text-only passes no frames; otherwise sample video.
                    response = vlm.generate(
                        role=f"Agent 3 attempt {attempt}",
                        system=agent3_system,
                        prompt=agent3_user,
                        video_path=None if self.agent3_text_only else video_path,
                    )
                elif self.agent3_text_only:
                    response = self.client.models.generate_content(
                        model="gemini-3-flash-preview",
                        contents=[agent3_user],
                        config=_gemini_generate_config(
                            skip_media_resolution=True,
                            system_instruction=agent3_system,
                            temperature=0.0,
                            response_mime_type="application/json",
                        ),
                    )
                    _log_gemini_usage(f"Agent 3 attempt {attempt}", response)
                else:
                    response = self.client.models.generate_content(
                        model="gemini-3-flash-preview",
                        contents=_gemini_video_text_contents(
                            video_file,
                            agent3_user,
                            video_fps=_clamp_gemini_video_fps(AGENT3_VIDEO_INPUT_FPS),
                        ),
                        config=_gemini_generate_config(
                            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
                            system_instruction=agent3_system,
                            temperature=0.0,
                            response_mime_type="application/json",
                        ),
                    )
                    _log_gemini_usage(f"Agent 3 attempt {attempt}", response)
                
                # Clean up uploaded file (video mode only)
                if video_file is not None:
                    try:
                        self.client.files.delete(name=video_file.name)
                    except Exception:
                        pass
                
                result = response.parsed
                if result is None and response.text:
                    try:
                        # Clean response text: remove markdown code blocks, leading/trailing whitespace
                        cleaned_text = response.text.strip()
                        if cleaned_text.startswith("```json"):
                            cleaned_text = cleaned_text[7:]  # Remove ```json
                        if cleaned_text.startswith("```"):
                            cleaned_text = cleaned_text[3:]  # Remove ```
                        if cleaned_text.endswith("```"):
                            cleaned_text = cleaned_text[:-3]  # Remove trailing ```
                        cleaned_text = cleaned_text.strip()
                        
                        # Handle "Extra data" errors by extracting only the first complete JSON object
                        try:
                            result = json.loads(cleaned_text)
                        except json.JSONDecodeError as je:
                            if "Extra data" in str(je):
                                # Find the position where the first JSON object ends
                                decoder = json.JSONDecoder()
                                result, idx = decoder.raw_decode(cleaned_text)
                                print(f"      ⚠️  Warning: Extra data after JSON (extracted first object)")
                            else:
                                raise
                    except json.JSONDecodeError as je:
                        print(f"      ⚠️  JSON parse error: {str(je)}")
                        print(f"      First 200 chars: {response.text[:200]}")
                        result = {"error": "JSON parse failed", "raw": response.text[:500]}
                
                if isinstance(result, list):
                    result = result[0] if result else {"error": "Empty list response"}

                final_result = result or {"error": "Empty response"}

                # Deterministic scoring calculation based on audit flags
                final_result = self._calculate_deterministic_scores(final_result)
                # final_result["computational_aesthetics"] = comp_aesthetics
                
                # Check if scores are valid
                if self._check_agent3_scores_valid(final_result):
                    if attempt > 1:
                        print(f"      ✓ Retry successful (attempt {attempt})")
                    return final_result
                else:
                    if attempt < max_retries:
                        print(f"      ⚠️  Agent 3 output structure invalid, retrying (attempt {attempt}/{max_retries})...")
                        continue
                    else:
                        print(f"      ⚠️  Agent 3 output still invalid after {max_retries} attempts, using best-effort result")
                        return final_result
                
            except Exception as e:
                print(f"      ✗ Agent 3 error (attempt {attempt}): {e}")
                if attempt == max_retries:
                    return {"error": str(e)}
                else:
                    print(f"      → Retrying...")
                    continue
        
        return {"error": "Max retries exceeded"}
    
    def _build_combined_report(self, task, agent1_result, agent2_result, agent3_result, scores, timestamp, task_idx, run_id) -> Dict:
        """組合單次任務的完整報告"""
        # Canonical 24-metric scores (with per-metric evidence) + the 4 rolled-up dims.
        obj_ev = agent2_result.get("metric_scores", {}) or {}
        subj_ev = agent3_result.get("metric_scores", {}) or {}
        obj_flat = agent2_result.get("objective_metric_scores", {}) or {}
        subj_flat = agent3_result.get("subjective_metric_scores", {}) or {}
        metric_scores = {}
        for code, m in iter_metrics():
            flat = obj_flat if m["evaluator"] == "objective" else subj_flat
            ev_src = obj_ev if m["evaluator"] == "objective" else subj_ev
            ev = ev_src.get(code, {})
            metric_scores[code] = {
                "score": flat.get(code, 3),
                "dimension": code.split("_")[0][0],
                "tm_dim": m["tm_dim"],
                "evidence": ev.get("evidence", "") if isinstance(ev, dict) else "",
            }
        return {
            "criteria_version": load_criteria().get("meta", {}).get("version", ""),
            "dimension_scores": {
                "accuracy": scores["accuracy"],
                "logic": scores["logic"],
                "adaptability": scores["adaptability"],
                "engagement": scores["engagement"],
            },
            "metric_scores": metric_scores,
            "agent1_content_analyst": {
                "teaching_mode": agent1_result.get("teaching_mode", ""),
                "content_map": agent1_result.get("content_map", []),
                "potential_issues": agent1_result.get("potential_issues", []),
                "presentation_analysis": agent1_result.get("presentation_analysis", {}),
                "written_text_legibility_audit": _get_written_text_legibility_audit(agent1_result),
                "observation_summary": agent1_result.get("observation_summary", ""),
            },
            "agent2_gap_analysis_judge": {
                "accuracy_score": scores["accuracy"],
                "logic_score": scores["logic"],
                "primary_language": agent2_result.get("primary_language", "english"),
                "critical_fact_error_count": agent2_result.get("critical_fact_error_count", 0),
                "key_learning_points_coverage": agent2_result.get("key_learning_points_coverage", {}),
                "verified_errors": agent2_result.get("verified_errors", []),
                "scoring_rationale": agent2_result.get("scoring_rationale", ""),
            },
            "subjective_evaluation": {
                "adaptability": {"score": scores["adaptability"]},
                "engagement": {"score": scores["engagement"]},
                "experiential_context": agent3_result.get("experiential_context", {}),
                "top_fix_suggestion": agent3_result.get("top_fix_suggestion", ""),
            },
            "_meta": {
                "video_url": task.video_url,
                "title_en": task.title,
                "big_concept": task.big_concept,
                "blooms_level": task.blooms_level,
                "learning_goal": task.learning_goal,
                "key_learning_points": task.key_learning_points,
                "student_persona": task.persona,
                "timestamp": timestamp,
                "task_index": task_idx,
                "run_id": run_id,
                "total_runs": self.num_runs,
                "agent3_text_only": self.agent3_text_only,
            }
        }

    async def process_single_task(self, task: VideoTask, task_idx: int, total: int, run_id: int = 1, output_dir: Path = None) -> Dict:
        """異步處理單個任務，完成後立即存 JSON"""
        async with self.semaphore:
            run_info = f" (Run {run_id}/{self.num_runs})" if self.num_runs > 1 else ""
            run_prefix = f"[Run {run_id}]" if self.num_runs > 1 else ""
            print(f"\n[{task_idx}/{total}]{run_info} Processing: {task.title}")
            print(f"   Persona: {task.persona[:80]}...")
            
            try:
                # Run Agent 1 (retry on failure; do NOT proceed to Agent 2/3 until success)
                agent1_max_retries = 2
                agent1_retry_wait_sec = 30
                agent1_result = None
                for attempt in range(1, agent1_max_retries + 1):
                    print(f"   {run_prefix} → Agent 1: Content Analysis (attempt {attempt}/{agent1_max_retries})...")
                    agent1_result = await asyncio.to_thread(
                        self.run_agent1_sync,
                        task.video_path,
                        task.title,
                        task.big_concept,
                        task.blooms_level,
                        task.learning_goal,
                        task.key_learning_points,
                    )
                    if agent1_result and "error" not in agent1_result:
                        break
                    err_msg = agent1_result.get("error", "Unknown") if agent1_result else "Empty"
                    if attempt < agent1_max_retries:
                        print(f"   ⚠️  Agent 1 failed: {err_msg}. Waiting {agent1_retry_wait_sec}s before retry...")
                        await asyncio.sleep(agent1_retry_wait_sec)
                    else:
                        print(f"   ✗ Agent 1 failed after {agent1_max_retries} attempts: {err_msg}")
                        raise RuntimeError(f"Agent 1 failed: {err_msg}")

                # Run Agent 2
                print(f"   {run_prefix} → Agent 2: Scoring...")
                agent2_result = await asyncio.to_thread(
                    self.run_agent2_sync,
                    task.title,
                    agent1_result,
                    task.blooms_level,
                    task.key_learning_points,
                )
                
                # Run Agent 3
                _a3_label = "Subjective (text-only, no video)" if self.agent3_text_only else "Subjective Simulation"
                print(f"   {run_prefix} → Agent 3: {_a3_label}...")
                agent3_result = await asyncio.to_thread(
                    self.run_agent3_sync,
                    task.video_path,
                    task.persona,
                    agent1_result,
                    agent2_result
                )
                
                # Canonical-criteria scoring: union the 9 objective + 15 subjective
                # metric scores, then mean each Teaching-Monster dim from them.
                obj_ms = agent2_result.get("objective_metric_scores", {}) or {}
                subj_ms = agent3_result.get("subjective_metric_scores", {}) or {}
                all_metric_scores = {**obj_ms, **subj_ms}

                if all_metric_scores:
                    tm = aggregate_tm_dims(all_metric_scores)
                    scores = {k: clip_score_1_5(v) for k, v in tm.items()}
                else:
                    # legacy fallback (old flag-penalty responses)
                    subj_scores = agent3_result.get("subjective_scores", {})
                    adaptability = subj_scores.get("adaptability", 0)
                    engagement = subj_scores.get("engagement", 0)
                    if isinstance(adaptability, dict):
                        adaptability = adaptability.get("score", 0)
                    if isinstance(engagement, dict):
                        engagement = engagement.get("score", 0)
                    scores = {
                        "accuracy": clip_score_1_5(agent2_result.get("accuracy_score", 0)),
                        "logic": clip_score_1_5(agent2_result.get("logic_score", 0)),
                        "adaptability": clip_score_1_5(adaptability),
                        "engagement": clip_score_1_5(engagement),
                    }
                print(
                    f"   ✓ Completed: Accuracy={scores['accuracy']:.2f}, Logic={scores['logic']:.2f}, "
                    f"Adaptability={scores['adaptability']:.2f}, Engagement={scores['engagement']:.2f} (1–5, clipped)"
                )

                # Immediately save JSON after task completes
                json_filename = None
                if output_dir is not None:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    combined_report = self._build_combined_report(
                        task, agent1_result, agent2_result, agent3_result,
                        scores, ts, task_idx, run_id
                    )
                    if self.num_runs > 1:
                        json_filename = f"{ts}_task_{task_idx}_run_{run_id}.json"
                    else:
                        json_filename = f"{ts}_task_{task_idx}.json"
                    json_path = output_dir / json_filename
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(combined_report, f, indent=2, ensure_ascii=False)
                    print(f"   💾 Saved: {json_filename}")

                return {
                    "task": task,
                    "task_idx": task_idx,
                    "run_id": run_id,
                    "agent1_result": agent1_result,
                    "agent2_result": agent2_result,
                    "agent3_result": agent3_result,
                    "scores": scores,
                    "json_filename": json_filename,
                    "success": True
                }
                
            except Exception as e:
                print(f"   ✗ Error: {e}")
                traceback.print_exc()
                return {
                    "task": task,
                    "task_idx": task_idx,
                    "run_id": run_id,
                    "error": str(e),
                    "success": False
                }
    
    async def process_all_tasks(self, tasks: List[VideoTask], output_dir: Path) -> Path:
        """並發處理所有任務（支持多次運行）"""
        print("\n" + "=" * 80)
        print(f"PHASE 3: CONCURRENT PROCESSING ({self.max_concurrent} at a time)")
        if self.num_runs > 1:
            print(f"   Each task will run {self.num_runs} times for consistency analysis")
        print("=" * 80)
        
        # Filter tasks with valid video paths
        valid_tasks = [t for t in tasks if t.video_path and t.video_path.exists()]
        total_runs = len(valid_tasks) * self.num_runs
        print(f"\n✓ Processing {len(valid_tasks)} tasks × {self.num_runs} runs = {total_runs} total executions")
        print(f"✓ Concurrent workers: {self.max_concurrent}\n")
        
        # Create processing tasks with multiple runs
        processing_tasks = []
        for run_id in range(1, self.num_runs + 1):
            for idx, task in enumerate(valid_tasks, 1):
                processing_tasks.append(
                    self.process_single_task(task, idx, len(valid_tasks), run_id, output_dir)
                )
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*processing_tasks, return_exceptions=True)
        
        # Compile CSV summary (JSONs already saved incrementally)
        print("\n" + "=" * 80)
        print("PHASE 4: SAVING RESULTS")
        print("=" * 80)

        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        all_results = []
        csv_summary = []

        for result in results:
            if isinstance(result, Exception):
                print(f"Exception: {result}")
                continue

            if not result.get("success"):
                continue

            task = result["task"]
            task_idx = result.get("task_idx", 1)
            run_id = result.get("run_id", 1)
            scores = result["scores"]
            json_filename = result.get("json_filename", "")

            all_results.append(result)

            # CSV record
            csv_summary.append({
                "run_id": run_id,
                "task_index": task_idx,
                "video_url": task.video_url,
                "title_en": task.title,
                "student_persona": task.persona[:100],
                "accuracy": scores["accuracy"],
                "logic": scores["logic"],
                "adaptability": scores["adaptability"],
                "engagement": scores["engagement"],
                "json_file": json_filename,
            })
        
        # Save CSV summary
        csv_filename = f"{timestamp}_summary.csv"
        csv_path = output_dir / csv_filename
        
        if csv_summary:
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=csv_summary[0].keys())
                writer.writeheader()
                writer.writerows(csv_summary)
        
        print(f"\n✓ Saved {len(all_results)} results to: {output_dir}")
        print(f"✓ CSV summary: {csv_path}\n")
        
        return csv_path

# ============================================================================
# Main Workflow
# ============================================================================


# ============================================================================
# Main Workflow
# ============================================================================

async def main():
    """主要工作流程"""
    
    print("\n" + "=" * 80)
    print(" ASYNC CONCURRENT VIDEO AUDIT PROCESSOR")
    print("=" * 80 + "\n")
    
    # Check API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY not set")
        print("   Run: export GEMINI_API_KEY='your-api-key'")
        return
    
    # ============================================================
    # Input Configuration
    # ============================================================
    # Choose input source via INPUT_FILE env var.
    # Default: eval_video_pool.json (the same pool the human eval app uses).
    # Set INPUT_FILE=input_videos.json to use a single-job input.
    input_path_str = os.environ.get("INPUT_FILE", "inputs/pool_demo.json")
    input_file = Path(input_path_str)
    if not input_file.exists():
        print(f"⚠️  {input_file} not found")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Normalise: support both
    #   A) flat list      [{video_url, course_requirement, student_persona, ...}]
    #   B) pool wrapper   {"videos": [{video_url, course_requirement, personas: [{student_persona: "..."}]}]}
    if isinstance(raw, dict) and "videos" in raw:
        videos = raw["videos"]
    else:
        videos = raw

    input_config = []
    for v in videos:
        # Personas may be a list of dicts ({"student_persona": "..."}) or list of strings
        raw_personas = v.get("personas") or []
        persona_strs = []
        for p in raw_personas:
            if isinstance(p, dict):
                ps = p.get("student_persona", "")
            else:
                ps = str(p)
            if ps:
                persona_strs.append(ps)
        # Or single student_persona field
        if not persona_strs and v.get("student_persona"):
            persona_strs = [v["student_persona"]]

        entry = {
            "video_url": v["video_url"],
            "course_requirement": v.get("course_requirement", ""),
            "title": v.get("title", "") or v.get("title_en", ""),
            "big_concept": v.get("big_concept", ""),
            "blooms_level": v.get("blooms_level", ""),
            "learning_goal": v.get("learning_goal", ""),
            "key_learning_points": v.get("key_learning_points", ""),
            "personas": persona_strs,
        }
        input_config.append(entry)

    print(f"✓ Loaded {len(input_config)} videos from {input_file}\n")
    
    # ============================================================
    # Initialize Processor
    # ============================================================
    max_concurrent = int(os.environ.get("MAX_CONCURRENT", "3"))
    num_runs = int(os.environ.get("NUM_RUNS", "3"))  # 每個任務運行次數
    
    print(f"✓ Max concurrent tasks: {max_concurrent}")
    if num_runs > 1:
        print(f"✓ Runs per task: {num_runs} (for consistency analysis)")
    print()
    
    processor = AsyncConcurrentProcessor(
        api_key=api_key, 
        max_concurrent=max_concurrent,
        num_runs=num_runs
    )
    
    # ============================================================
    # PHASE 1-2: Prepare tasks and download videos
    # ============================================================
    tasks = await processor.prepare_tasks(input_config)
    
    if not tasks:
        print("❌ No valid tasks to process")
        return
    
    # ============================================================
    # PHASE 3-4: Process all tasks concurrently
    # ============================================================
    # Build output directory name with optional tag
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    test_tag = os.getenv('TEST_TAG', 'finegrain_persona')
    if test_tag:
        dir_name = f"concurrent_{timestamp}_{test_tag}"
    else:
        dir_name = f"concurrent_{timestamp}"
    output_dir = EVAL_RESULTS_DIR / dir_name
    csv_path = await processor.process_all_tasks(tasks, output_dir)
    
    # ============================================================
    # PHASE 5: Cleanup
    # ============================================================
    print("=" * 80)
    print("PHASE 5: CLEANUP")
    print("=" * 80)
    
    # Clean up temporary videos
    for task in tasks:
        if task.video_path and task.video_path.exists():
            try:
                task.video_path.unlink()
                print(f"✓ Deleted: {task.video_path.name}")
            except Exception as e:
                print(f"✗ Failed to delete {task.video_path.name}: {e}")
    
    print("\n" + "=" * 80)
    print("✅ CONCURRENT PROCESSING COMPLETE")
    print("=" * 80)
    print(f"Results: {output_dir}")
    print(f"CSV Summary: {csv_path}")
    print("=" * 80 + "\n")

# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    asyncio.run(main())

