---
name: research-idea-check-feasibility
description: Audit whether an LLM/NLP method has an executable path. Use when developing or reviewing a method that may rely on unavailable labels, logits, gradients, model access, data, compute or evaluation assumptions.
---

# Design a workable implementation path

## Inputs
Use the method, resource constraints, supplied evidence, and proposed first experiment. Treat an unmeasured resource estimate as unknown. A plausible algorithm is not an executed implementation.

## Procedure
1. Walk one sample through training, inference, and evaluation. List every required signal and when it is used: labels, scores, logits, gradients, hidden states, retrieval, tools and annotations. Identify who produces each signal.
2. Identify the concrete interfaces and data transformations between steps. For learned components, follow the supervision and gradient path. For API-only access, do not assume weights, token probabilities or gradients are exposed.
3. Fill exactly seven feasibility.checks: data_access, inference_signal, interface, learning_signal, compute, evaluation, minimal_test. For each give requirement, status, evidence_ids, verification_plan and failure_action.
4. Use source_supported only with relevant source evidence, and preserve differences between the paper's environment and this project. It never means locally tested. Use unverified for uninspected access, interfaces or resource estimates. For not_applicable, explain why the method does not need that prerequisite.
5. For each required_signal give needed_at, availability, acquisition_plan and substitute. State explicitly when no acquisition path or valid substitute is known. A substitute is a new hypothesis until tested.
6. Identify the earliest decisive check: inspect a data example, verify an API response, trace one gradient, measure one representative batch, or test an evaluator with a deliberately wrong answer. Describe the action; do not claim it was run.
7. Make the minimum experiment preserve the central mechanism. A toy setup that supplies an unavailable deployment signal cannot establish deployment feasibility.

## Output
Populate feasibility and the operational method fields in the active JSON schema. Put the weakest prerequisite and its check in validation. Keep concept value separate from execution status.

## Failure behavior
An unavailable signal calls for a concrete redesign: remove the dependency, choose an observable substitute, or use an oracle only as a clearly identified diagnostic control. Update the actual method and signal list together. Unknown access or unmeasured cost calls for a small configurable pilot. Keep the research idea and improve its implementation path; do not turn normal pre-experiment uncertainty into an approval gate. A proposed substitute is still a hypothesis to test, and an oracle is not a deployment method.

## Synthetic example
A controller chooses the better answer by comparing against the hidden test label. Labels exist for evaluation but not inference. Mark that inference dependency unavailable. An oracle comparison may still diagnose headroom; a deployable estimator requires its own learning signal and validation.
