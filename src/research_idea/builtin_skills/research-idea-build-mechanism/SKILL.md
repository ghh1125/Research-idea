---
name: research-idea-build-mechanism
description: Turn a research hypothesis into a concrete, minimal LLM/NLP method. Use during develop or refine when an idea needs explicit interfaces, information flow, learning signals, inference operations, and a mechanism-level contribution.
---

## Input

Use the supplied candidate, motivation, source evidence, constraints, and any existing method specification. Do not inspect repositories or execute anything; describe missing inspections through the current task's `next_action`.

## Steps

1. Anchor the original problem, hypothesis, and predicted observation. Identify the single causal link the intervention should change. Preserve these anchors during refinement; distinguish an improved explanation from a different research claim.
2. Trace one example from inputs through intermediate representations to outputs. Name each operation, its required information, when that information exists, and the interface it crosses. Put relevant dimensions or shapes in the method text when known; do not invent implementation facts.
3. Identify the reusable backbone or implementation and the smallest required changes. Separate source-supported components from proposed components. For every added component, ask what breaks if a simple rule or existing component replaces it.
4. Make training explicit: trainable and frozen parameters, supervision acquisition, objective, and how the learning signal reaches the changed parameters. For discrete or nondifferentiable operations, specify a justified optimization route or leave that link unverified. For inference-only methods, state why training fields are inapplicable.
5. Reconstruct inference without evaluator-only labels, future information, or inaccessible model internals. Count additional calls and major resource terms as estimates. Include preprocessing and auxiliary-model costs when they affect the claimed benefit.
6. Describe what variable changes relative to closest work and what distinct observable consequence follows. Shared terminology does not establish coverage; cosmetic renaming, dataset substitution, or extra modules do not establish novelty. Preserve unresolved comparisons for targeted reading.

## Output

Return only the current develop/refine JSON. Fill `method.base_implementation`, `changes`, `inputs`, `outputs`, `trainable_parameters`, `frozen_parameters`, `objective`, `supervision`, `inference_steps`, `resource_requirements`, and `assumptions`. Coordinate these with `motivation.why_this_method`, `novelty_claim`, and `feasibility.required_signals`; retain all other required fields. Attach evidence IDs only to supplied source facts. Label design choices and predictions as proposals.

## Failure behavior

An unspecified interface or missing signal becomes an explicit assumption and verification action, not a claim that implementation works. If a substitute changes the hypothesis, explain the change and request revision through `next_action`; never silently repair the claim. Do not fabricate code availability, measurements, or completed experiments.

## Synthetic decision contrast

A router requiring the correct answer during inference has an unavailable input. An oracle router may diagnose possible headroom; a deployable router still needs an observable signal and its own test. This example illustrates information flow only, not an established research result.
