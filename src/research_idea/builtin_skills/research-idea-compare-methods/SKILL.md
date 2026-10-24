---
name: research-idea-compare-methods
description: Compare a research candidate with the closest supplied methods at the mechanism and claim level. Use for novelty checks, related-work concerns, or a reviewer claiming that an idea has already been done.
---

# Compare mechanisms and conditions

## Inputs
Use the candidate problem, hypothesis, method specification, source records and verified evidence IDs. Similar titles identify reading targets; they do not establish duplication.

## Procedure
1. Restate the candidate's smallest central claim. Separate inherited components from its proposed new interaction, explanatory claim, boundary, or capability.
   Start with motivation overlap: compare the observed problem, the limitation that makes it important, the causal explanation and the knowledge the study would establish. Shared methods are reusable tools, not an automatic duplicate verdict. A new motivation can justify an existing method when it answers a materially different question, distinguishes explanations, or establishes an untested boundary. A shared broad topic is not a shared motivation. Express these comparisons within problem, mechanism and claim, with source evidence.
2. During first-round proposal, fill positioning for the closest relevant sources: addressed_problem, remaining_question and contribution with that paper’s evidence. Improve a motivation already answered by supplied work before proposing it. During develop/refine, fill the six detailed comparisons: problem, mechanism, information, objective, evaluation, claim. Give concrete prior_detail and proposed_detail, relation same/different/unknown, and evidence_ids from that paper.
3. Trace both information paths: what is available during training, inference, and evaluation; what intervention changes the computation; what observable the claim predicts. Compare conditions rather than technique names.
4. Ask whether the prior method already implies the candidate's central prediction under comparable conditions. Distinguish topical overlap, shared problem, shared mechanism, and actual core-claim coverage.
5. Challenge every claimed difference: would it survive renaming modules, equalizing compute, using the same data, or replacing a component with the simplest baseline? A dataset swap or unmotivated tradeoff alone is not a substantive research gap.
6. When related work leaves a consequential boundary or assumption open, retain that route with an explicit test. If it truly covers the claim, record the narrow overlap and seek a meaningful reformulation without silently changing the hypothesis.
   Before abandoning a candidate, give a motivation-led reframing route when the evidence supports one. The story may change; explain what changed and what new prediction or test follows. Do not demand a new algorithm for an explanatory or boundary contribution, and do not label inherited machinery as a new mechanism.

## Output
In propose, fill positioning and the motivation argument without expanding a full technical protocol. In develop/refine, fill prior_art.overlaps and novelty_claim in the active method schema. Explain the changed variable, observable consequence, falsifier, and nontriviality. Supply follow-up queries only for a consequential unresolved relation. Technical borrowing from another domain is useful even when the mechanism itself is established; distinguish its source problem from the question our idea answers. A justified local difference is not proof of global novelty.

## Missing evidence
Use unknown for unavailable details and uncertain for unsupported coverage. A covered recommendation needs a same-claim, six-dimensional comparison backed by full-text evidence, including reported_result evidence in the evaluation comparison; its semantics still require review. An author claim alone cannot establish that the problem was empirically solved. Unproven efficacy does not make a preexisting mechanism novel. Never reject an idea merely because a related title exists.

## Synthetic example
Two methods both allocate extra decoding steps. One assumes a fixed external verifier; the candidate learns when that verifier is unreliable. The shared allocation topic does not settle overlap. Check the verifier access, learning signal, reliability intervention, and conditional prediction before deciding whether the difference is meaningful.
