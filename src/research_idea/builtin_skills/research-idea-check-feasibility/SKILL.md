---
name: research-idea-check-feasibility
description: Design an executable path for an LLM/NLP idea. Use when proposing, developing or reviewing a method that may rely on unavailable labels, logits, gradients, model access, data, compute or evaluation assumptions.
---

# Design a workable implementation path

## Inputs
Use the method, resource constraints, supplied evidence, and proposed first experiment. Treat an unmeasured resource estimate as unknown. A plausible algorithm is not an executed implementation.

## Procedure
During first-round propose, trace one representative example before presenting the idea. Fill feasibility_sketch with inputs actually available to the agent, an available_path through the key operation, the key_assumption and first_check. A simple pilot must preserve the scientific question. If a hidden answer, unexposed API signal or circular supervision is needed, redesign now using obtainable inputs. Separate what the agent observes from what the evaluator knows. Explain why the existing simplest solution does not already answer the question. Unknown resource measurements call for a small configurable pilot, not a demand for completed experiments. Leave the detailed seven-dimension protocol to technical design.

Inspect the example's observation/action contract now. Can a minimal reactive policy finish using the visible state? Are the intended outcomes reachable through the allowed actions? What useful decision actually requires the proposed inference? Resolve a needless inference step or an unreachable task within the idea; never create difficulty by hiding normally visible information. These are internal reasoning checks, not another user-facing gate or a requirement to execute experiments in phase one.

During develop, refine or review:
1. Walk one sample through training, inference, and evaluation. List every required signal and when it is used: labels, scores, logits, gradients, hidden states, retrieval, tools and annotations. Identify who produces each signal.
2. Identify the concrete interfaces and data transformations between steps. For learned components, follow the supervision and gradient path. For API-only access, do not assume weights, token probabilities or gradients are exposed.
3. Fill exactly seven feasibility.checks: data_access, inference_signal, interface, learning_signal, compute, evaluation, minimal_test. For each give requirement, status, evidence_ids, verification_plan and failure_action.
4. Use source_supported only with relevant source evidence, and preserve differences between the paper's environment and this project. It never means locally tested. Use unverified for uninspected access, interfaces or resource estimates. For not_applicable, explain why the method does not need that prerequisite.
5. For each required_signal give needed_at, availability, acquisition_plan and substitute. State explicitly when no acquisition path or valid substitute is known. A substitute is a new hypothesis until tested.
6. Identify the earliest decisive check: inspect a data example, verify an API response, trace one gradient, measure one representative batch, or test an evaluator with a deliberately wrong answer. Describe the action; do not claim it was run.
7. Make the minimum experiment preserve the central mechanism. A toy setup that supplies an unavailable deployment signal cannot establish deployment feasibility.

## Output
For propose, populate feasibility_sketch in the active schema. For technical design, populate feasibility and the operational method fields; put the weakest prerequisite and its check in validation. Fix known implementation contradictions in the proposal itself, rather than merely recording a warning for later.

## Failure behavior
An unavailable signal calls for a concrete redesign: remove the dependency, choose an observable substitute, or use an oracle only as a clearly identified diagnostic control. Update the actual method and signal list together. Unknown access or unmeasured cost calls for a small configurable pilot. Keep the research idea and improve its implementation path; do not turn normal pre-experiment uncertainty into an approval gate. A proposed substitute is still a hypothesis to test, and an oracle is not a deployment method.

## Synthetic example
A controller chooses the better answer by comparing against the hidden test label. Labels exist for evaluation but not inference. Mark that inference dependency unavailable. An oracle comparison may still diagnose headroom; a deployable estimator requires its own learning signal and validation.
