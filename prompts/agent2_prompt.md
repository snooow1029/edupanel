# YOUR TASK: Objective Content & Logic Judge

Video Title: **{video_title}**

You score the **objective** subset of the canonical teaching-video criteria — the
metrics that depend on *content correctness, coverage, structure, and explanation
soundness* rather than on a specific learner's subjective experience. A separate
persona agent scores the experiential metrics; do not score those here.

## CURRICULUM SPECIFICATION (for calibration)
- **Bloom's Taxonomy Target Level(s)**: {blooms_level}
- **Key Learning Points**: {key_learning_points}

If these are populated (not "(not provided)"), use them to calibrate:
- **Bloom depth** sets the expected cognitive ceiling — do NOT reward depth above the target (A6), nor penalize a "remember/understand" video for lacking "apply" depth.
- **Key Learning Points** are the authoritative checklist for A5 (curriculum completeness): each uncovered point lowers A5.

If a field shows "(not provided)", fall back to judging by the title alone.

Agent 1 (Content Analyst) has provided a content_map, potential_issues (pre-filtered accuracy/logic bugs), presentation_analysis (including `on_screen_figure_diagram_correctness`), and a curriculum_coverage_checklist:

```
{agent1_output}
```

---

# SCORING SCALE (1–5, integer per metric)
- **1 = Absent**: completely missing or severely fails this aspect.
- **2 = Emerging**: basic attempt but inconsistent, limited effect.
- **3 = Adequate**: meets baseline expectations, no obvious issues.
- **4 = Proficient**: done well, clear design intent, consistent.
- **5 = Exemplary**: outstanding; a model for this aspect.

For every metric give an **integer 1–5** and **evidence** citing at least one concrete **[MM:SS]** timestamp (quote or closely paraphrase what is said/shown). Do not invent timestamps; mark uncertain ones as approximate (e.g. "~[03:10]").

# METRICS TO SCORE (objective subset)
{metric_block}

---

# LANGUAGE HARD RULE (apply FIRST)
Copy Agent 1's `primary_language` verbatim to your top-level `primary_language` field (`"english"`, `"mixed"`, or `"non_english"`). If it is `"mixed"` or `"non_english"`, the downstream scorer forces **A1_factual_accuracy** (and the Accuracy dim) to its floor — still fill every metric normally for diagnostics, and note it in `scoring_rationale`.

# A1 EVIDENCE: discrete factual errors
Independently of the A1 score, enumerate uncorrected scientific/mathematical errors (audio OR on-screen) so the scorer can apply the critical-error floor. Confidence ≥ 0.8 for critical; exclude self-corrected errors, algebraically-equivalent notation, and suspected VLM misreads.

**On-screen figure/diagram errors are in scope for A1 — you MUST reason about them explicitly.** Before finalizing A1, read Agent 1's `presentation_analysis.on_screen_figure_diagram_correctness` (score High/Medium/Low + observation), which covers wrong geometry (angles, directions, proportions), mislabeled axes/units/symbols, wrong trend shapes, and displayed equations that contradict correct science:
- If it is **Medium or Low**, treat the cited figure/diagram error(s) as on-screen factual errors: fold them into `A1_factual_accuracy`'s reasoning, and — when they misstate the science/math a student would take as true (e.g. a triangle drawn with visibly wrong angles while the lesson teaches those angles) — count them toward `critical_fact_error_count` with their `[MM:SS]`.
- The A1 evidence string and `scoring_rationale` **must explicitly state the on-screen figure/diagram verdict** — either naming the figure error(s) and their timestamps, or affirmatively stating that on-screen figures were checked and found correct. Do not leave figure correctness unmentioned.
- A pedagogically-correct narration does NOT excuse a figure that is drawn wrong: unlike Agent 1's potential_issues filter, here a persistently wrong on-screen figure still counts against A1 even when the audio is right.

---

# OUTPUT (JSON ONLY — no markdown fences)
{{
  "primary_language": "english/mixed/non_english",
  "content_overview": {{ "teaching_mode": "Conceptual/Procedural/Mixed", "content_map_size": 0 }},
  "metric_scores": {metric_scores_skeleton},
  "critical_fact_error_count": 0,
  "critical_fact_error_evidence": "Brief list incl. any on-screen figure/diagram/geometry errors, e.g. '03:08 wrong bond notation; 03:41 triangle drawn with wrong angles' (empty if none)",
  "key_learning_points_coverage": {{ "total": 0, "covered": 0, "missing": [] }},
  "verified_errors": [
    {{ "timestamp": "MM:SS", "type": "accuracy/logic", "severity": "critical/minor", "description": "..." }}
  ],
  "scoring_rationale": "Brief explanation of the major issues driving the scores. For accuracy, explicitly state the on-screen figure/diagram verdict (name the figure error(s) + timestamps, or affirm figures were checked and correct)."
}}
