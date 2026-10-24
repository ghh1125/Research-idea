---
name: research-idea-design-falsification
description: Design the first discriminating test for an LLM/NLP research hypothesis. Use during develop, refine, or review to replace vague feasibility claims with operational tests, meaningful controls, and positive, negative, or inconclusive interpretations.
---

## Input

Use the supplied hypothesis, method, motivation, evidence, available resources, and unresolved assumptions. Plan tests only. Do not execute scripts, access tools, or imply that experiments have already run.

## Steps

1. Choose the weakest consequential assumption: the one whose failure would change the research decision. Separate implementation uncertainty, signal availability, mechanism plausibility, and outcome validity; a runtime check answers only the first.
2. Choose the cheapest informative action. Use source or code inspection for unknown interfaces; a signal diagnostic for observability; an oracle analysis for possible headroom; a controlled intervention for causal alternatives. Specify what each possible answer would change.
3. Operationalize `first_test`: experimental units or examples, data partition, intervention, measured quantity, comparator, and decision rule. Derive thresholds or sample-size needs from supplied information; otherwise state what must be calibrated. Do not invent baseline values or statistical power.
   Separate the first informative comparison from a later confirmation suite. Order it as a tiny interface/data check, the strongest simple baseline, then the minimum mechanism comparison. Estimate the first-test cost separately. Put optional scaling and broad ablations in the next action, rather than turning the first experiment into a full paper's matrix.
4. Include a simple alternative, the closest relevant baseline, and controls for plausible rival explanations. Match resources relevant to the claim, including extra inference calls and selection overhead. Make the necessity test capable of showing the proposed mechanism is unnecessary.
5. Check that a reduced pilot retains the mechanism and regime being studied. If scaling down removes them, select another diagnostic or mark the test infeasible under the budget. Do not interpret absence of signal in an inadequate pilot as refutation.
   State the bridge from the pilot to the representative task: what stays the same, what changes, and what pilot result would justify that next step. Keep the first comparison small without manufacturing difficulty or confusing a hand-built example with the whole research claim.
6. Define three outcomes before execution: supportive evidence within stated conditions; evidence against the specific hypothesis; and inconclusive measurement or insufficient sensitivity. Reserve independent confirmation data after adaptive exploration. Label predictions separately from supplied observations.

## Output

Return only the current task JSON. In develop/refine, populate `validation.weakest_assumption`, `first_test`, `baselines`, `controls`, `positive`, `negative`, `inconclusive`, and `budget_estimate`; align `motivation.necessity_test`, `feasibility.checks`, and `next_action`. In review, use `issues`, `motivation_assessment.decisive_test`, and `next_action`. Preserve all other required task fields.

## Failure behavior

Route implementation errors to debugging, resource obstacles to an available substitute or a smaller pilot, and inadequate measurements to redesign. Only relevant evidence can weaken the core hypothesis; related titles cannot. Preserve informative negative outcomes without retroactively changing predictions. Resource estimates and reviewer agreement never demonstrate effectiveness.

## Synthetic decision contrast

If adaptive retrieval outperforms one fixed retrieval call, extra calls may explain the gain. Compare against fixed or random retrieval at the same budget and record overhead. A disappearing advantage challenges the adaptive-selection claim, not necessarily retrieval's usefulness. These are hypothetical outcomes, not experimental results.

In `validation.summary`, briefly explain the first test, simplest comparator, measured outcome, and decision. Keep detailed branches, controls and cost accounting in the other validation fields.
