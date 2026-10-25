---
name: research-idea-check-feasibility
description: Design an executable path for an LLM/NLP idea. Use when proposing, developing or reviewing a method that may rely on unavailable labels, logits, gradients, model access, data, compute or evaluation assumptions.
---

# Design a workable implementation path

## Inputs
Use the idea, technical references, resource constraints and supplied evidence. Treat an unmeasured resource estimate as unknown. A plausible algorithm is not an executed implementation.

## Procedure
During first-round propose, reason through essential information dependencies before presenting the idea, without a worked example. Fill feasibility_sketch with inputs actually available to the agent, an available_path through the key operation, the key_assumption and first_check. first_check briefly names the evidence or interface relevant to the assumption; it is not an experiment plan. If a hidden answer, unexposed API signal or circular supervision is needed, redesign now using obtainable inputs. Separate what the agent observes from what the evaluator knows. Explain why the existing simplest solution does not already answer the question. Keep unknown resource requirements as concise conditions and preserve the scientific question.

Record central dependencies in idea_core.information_path: information, source, construction, reliability_basis, error_handling, applicability and evidence_ids. Use at most three entries, only for inputs requiring actual inference or construction. Traceability establishes provenance, not semantic correctness; agreement between generations is not independent authority. Explain scope, exceptions and matching errors when they affect the operation. Noisy inputs are acceptable: explain the method's useful path under that noise rather than assuming perfect labels. Applicability explains where enough usable material can be obtained, without inventing coverage numbers. This structure preserves the reasoning for later design and display; it is not an additional rejection checklist.

Make the central input concrete. Name the objects involved, the information or relationship needed, the conditions under which it is valid, and its available source. Distinguish obtaining a proposed relation from checking it: identify the transformation or procedure that obtains it and what source, observable outcome or rule gives the check its authority. A model's confidence in a relation does not supply that authority. If verification is partial, explain what it establishes and where the core assumption begins.

Trace the key operation through to its intended effect: what input it consumes, what it changes, what the learner or decision maker must consequently do, and why that could improve the target capability. Check whether the prior shortcut would still satisfy the changed objective. Keep this a reasoning explanation, not a detailed implementation or experiment protocol.

Do not hide the main research difficulty inside "first construct reliable relationships," "identify useful information," or "let the researcher verify it." If such a prerequisite performs the essential inference, explain its feasible inputs and operation here. When access has not been specified, state the needed condition without pretending it is granted; when the dependency is circular or impossible, change the route within the current proposal. Phase two can choose tools, but it should not have to supply a missing source of truth for phase one.

For an idea involving actions or decisions, inspect the observation/action contract. Can a minimal reactive policy finish using the visible state? Are the intended outcomes reachable through the allowed actions? What useful decision actually requires the proposed inference? Resolve a needless inference step or an unreachable task within the idea; never create difficulty by hiding normally visible information. These are internal reasoning checks, not another user-facing gate or a requirement to execute experiments in phase one.

During develop, refine or review:
1. Check the dependency path across training, inference, and evaluation internally. List every required signal and when it is used: labels, scores, logits, gradients, hidden states, retrieval, tools and annotations. Identify who produces each signal, from which available input and by what operation; naming a producer alone does not explain acquisition.
2. Identify the concrete interfaces and data transformations between steps. For learned components, follow the supervision and gradient path. For API-only access, do not assume weights, token probabilities or gradients are exposed.
3. Fill exactly seven feasibility.checks: data_access, inference_signal, interface, learning_signal, compute, evaluation, minimal_test. For each give requirement, status, evidence_ids, verification_plan and failure_action in short clauses. verification_plan names the relevant evidence or interface to inspect; do not turn it into an experiment plan.
4. Use source_supported only with relevant source evidence, and preserve differences between the paper's environment and this project. It never means locally tested. Use unverified for uninspected access, interfaces or resource estimates. For not_applicable, explain why the method does not need that prerequisite.
5. For each required_signal give needed_at, availability, acquisition_plan and substitute. State explicitly when no acquisition path or valid substitute is known. A substitute is a new hypothesis until tested.
6. Identify which source evidence, data property or interface contract could resolve the weakest dependency. Explain the relevant condition briefly without designing an execution protocol.
7. Preserve the real scientific difficulty. Simplifying the technical route must not depend on signals that the intended setting cannot provide.

## Output
For propose, populate feasibility_sketch and idea_core.construction_path, using the objects and conditions in concrete_target. State the usable path in direct language, with the important assumption attached to the step it affects. In develop/refine, update this path when the technical route changes and keep capability_bridge consistent. For technical design, populate feasibility and the concise operational method fields; validation.weakest_assumption may name the weakest prerequisite. Leave the remaining compatibility-only validation fields empty. Fix known implementation contradictions in the proposal itself, rather than merely recording a warning for later. Do not add a separate checklist, score, approval step, worked example or experiment plan to the user's idea.

## Failure behavior
An unavailable signal calls for a concrete redesign: remove the dependency or choose an observable substitute. Update the actual method and signal list together. Keep unknown access or unmeasured cost as a specific condition. Keep the research idea and improve its implementation path; do not turn normal pre-experiment uncertainty into an approval gate. A proposed substitute is still a hypothesis, and an oracle is not a deployment method.
