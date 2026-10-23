---
name: research-idea-motivation
description: Develop or review the evidence-based problem-motivation-method chain for LLM/NLP research candidates. Use during proposal, development, refinement, or review when a contribution sounds useful but its importance, causal rationale, or necessity is unclear.
---

## Input

Use the supplied topic, constraints, evidence, candidate, and current task schema. Treat this skill as a reasoning procedure, never scientific evidence. Do not access tools, scripts, files, or services; propose needed actions to the controller.

## Steps

1. Identify one observable bottleneck and its conditions. Separate source-backed observations from author interpretations and your inferred explanation. Attach existing evidence IDs to supported facts; state missing evidence explicitly.
2. Before proposing a method, describe a concrete case: input/situation, current response, observed failure or hypothesized limitation, and its consequence. For an unobserved phenomenon, explain a concrete scenario and make observing it part of the first test. A paper not trying a certain combination is not evidence of a problem. Establish the consequence: what important capability, practical use, or scientific understanding is blocked? Describe why resolving this problem would matter even if the favored technique failed. Do not manufacture a problem around that technique.
3. Reconstruct the strongest available alternative. Identify its assumption, what it already explains, and the specific remaining limitation. Similar titles trigger comparison, not abandonment; unknown full-text details remain unknown.
   Separate motivation novelty from method novelty. The main overlap question is whether the same observed difficulty, causal rationale and intended scientific claim are already addressed. Reusing an existing method is acceptable. Reframe the story around a different evidence-backed problem, explanation or boundary when justified; state the change and a discriminating prediction rather than merely changing terminology.
4. Connect the proposed intervention to a testable cause. Ask which observable should change if that cause is correct, and which competing explanation predicts something else. Treat the causal link as a hypothesis until supported.
5. Explain expected progress beyond an arbitrary metric delta. Efficiency can be substantive when it removes a binding constraint; a new explanation or failure boundary can matter without improving accuracy. Neither an added module nor a renamed tradeoff establishes progress alone.
6. Challenge the motivation with the strongest plausible counterargument: misread evidence, a low-value failure, an existing simple solution, or an intervention unrelated to the cause. Resolve the specific objection before polishing the story. Do not replace this reasoning with an overall score.
7. Specify the simplest alternative and a necessity test that could show the proposed mechanism adds nothing. During refinement preserve the original problem, hypothesis, and prediction; expose any required change rather than silently reframing success.

## Output

Return only the current task JSON. In propose, fill each candidate's `motivation`; in develop/refine, fill top-level `motivation`: `basis`, `problem_observation`, `evidence_ids`, `importance`, `existing_approach_limit`, `causal_explanation`, `why_this_method`, `expected_progress`, `simplest_alternative`, and `necessity_test`. Use `source_observation` for an observed problem with source IDs; use `research_hypothesis` for a plausible phenomenon or question to investigate, with an initial test of that phenomenon. Hypothetical premises do not need invented citations. In review, use `motivation_assessment`, `issues`, and `revision_instructions`. Keep all other required task fields.

## Failure behavior

If importance or causality lacks evidence, mark the uncertainty in the applicable text or review enum and identify the decisive missing evidence. Do not substitute confidence scores, invented experiments, or novelty claims. A weak current rationale warrants a concrete revision, not automatic termination. State the proposed explanation directly and attach a distinguishing test; avoid generic disclaimers about whether the idea is globally original or experiments have run.

Deliver a concrete proposal and improve it constructively. Normal idea-stage assumptions belong in the first-test design. Offer a motivation-led reframing when the starting story is weak. During refinement answer each critique explicitly: adopt, adapt, decline with reasons, or test. Preserve the user's direction; the initial hypothesis is allowed to improve, with the change explained.

## Synthetic decision contrast

“Add a confidence head to save tokens” leaves the motivation unresolved. A sharper hypothesis asks whether observable signals predict benefit from additional computation, then compares against fixed-budget allocation. This is an illustrative test proposal, not a demonstrated finding or novel idea.
