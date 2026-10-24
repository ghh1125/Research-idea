---
name: research-idea-motivation
description: Develop or review the evidence-based background-problem-motivation-method chain for LLM/NLP research candidates. Use during proposal, development, refinement, or review when a contribution sounds useful but its importance, causal rationale, or necessity is unclear.
---

## Input

Use the supplied topic, constraints, evidence, candidate, and current task schema. Treat this skill as a reasoning procedure, never scientific evidence. Do not access tools, scripts, files, or services; propose needed actions to the controller.

## Steps

1. Start with a concrete background setting and what it needs to accomplish. Explain the bottleneck that prevents it; the problem must follow from that setting, not from the popularity of a technique. Separate source-backed observations from author interpretations and your inferred explanation. Attach existing evidence IDs to supported facts; state missing evidence explicitly.
2. Before proposing a method, describe a concrete case: input/situation, current response, observed failure or hypothesized limitation, and its consequence. For an unobserved phenomenon, explain a concrete scenario and make observing it part of the first test. A paper not trying a certain combination is not evidence of a problem. Establish the consequence: what important capability, practical use, or scientific understanding is blocked? Describe why resolving this problem would matter even if the favored technique failed. Do not manufacture a problem around that technique.
3. Reconstruct the strongest available alternative. Identify its assumption, what it already explains, and the specific remaining limitation. Similar titles trigger comparison, not abandonment; unknown full-text details remain unknown.
   Use the claim audit now: author claim → tested conditions and controls → reported result → warranted conclusion. Do not let a broad abstract claim erase a concrete open problem. An already proposed mechanism remains prior art even if its claimed efficacy was not adequately established; the new contribution must then be a meaningful question, explanation, boundary or justified change.
   Separate motivation novelty from method novelty. The main overlap question is whether the same observed difficulty, causal rationale and intended scientific claim are already addressed. Reusing an existing method is acceptable. Reframe the story around a different evidence-backed problem, explanation or boundary when justified; state the change and a discriminating prediction rather than merely changing terminology.
4. Connect the proposed intervention to a testable cause. Ask which observable should change if that cause is correct, and which competing explanation predicts something else. Treat the causal link as a hypothesis until supported.
5. Explain expected progress beyond an arbitrary metric delta. Identify the new capability or understanding, or the binding limitation removed. Each link must justify the next: a compelling background alone does not justify a weak problem, and a sophisticated technique does not justify an unrelated intervention. Efficiency can be substantive when it removes a binding constraint; a new explanation or failure boundary can matter without improving accuracy. Neither an added module nor a renamed tradeoff establishes progress alone.
6. Challenge the motivation with the strongest plausible counterargument: misread evidence, a low-value failure, an existing simple solution, or an intervention unrelated to the cause. Resolve the specific objection before polishing the story. Do not replace this reasoning with an overall score.
7. Specify the simplest alternative and a necessity test that could show the proposed mechanism adds nothing. During refinement keep the background, problem, hypothesis, method and prediction consistent; explain substantive reframing.
8. Separate the research setting from its first small test. Name the real task or scientific question that makes the result useful, the difficulty a reduced test preserves, and the next representative setting it informs. A transparent example helps explain the mechanism; solving only a contrived puzzle is not the contribution.

## Output
When choosing a question, consider a contradictory result, an untested assumption, a transferable mechanism, a new operating regime or an informative diagnosis as appropriate. Use these as alternative ways to understand the literature, not a quota of ideas or extra roles. Prefer a consequential question with one clear mechanism. State what would be learned if the strongest simple alternative explains the effect; useful negative evidence can change the explanation or design.


Return only the current task JSON. In propose, fill each candidate's `motivation`; in develop/refine, fill top-level `motivation`: `basis`, `background`, `problem_observation`, `evidence_ids`, `importance`, `existing_approach_limit`, `causal_explanation`, `why_this_method`, `expected_progress`, `simplest_alternative`, and `necessity_test`. Use `source_observation` for an observed problem with source IDs; use `research_hypothesis` for a plausible phenomenon or question to investigate, with an initial test of that phenomenon. Hypothetical premises do not need invented citations. In review, use `motivation_assessment`, `issues`, and `revision_instructions`. Keep all other required task fields.

Make the narrative answer directly: what is the new substantive problem, why does it matter, and how does this idea address it? State the setting, bottleneck, consequence and proposed intervention in concrete language. Avoid generic '尚未确认' or originality disclaimers. A meaningful condition belongs in the relevant input, design decision or first test. Keep facts, hypotheses and planned experiments distinct without repeating cautionary labels.

## Failure behavior

If importance or causality lacks evidence, mark the uncertainty in the applicable text or review enum and identify the decisive missing evidence. Do not substitute confidence scores, invented experiments, or novelty claims. A weak current rationale warrants a concrete revision, not automatic termination. State the proposed explanation directly and attach a distinguishing test; avoid generic disclaimers about whether the idea is globally original or experiments have run.

Deliver a concrete proposal and improve it constructively. Normal idea-stage assumptions belong in the first-test design. Offer a motivation-led reframing when the starting story is weak. During refinement answer each critique explicitly: adopt, adapt, decline with reasons, or test. Preserve the user's direction; the initial hypothesis is allowed to improve, with the change explained.

## Synthetic decision contrast

“Add a confidence head to save tokens” leaves the motivation unresolved. A sharper hypothesis asks whether observable signals predict benefit from additional computation, then compares against fixed-budget allocation. This is an illustrative test proposal, not a demonstrated finding or novel idea.
