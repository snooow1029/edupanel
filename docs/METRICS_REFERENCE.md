# Teaching-Video Rubric — 24-Metric Reference & Ceiling-Effect Record

> One consolidated reference for the A–F, 24-metric teaching-video rubric: each metric's **learning-science source**, its **original definition + 1/3/5 anchors**, which agent scores it, which **legacy `batch_audit` flags it absorbed**, and the **ceiling-effect pilot numbers** measured on real teaching videos.

**Rubric:** `criteria/teaching_video_criteria_v2.json` (v2.0). **Scale:** 1–5 ordinal (1 Absent · 2 Emerging · 3 Adequate · 4 Proficient · 5 Exemplary).

**Ceiling data:** latest metric score per video across all `eval_results/concurrent_*` runs. **Human/good column** = 10 real-human + real-good teaching videos (the ceiling-effect sample). **Full-population column** = all 56 pool videos (bad→excellent), for contrast.

**Band** (from the human/good sample): 🔴 CEILING = mean≥4.6 & std<0.55 (good videos indistinguishable) · 🟠 near-ceiling · 🟡 mid · 🟢 frontier = mean<3.7 (weak even on good videos).

## 1. Master table

| # | Metric | TM dim | Agent | Theory source | Def. (short) | Human/good μ±σ | Full-pop μ±σ | Band |
|---|---|---|---|---|---|---|---|---|
| A1 | `A1_factual_accuracy` | accuracy | A2 | Backward Design + Bloom's Taxonomy | Are spoken facts, formulas, data, AND on-screen figures/diagrams/equat… | 4.40±1.28 | 4.23±1.31 | 🟡 mid |
| A2 | `A2_topic_coverage` | accuracy | A2 | Backward Design + Bloom's Taxonomy | Does the video cover all topics implied by its title/learning goal, at… | 4.50±0.50 | 3.55±1.41 | 🟠 near-ceiling |
| A3 | `A3_logical_structure` | pedagogical_logic | A2 | Backward Design + Bloom's Taxonomy | Are concepts presented in a logical, coherent sequence, with each idea… | 4.90±0.30 | 4.41±0.65 | 🔴 CEILING |
| A4 | `A4_learning_objectives` | pedagogical_logic | A2 | Backward Design + Bloom's Taxonomy | Does the video state, near the start, what the learner will be able to… | 3.30±0.64 | 2.82±0.91 | 🟢 frontier (spreads) |
| A5 | `A5_curriculum_completeness` | accuracy | A2 | Backward Design + Bloom's Taxonomy | Relative to the Key Learning Points in the course requirement, does th… | 4.70±0.64 | 3.79±1.51 | 🟠 near-ceiling |
| A6 | `A6_bloom_alignment` | pedagogical_logic | A2 | Backward Design + Bloom's Taxonomy | Does the cognitive depth actually delivered match the target Bloom's l… | 4.80±0.40 | 4.16±1.36 | 🔴 CEILING |
| B1 | `B1_signaling` | engagement | A3 | Mayer CTML + Sweller CLT | Does the video use visual cues — highlights, arrows, boxing, color-cod… | 3.80±0.60 | 3.95±0.81 | 🟡 mid |
| B2 | `B2_segmenting` | pedagogical_logic | A3 | Mayer CTML + Sweller CLT | Is the video segmented at cognitive turning points — with recaps, sign… | 4.00±0.89 | 3.77±0.98 | 🟡 mid |
| B3 | `B3_coherence` | engagement | A3 | Mayer CTML + Sweller CLT | Is the video free of irrelevant or distracting material — decorative a… | 4.30±0.90 | 4.45±0.84 | 🟡 mid |
| B4 | `B4_modality_integration` | engagement | A3 | Mayer CTML + Sweller CLT | Do narration and visuals COMPLEMENT each other (not redundant word-for… | 4.30±0.90 | 4.48±1.07 | 🟡 mid |
| C1 | `C1_examples_analogies` | pedagogical_logic | A3 | Cognitive Apprenticeship + Dual-Coding | Does the video use analogies, concrete examples, or multiple represent… | 4.10±0.94 | 3.70±1.22 | 🟡 mid |
| C2 | `C2_scaffolding_strategy` | pedagogical_logic | A2 | Cognitive Apprenticeship + Dual-Coding | Does the video build from what the learner knows to what they need (kn… | 4.80±0.40 | 4.25±0.85 | 🔴 CEILING |
| C3 | `C3_conceptual_procedural_balance` | pedagogical_logic | A2 | Cognitive Apprenticeship + Dual-Coding | Is there an appropriate balance between 'understanding why' (concept)… | 4.60±0.49 | 4.21±0.99 | 🔴 CEILING |
| C4 | `C4_visual_explanation_power` | engagement | A3 | Cognitive Apprenticeship + Dual-Coding | Do the visuals do real explanatory work — actively reveal a mechanism… | 3.80±0.87 | 4.02±0.97 | 🟡 mid |
| D1 | `D1_speaker_delivery` | engagement | A3 | Keller ARCS + Mayer Voice/Coherence | Is the speaker's delivery conducive to sustained attention — expressiv… | 3.80±0.75 | 4.00±0.87 | 🟡 mid |
| D2 | `D2_visual_design` | engagement | A3 | Keller ARCS + Mayer Voice/Coherence | Is the overall visual design clean, readable, uncluttered, well-compos… | 3.80±0.75 | 3.68±0.80 | 🟡 mid |
| D3 | `D3_narrative_and_learner_agency` | engagement | A3 | Keller ARCS + Mayer Voice/Coherence | Does the video establish WHY the topic matters, build a question -> ex… | 3.60±1.11 | 3.29±1.08 | 🟢 frontier (spreads) |
| D4 | `D4_audio_production` | engagement | A3 | Keller ARCS + Mayer Voice/Coherence | Is the audio signal clear and continuous — decodable words (no mumblin… | 4.40±0.92 | 4.61±0.75 | 🟡 mid |
| E1 | `E1_embedded_questions` | engagement | A3 | Generative Learning + ICAP | Does the video include genuine questions, quizzes, or pause-and-think… | 3.30±1.42 | 2.34±1.41 | 🟢 frontier (spreads) |
| E2 | `E2_generative_prompts` | engagement | A3 | Generative Learning + ICAP | Does the video prompt learners to DO something generative — predict, e… | 3.00±1.10 | 2.18±1.23 | 🟢 frontier (spreads) |
| E3 | `E3_worked_examples` | pedagogical_logic | A2 | Generative Learning + ICAP | Does the video provide worked examples with progressive fading toward… | 3.60±0.66 | 2.88±1.21 | 🟢 frontier (spreads) |
| F1 | `F1_vocabulary_appropriateness` | adaptation | A3 | Expertise Reversal + Pre-training | Are technical terms introduced at a level appropriate for this learner… | 4.10±0.83 | 4.05±1.11 | 🟡 mid |
| F2 | `F2_prerequisite_awareness` | adaptation | A3 | Expertise Reversal + Pre-training | Does the video stay WITHIN this persona's prior knowledge… | 4.20±0.87 | 3.77±1.16 | 🟡 mid |
| F3 | `F3_pacing_fit` | adaptation | A3 | Expertise Reversal + Pre-training | Is the information density and speaking rate appropriate for this pers… | 3.80±1.08 | 3.86±1.12 | 🟡 mid |

## 2. Ceiling-effect summary

**🔴 Saturated on good/human videos (the ceiling):** A3 (4.90±0.30), A6 (4.80±0.40), C2 (4.80±0.40), C3 (4.60±0.49)

All **content-reasoning** metrics (structure, scaffolding, balance, curriculum depth, Bloom fit). Good teachers — human or AI — all clear them, so they do **not** discriminate quality *within the good band*. Each still spreads across the **full** population (e.g. A6 full-pop σ=1.36) → they saturate only among good videos, which is exactly why the **tier-2 rubric** drops A3/A5/A6/C2/C3.

**🟠 Near-ceiling:** A2 (4.50), A5 (4.70)

**🟢 Frontier — weak even on good videos (the real quality gap):** A4 (3.30±0.64), D3 (3.60±1.11), E1 (3.30±1.42), E2 (3.00±1.10), E3 (3.60±0.66)

Active-learning + explicit objectives. Even strong human teaching videos rarely embed genuine questions (E1), generative prompts (E2), faded worked examples (E3), or explicit objectives (A4). This is the frontier the rubric exposes: *almost no one teaches generatively* — and where a personalized system can actually win.

## 3. Per-metric detail

### Dimension A — Content Quality
*Learning-science source: Backward Design (Wiggins & McTighe) + Bloom's Taxonomy + KC/Curriculum framework; factual-correctness-as-design-constraint*

#### A1 · `A1_factual_accuracy`  —  🟡 mid
- **Definition:** Are spoken facts, formulas, data, AND on-screen figures/diagrams/equations factually correct for what the video teaches?
- **Anchors:** **1** Pervasive wrong/misleading content; a learner would draw false conclusions.  ·  **3** No substantive errors; any nitpicks negligible.  ·  **5** Exemplary correctness; visuals and statements are precise and well-matched to the science/math.
- **TM dimension:** accuracy  ·  **Scored by:** Agent 2 (objective content/logic judge)  ·  **Modalities needed:** transcript, visual  ·  **Discriminability:** low
- **Absorbs (legacy batch_audit flags → this single home):** `critical_fact_error_count`, `minor_slip_count`, `visual_alignment_issue_level`
- **Score floors:** Any uncorrected critical error (confidence>=0.8) caps A1<=2. primary_language in {mixed, non_english} caps A1=1.
- **Ceiling record:** human/good = 4.40±1.28 (min 1, n=10) · full-pop = 4.23±1.31 (range 1–5, n=56)

#### A2 · `A2_topic_coverage`  —  🟠 near-ceiling
- **Definition:** Does the video cover all topics implied by its title/learning goal, at appropriate depth (not absent, not so thin as to be essentially absent)?
- **Anchors:** **1** Multiple core topics absent; fails its stated scope.  ·  **3** All implied topics present with adequate coverage.  ·  **5** Notably richer than the title implies; goes meaningfully beyond stated scope.
- **TM dimension:** accuracy  ·  **Scored by:** Agent 2 (objective content/logic judge)  ·  **Modalities needed:** transcript  ·  **Discriminability:** medium
- **Absorbs (legacy batch_audit flags → this single home):** `title_depth_mismatch_level`, `content_completeness_level (title-implied half)`, `explanatory_depth_level (coverage half)`
- **Ceiling record:** human/good = 4.50±0.50 (min 4, n=10) · full-pop = 3.55±1.41 (range 1–5, n=56)

#### A3 · `A3_logical_structure`  —  🔴 CEILING
- **Definition:** Are concepts presented in a logical, coherent sequence, with each idea ordered after its prerequisites and conclusions following from their support?
- **Anchors:** **1** Concepts arrive before their prerequisites; conclusions unsupported; order obstructs understanding.  ·  **3** Sound order; no idea needs a later one to make sense.  ·  **5** Deliberately built sequence; each step motivates the next.
- **TM dimension:** pedagogical_logic  ·  **Scored by:** Agent 2 (objective content/logic judge)  ·  **Modalities needed:** transcript  ·  **Discriminability:** medium
- **Absorbs (legacy batch_audit flags → this single home):** `sequence_disorder_count`, `causal_inconsistency_count`
- **Ceiling record:** human/good = 4.90±0.30 (min 4, n=10) · full-pop = 4.41±0.65 (range 2–5, n=56)

#### A4 · `A4_learning_objectives`  —  🟢 frontier (spreads)
- **Definition:** Does the video state, near the start, what the learner will be able to do or understand afterwards (explicit objectives / 'what you'll learn')?
- **Anchors:** **1** No statement of purpose anywhere; learner cannot tell what success looks like (or stated objectives misrepresent the content).  ·  **3** Objectives or a clear 'what you'll learn' framing stated (or the single-concept goal is self-evident for a short clip).  ·  **5** Crisp objectives that are explicitly returned to and fulfilled.
- **TM dimension:** pedagogical_logic  ·  **Scored by:** Agent 2 (objective content/logic judge)  ·  **Modalities needed:** transcript  ·  **Discriminability:** high
- **Absorbs (legacy batch_audit flags → this single home):** `learning_objectives_level`
- **Ceiling record:** human/good = 3.30±0.64 (min 3, n=10) · full-pop = 2.82±0.91 (range 1–5, n=56)

#### A5 · `A5_curriculum_completeness`  —  🟠 near-ceiling
- **Definition:** Relative to the Key Learning Points in the course requirement, does the video cover every required point (not just title-implied topics)? Judge against the title if no requirement is given.
- **Anchors:** **1** Most key learning points missing or only named without explanation.  ·  **3** Most key points covered; one or two missing or only superficial.  ·  **5** All key points covered with appropriate depth, and connections between them made explicit.
- **TM dimension:** accuracy  ·  **Scored by:** Agent 2 (objective content/logic judge)  ·  **Modalities needed:** transcript  ·  **Discriminability:** unknown
- **Absorbs (legacy batch_audit flags → this single home):** `content_completeness_level (key-points half)`
- **Ceiling record:** human/good = 4.70±0.64 (min 3, n=10) · full-pop = 3.79±1.51 (range 1–5, n=56)

#### A6 · `A6_bloom_alignment`  —  🔴 CEILING
- **Definition:** Does the cognitive depth actually delivered match the target Bloom's level in the course requirement? Penalize BOTH under-shooting (only definitions when 'apply' is required) AND wasteful over-shooting (heavy derivation when only 'understand' is required).
- **Anchors:** **1** Severe mismatch: delivered depth far below or wastefully above target throughout.  ·  **3** Roughly on target; several sections at the wrong cognitive level.  ·  **5** Precisely calibrated to the target level, depth deliberately tuned to it.
- **TM dimension:** pedagogical_logic  ·  **Scored by:** Agent 2 (objective content/logic judge)  ·  **Modalities needed:** transcript  ·  **Discriminability:** unknown
- **Absorbs (legacy batch_audit flags → this single home):** `pure_calculation_bias_level (depth-vs-target half)`, `title_depth_mismatch_level (depth half)`
- **Ceiling record:** human/good = 4.80±0.40 (min 4, n=10) · full-pop = 4.16±1.36 (range 1–5, n=56)

### Dimension B — Cognitive Design (Mayer)
*Learning-science source: Mayer's Cognitive Theory of Multimedia Learning (CTML) + Sweller's Cognitive Load Theory (CLT)*

#### B1 · `B1_signaling`  —  🟡 mid
- **Definition:** Does the video use visual cues — highlights, arrows, boxing, color-coding, zoom, pointer/cursor, progressive reveal — to guide attention to the relevant part of the screen while narrating?
- **Anchors:** **1** Narration systematically references specific visual elements with no cueing; viewer cannot follow without pausing.  ·  **3** Basic signaling present and sufficient, or content simple enough that explicit cueing is unnecessary.  ·  **5** Consistently timed, precise signaling; viewer always knows where to look.
- **TM dimension:** engagement  ·  **Scored by:** Agent 3 (persona simulator)  ·  **Modalities needed:** visual  ·  **Discriminability:** high
- **Absorbs (legacy batch_audit flags → this single home):** `visual_signaling_level`
- **Ceiling record:** human/good = 3.80±0.60 (min 3, n=10) · full-pop = 3.95±0.81 (range 1–5, n=56)

#### B2 · `B2_segmenting`  —  🟡 mid
- **Definition:** Is the video segmented at cognitive turning points — with recaps, signposted transitions, or natural pauses between chunks — so the learner can assimilate before the next idea, without information overload?
- **Anchors:** **1** One undifferentiated stream, no chunk boundaries or recaps; cognitively overwhelming.  ·  **3** Reasonable chunking; topic shifts signposted or paced so the learner keeps up.  ·  **5** Deliberate segmentation with crisp recaps at every turning point.
- **TM dimension:** pedagogical_logic  ·  **Scored by:** Agent 3 (persona simulator)  ·  **Modalities needed:** transcript, visual  ·  **Discriminability:** high
- **Absorbs (legacy batch_audit flags → this single home):** `segmenting_level`, `information_overload_count`
- **Ceiling record:** human/good = 4.00±0.89 (min 3, n=10) · full-pop = 3.77±0.98 (range 2–5, n=56)

#### B3 · `B3_coherence`  —  🟡 mid
- **Definition:** Is the video free of irrelevant or distracting material — decorative animations with no teaching payload, tangents, excessive branding, seductive details (Mayer's coherence principle)?
- **Anchors:** **1** Eye-candy/tangents replace substance; learner asks 'why am I watching this?'.  ·  **3** Largely on-task; at most one minor decorative distraction.  ·  **5** Every element earns its place; nothing extraneous.
- **TM dimension:** engagement  ·  **Scored by:** Agent 3 (persona simulator)  ·  **Modalities needed:** transcript, visual  ·  **Discriminability:** low
- **Absorbs (legacy batch_audit flags → this single home):** `decorative_eye_candy_level`
- **Ceiling record:** human/good = 4.30±0.90 (min 3, n=10) · full-pop = 4.45±0.84 (range 2–5, n=56)

#### B4 · `B4_modality_integration`  —  🟡 mid
- **Definition:** Do narration and visuals COMPLEMENT each other (not redundant word-for-word text) and stay SYNCHRONIZED — the right picture present when the words need it, never fighting or ignoring each other?
- **Anchors:** **1** Visuals repeatedly contradict, lag, or distract from narration; learner must ignore the screen.  ·  **3** Narration and visuals generally aligned; at most one harmless mismatch.  ·  **5** Tight, complementary integration; words and visuals each carry distinct, synchronized load.
- **TM dimension:** engagement  ·  **Scored by:** Agent 3 (persona simulator)  ·  **Modalities needed:** transcript, audio, visual  ·  **Discriminability:** low
- **Absorbs (legacy batch_audit flags → this single home):** `disconnect_level`
- **Ceiling record:** human/good = 4.30±0.90 (min 3, n=10) · full-pop = 4.48±1.07 (range 1–5, n=56)

### Dimension C — Explanation Quality
*Learning-science source: Cognitive Apprenticeship (Collins) scaffolding/fading + Dual-Coding / worked-example explanation design*

#### C1 · `C1_examples_analogies`  —  🟡 mid
- **Definition:** Does the video use analogies, concrete examples, or multiple representations to make abstract concepts intuitive?
- **Anchors:** **1** Pure abstraction; no examples, analogies, or alternate representations.  ·  **3** At least one effective example/analogy for the key concept.  ·  **5** Rich, well-chosen examples and analogies throughout that genuinely build intuition.
- **TM dimension:** pedagogical_logic  ·  **Scored by:** Agent 3 (persona simulator)  ·  **Modalities needed:** transcript  ·  **Discriminability:** medium
- **Absorbs (legacy batch_audit flags → this single home):** — (new construct; no legacy flag)
- **Ceiling record:** human/good = 4.10±0.94 (min 3, n=10) · full-pop = 3.70±1.22 (range 1–5, n=56)

#### C2 · `C2_scaffolding_strategy`  —  🔴 CEILING
- **Definition:** Does the video build from what the learner knows to what they need (known->unknown bridge), motivate each formula/step (intuition, derivation sketch, limiting case), and avoid unjustified logic leaps?
- **Anchors:** **1** Formulas presented as facts with zero scaffolding; derivations riddled with unexplained leaps.  ·  **3** Definitions and reasoning present; at most one key 'why' skipped.  ·  **5** Every step motivated and bridged from prior knowledge; standout exposition.
- **TM dimension:** pedagogical_logic  ·  **Scored by:** Agent 2 (objective content/logic judge)  ·  **Modalities needed:** transcript  ·  **Discriminability:** high
- **Absorbs (legacy batch_audit flags → this single home):** `scaffolding_failure_level`, `missing_scaffolding_level`
- **Ceiling record:** human/good = 4.80±0.40 (min 4, n=10) · full-pop = 4.25±0.85 (range 2–5, n=56)

#### C3 · `C3_conceptual_procedural_balance`  —  🔴 CEILING
- **Definition:** Is there an appropriate balance between 'understanding why' (concept) and 'knowing how to do' (procedure), rather than a drill of worked calculations with thin theory?
- **Anchors:** **1** Almost pure calculation/procedure (>85%); a worked-examples playlist with no conceptual spine.  ·  **3** Theory and procedure both present and reasonably balanced for the goal.  ·  **5** Concept-first spine; calculations subordinate, illustrating rather than dominating.
- **TM dimension:** pedagogical_logic  ·  **Scored by:** Agent 2 (objective content/logic judge)  ·  **Modalities needed:** transcript  ·  **Discriminability:** high
- **Absorbs (legacy batch_audit flags → this single home):** `pure_calculation_bias_level`
- **Ceiling record:** human/good = 4.60±0.49 (min 4, n=10) · full-pop = 4.21±0.99 (range 1–5, n=56)

#### C4 · `C4_visual_explanation_power`  —  🟡 mid
- **Definition:** Do the visuals do real explanatory work — actively reveal a mechanism (how/why), not merely decorate or restate the conclusion as text? Static/decorative where a dynamic build is needed scores low; a visual the concept would be harder to grasp WITHOUT scores high. (Judges explanatory USE of visuals only — geometric/factual correctness of the figure is scored under A1, not here.)
- **Anchors:** **1** Visuals static or decorative; all conceptual work done by narration; OR narration actively ignores/devalues the visual.  ·  **3** Key concepts have supporting visuals that illustrate the idea.  ·  **5** Visuals carry genuine explanatory load; the chosen visual approach makes the concept clearer than words alone could.
- **TM dimension:** engagement  ·  **Scored by:** Agent 3 (persona simulator)  ·  **Modalities needed:** transcript, visual  ·  **Discriminability:** unknown
- **Absorbs (legacy batch_audit flags → this single home):** `visual_pairing_level`, `ineffective_visual_representation_level`
- **Pilot-validated:** Confirmed 2026-06-02: drops cleanly when narration stops leveraging / devalues the visual (C4txt_severe -> -0.67 swing). The OLD visual-only degradation (curve removed) did NOT move it — detection requires the defect to surface in narration.
- **Ceiling record:** human/good = 3.80±0.87 (min 3, n=10) · full-pop = 4.02±0.97 (range 2–5, n=56)

### Dimension D — Engagement & Presentation
*Learning-science source: Keller ARCS motivation model + Mayer Voice/Personalization & Coherence principles*

#### D1 · `D1_speaker_delivery`  —  🟡 mid
- **Definition:** Is the speaker's delivery conducive to sustained attention — expressive (not flat/monotone/robotic) AND FLUENT (not halting, stuttering, or full of false starts/repetitions)?
- **Anchors:** **1** Persistently soporific (drone/monotone) OR so disfluent — stutters, restarts, repeated words, broken cadence — that following the delivery is a strain.  ·  **3** Clear and followable; neither notably flat nor notably disfluent.  ·  **5** Energizing, well-paced, fluent delivery that actively sustains attention.
- **TM dimension:** engagement  ·  **Scored by:** Agent 3 (persona simulator)  ·  **Modalities needed:** audio  ·  **Discriminability:** high
- **Absorbs (legacy batch_audit flags → this single home):** `monotone_audio_level`
- **Adds (new construct):** disfluency / halting delivery (NEW — closes the D4txt pilot gap; the old intelligibility+continuity flags could not catch stuttering because clear-but-stuttered speech is still intelligible and gap-free)
- **Ceiling record:** human/good = 3.80±0.75 (min 3, n=10) · full-pop = 4.00±0.87 (range 1–5, n=56)

#### D2 · `D2_visual_design`  —  🟡 mid
- **Definition:** Is the overall visual design clean, readable, uncluttered, well-composed (hierarchy/alignment/spacing), free of generic 'AI-slop' imagery, with legible on-screen text/labels — and is any animation/motion smooth and well-crafted? (Whether the visual HELPS understanding is C4, not here.)
- **Anchors:** **1** Cluttered, poorly composed, illegible text, or dominant generic AI art throughout.  ·  **3** Clean and readable; at most one weak slide.  ·  **5** Polished, consistent, professional composition — and smooth, well-crafted animation where present — that aids reading.
- **TM dimension:** engagement  ·  **Scored by:** Agent 3 (persona simulator)  ·  **Modalities needed:** visual  ·  **Discriminability:** low
- **Absorbs (legacy batch_audit flags → this single home):** `visual_clutter_level`, `slide_layout_level`, `written_text_legibility_level`, `visual_accessibility_level`, `ai_generated_fatigue_level`
- **Ceiling record:** human/good = 3.80±0.75 (min 3, n=10) · full-pop = 3.68±0.80 (range 1–5, n=56)

#### D3 · `D3_narrative_and_learner_agency`  —  🟢 frontier (spreads)
- **Definition:** Does the video establish WHY the topic matters, build a question -> exploration -> resolution arc, and position the learner as an active discoverer rather than a passive recipient?
- **Anchors:** **1** No motivational framing; content starts abruptly; learner purely passive.  ·  **3** Clear relevance ('why this matters') plus a summary/takeaway.  ·  **5** Sustained narrative arc and 'aha' moments; learner consistently framed as discoverer.
- **TM dimension:** engagement  ·  **Scored by:** Agent 3 (persona simulator)  ·  **Modalities needed:** transcript  ·  **Discriminability:** unknown
- **Absorbs (legacy batch_audit flags → this single home):** `narrative_agency_level`
- **Ceiling record:** human/good = 3.60±1.11 (min 2, n=10) · full-pop = 3.29±1.08 (range 1–5, n=56)

#### D4 · `D4_audio_production`  —  🟡 mid
- **Definition:** Is the audio signal clear and continuous — decodable words (no mumbling/clipping/masking noise) and smooth joins (no abrupt voice-identity shifts, overlaps, gaps, or robotic cut-offs at transitions)?
- **Anchors:** **1** Largely unintelligible or pervasive splice/dropout artifacts dominate listening.  ·  **3** Clear and continuous; at most one minor artifact.  ·  **5** Studio-clean, seamless audio throughout.
- **TM dimension:** engagement  ·  **Scored by:** Agent 3 (persona simulator)  ·  **Modalities needed:** audio  ·  **Discriminability:** medium
- **Absorbs (legacy batch_audit flags → this single home):** `speech_intelligibility_level`, `audio_continuity_level`
- **Ceiling record:** human/good = 4.40±0.92 (min 3, n=10) · full-pop = 4.61±0.75 (range 3–5, n=56)

### Dimension E — Active Learning Design
*Learning-science source: Generative Learning Theory (Wittrock) + ICAP (Chi) + Retrieval Practice + Worked-Example→Faded→Independent*

#### E1 · `E1_embedded_questions`  —  🟢 frontier (spreads)
- **Definition:** Does the video include genuine questions, quizzes, or pause-and-think prompts during viewing (not rhetorical questions the narrator immediately answers)?
- **Anchors:** **1** Fully passive; no embedded questions or pauses.  ·  **3** At least one genuine posed question with room to think.  ·  **5** Well-placed checks for understanding at the right cognitive moments.
- **TM dimension:** engagement  ·  **Scored by:** Agent 3 (persona simulator)  ·  **Modalities needed:** transcript  ·  **Discriminability:** high
- **Absorbs (legacy batch_audit flags → this single home):** `active_learning_level (question half)`
- **Ceiling record:** human/good = 3.30±1.42 (min 1, n=10) · full-pop = 2.34±1.41 (range 1–5, n=56)

#### E2 · `E2_generative_prompts`  —  🟢 frontier (spreads)
- **Definition:** Does the video prompt learners to DO something generative — predict, explain, draw, summarize, 'try it yourself'?
- **Anchors:** **1** No invitation to generate anything; watch-only.  ·  **3** At least one real generative prompt with room to act.  ·  **5** Recurrent generative activity woven through the lesson.
- **TM dimension:** engagement  ·  **Scored by:** Agent 3 (persona simulator)  ·  **Modalities needed:** transcript  ·  **Discriminability:** high
- **Absorbs (legacy batch_audit flags → this single home):** `active_learning_level (generative half)`
- **Ceiling record:** human/good = 3.00±1.10 (min 1, n=10) · full-pop = 2.18±1.23 (range 1–5, n=56)

#### E3 · `E3_worked_examples`  —  🟢 frontier (spreads)
- **Definition:** Does the video provide worked examples with progressive fading toward independent practice (full worked -> partially worked -> learner does it)?
- **Anchors:** **1** No worked examples where the procedure clearly needs them.  ·  **3** Worked examples present and clearly stepped.  ·  **5** Deliberate fading from fully-worked to independent practice.
- **TM dimension:** pedagogical_logic  ·  **Scored by:** Agent 2 (objective content/logic judge)  ·  **Modalities needed:** transcript, visual  ·  **Discriminability:** high
- **Absorbs (legacy batch_audit flags → this single home):** — (new construct; no legacy flag)
- **Ceiling record:** human/good = 3.60±0.66 (min 3, n=10) · full-pop = 2.88±1.21 (range 1–5, n=56)

### Dimension F — Learner Adaptability
*Learning-science source: Expertise Reversal Effect + Pre-training/Advance Organizers + Learning Hierarchy (prerequisite structure); persona-adaptation falsifiability commitment*

#### F1 · `F1_vocabulary_appropriateness`  —  🟡 mid
- **Definition:** Are technical terms introduced at a level appropriate for this learner's grade/background, with definitions when needed (undefined jargon beyond their stated knowledge counts against)?
- **Anchors:** **1** Pervasive undefined jargon beyond the persona's level.  ·  **3** Terms generally pitched right; key new terms defined.  ·  **5** Vocabulary precisely tuned to the persona; every new term scaffolded.
- **TM dimension:** adaptation  ·  **Scored by:** Agent 3 (persona simulator)  ·  **Modalities needed:** transcript  ·  **Discriminability:** low
- **Absorbs (legacy batch_audit flags → this single home):** `jargon_overload_level`
- **Ceiling record:** human/good = 4.10±0.83 (min 3, n=10) · full-pop = 4.05±1.11 (range 1–5, n=56)

#### F2 · `F2_prerequisite_awareness`  —  🟡 mid
- **Definition:** Does the video stay WITHIN this persona's prior knowledge? Scored by DEDUCTION: penalize ONLY when the content assumes or requires knowledge the persona LACKS (esp. items under the persona's 'Lacks'). Do NOT require the video to actively mention, review, or re-teach prerequisites — a video pitched correctly at the persona scores high even if it never revisits background. This measures over-assumption, not the presence of prerequisite coverage.
- **Anchors:** **1** Core steps require knowledge the persona lacks; the persona would be lost and give up.  ·  **3** Mostly within the persona's reach; a few spots assume something under 'Lacks' but can be patched while watching.  ·  **5** Stays entirely within the persona's prior knowledge; nothing is assumed beyond their background (no active prerequisite review required to earn this).
- **TM dimension:** adaptation  ·  **Scored by:** Agent 3 (persona simulator)  ·  **Modalities needed:** transcript  ·  **Discriminability:** medium
- **Absorbs (legacy batch_audit flags → this single home):** `prerequisite_gap_level`
- **Ceiling record:** human/good = 4.20±0.87 (min 3, n=10) · full-pop = 3.77±1.16 (range 1–5, n=56)

#### F3 · `F3_pacing_fit`  —  🟡 mid
- **Definition:** Is the information density and speaking rate appropriate for this persona's grade and Focus Time — not too rushed, not padded, not over-rehashing what they already know? Judge by on-screen PACE / information density relative to Focus Time, NOT by raw total duration: a longer video that stays within the persona's pace and finishes the material is fine.
- **Anchors:** **1** Unwatchable for this persona: Focus Time blown by padding, or so dense/fast that constant rewinding is needed.  ·  **3** Occasionally too fast/slow but finishes within Focus Time without major frustration.  ·  **5** Rhythm and density ideally matched to this persona's attention and baseline.
- **TM dimension:** adaptation  ·  **Scored by:** Agent 3 (persona simulator)  ·  **Modalities needed:** transcript, audio  ·  **Discriminability:** medium
- **Absorbs (legacy batch_audit flags → this single home):** `pacing_mismatch_level`
- **Ceiling record:** human/good = 3.80±1.08 (min 2, n=10) · full-pop = 3.86±1.12 (range 2–5, n=56)
