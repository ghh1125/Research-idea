---
name: research-idea-build-mechanism
description: Suggest relevant technical routes for a substantive LLM/NLP research idea. Use during design_transfer, develop or refine when an idea needs explicit interfaces, information flow, learning signals, inference operations, and a mechanism-level contribution.
---

## Input

Use the supplied candidate, motivation, source evidence, constraints, and any existing method specification. Do not inspect repositories or execute anything; describe missing inspections through the current task's `next_action`.

## Steps

1. Connect the background need, specific problem, motivating cause and intended scientific contribution. Identify the causal link the intervention should change. The first-round idea supplies the question; the technical route may improve as new papers are read.
2. Reason internally through the information dependencies from inputs to outputs without writing a worked example. Name each operation, its required information, when that information exists, and the interface it crosses. Put relevant dimensions or shapes in the method text when known; do not invent implementation facts.
3. Look for a reusable principle wherever it fits in computer science, including another subfield. Map the shared structure, original assumptions and observable inputs to this problem. Identify the reusable backbone or implementation and the smallest required changes. Explain the resulting technique through the target setting: which bottleneck it addresses, which objects and signals it operates on, which operation changes, and why the change is necessary here. Retain attribution for the borrowed principle; a renamed technique or a list of modules is not an adaptation. Separate source-supported components from proposed components. For every added component, ask what breaks if a simple rule or existing component replaces it.
4. Make training explicit: trainable and frozen parameters, supervision acquisition, objective, and how the learning signal reaches the changed parameters. For discrete or nondifferentiable operations, specify a justified optimization route or leave that link unverified. For inference-only methods, state why training fields are inapplicable.
5. Reconstruct inference without evaluator-only labels, future information, or inaccessible model internals. Name major resource dependencies when they affect the claimed benefit; do not invent call counts or detailed budgets.
6. Describe what variable changes relative to closest work and what distinct observable consequence follows. Shared terminology does not establish coverage; cosmetic renaming, dataset substitution, or extra modules do not establish novelty. Preserve unresolved comparisons for targeted reading.

## Output
When mapping a source technique to the target, state what plays the role of what: objects, observations, decisions and feedback. Identify the source condition that could fail here, and compare against the simplest viable route before adding another component. An objection calls for a reasoned design choice or a discriminating test, not automatic complexity.


Return only the active task JSON. For design_transfer, give up to three options answering the reading question: source technique → shared structure → conditions → proposed adaptation → reason it helps → simpler alternative. Leave the compatibility field first_test empty. Cite the supplied source evidence for the original technique; describe the transfer as a proposal. Empty options with a concrete reading gap are appropriate when the supplied passages do not explain a usable technique. For develop/refine, suggest one or two suitable routes and record them in design_decisions with first_test empty; borrowed options are not a required module list. Give `method.summary` as a short explanation of the actual mechanism in the target setting and its main actions. State the chosen operation and its purpose directly; replace generic caveats with the concrete input or design choice that matters. Keep method fields concise: key operations, usable information and important dependencies; no exhaustive state/action contracts or experimental protocols. Fill `method.base_implementation`, `changes`, `inputs`, `outputs`, `trainable_parameters`, `frozen_parameters`, `objective`, `supervision`, `inference_steps`, `resource_requirements`, and `assumptions`. Coordinate these with `motivation.why_this_method`, `novelty_claim`, and `feasibility.required_signals`; retain all other required fields. Attach evidence IDs only to supplied source facts. Label design choices and predictions as proposals.

## Failure behavior

An unspecified interface or missing signal becomes an explicit assumption and verification action, not a claim that implementation works. If a substitute changes the hypothesis, update the rationale and explain the changed prediction. A concrete redesign is more useful than a pending approval label. Do not fabricate code availability, measurements, or completed experiments.

## Synthetic decision contrast

A router requiring the correct answer during inference has an unavailable input. An oracle router may diagnose possible headroom; a deployable router still needs an observable signal and its own test. This example illustrates information flow only, not an established research result.
