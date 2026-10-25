---
name: research-idea-check-feasibility
description: Design a workable information and implementation path for an LLM/NLP idea. Use when proposing, developing or reviewing methods with inferred inputs, supervision, model-access or resource dependencies.
---

# Design a workable information path

Use the idea, technical references, resource constraints and supplied evidence to explain how the method obtains and uses its essential information. Preserve the capability and scientific question that made the idea worth pursuing. A plausible route is a design proposal; resource estimates remain estimates.

## Core acquisition reasoning

Follow the central dependency from an observation available in the intended setting to the information the method needs, then to the operation that uses it. Separate observations available during training, inference and evaluation. When obtaining the information performs the difficult inference, make that acquisition part of the research method and explain its contribution. Leaving it as a prerequisite simply moves the unresolved problem upstream.

Record up to three central constructed or inferred inputs in `idea_core.information_path`, using the existing fields:

- `information` names the object or signal needed, its meaning and downstream use. `source` names the raw observable input, who can access it and when. Separate information already present in the source from information supplied by a teacher, annotator or external service.
- `construction` explains the substantive operations that turn those observations into the needed output. State what the procedure inspects, how it infers or transforms the input, and what it returns. A parser, retriever, model judge or verification tool is a component name, not an acquisition explanation. For a learned step, explain where its supervision or other learning signal comes from; for a constrained procedure, explain which observable properties make the constraint applicable and what remains to be inferred.
- `reliability_basis` identifies the evidence used to check the result, the property that evidence can establish, and the consequential error it leaves unresolved. Explain what information the check adds beyond the candidate-generation process. Source alignment establishes provenance; syntax and type checks establish admissible form; execution establishes the observed behavior. Their relevance to the intended meaning must be argued. Another model's agreement can help estimate uncertainty but may repeat the same error. If people provide the check, name the material and criterion available to them rather than assuming they know the answer.
- `error_handling` explains how the downstream method uses incomplete, ambiguous or noisy information and why that use still serves the target capability. Choose a treatment that fits the mechanism, such as retaining alternatives, learning from partial constraints or seeking additional observations. Explain which error it addresses and what useful signal remains; simply discarding all difficult inputs or calling the remainder reliable does not explain the method.
- `applicability` explains where this acquisition route can operate, how the available material relates to the intended research setting, and which part of that setting remains a design challenge. Keep an accessible starting implementation distinct from the scope of the research question. Attach `evidence_ids` to supplied source facts, not to proposed operations or predicted reliability.

Describe the connection between these steps, rather than filling each field with a separate reassurance. A check downstream cannot establish an upstream assumption that it never observes. Partial checking is useful when the method explains which decisions it can support and how remaining uncertainty affects the learning or decision process. Perfect information is not a prerequisite for a meaningful idea.

Trace the resulting signal through to the intended effect: what changes in the learner's objective or the decision maker's action, what it must now distinguish, and why the former shortcut would no longer suffice. For action-based ideas, use the actually visible state and allowed actions to determine whether the intended decision requires the proposed inference and whether the outcome is reachable. This reasoning should clarify the mechanism, without constructing an artificial difficulty.

## Choosing a feasible route

When a dependency is unavailable or poorly grounded, compare plausible alternatives at the level of acquisition and use. A different observation, representation, learning objective or use of uncertain evidence may preserve the important capability. Explain why the chosen route fits the available information and what substantive assumption it retains. Prefer a simpler route when it answers the same question.

A narrow implementation can be a useful starting point. Say what difficulty it isolates and what work connects it to the intended setting; do not silently replace the selected capability with the subset easiest to certify. If acquiring the central signal remains the main challenge, develop that operation within the research method and explain how it supports the selected contribution. If no credible route is yet known, name the missing operation and the technical question it creates, without claiming that an easier, different problem resolves it.

## Stage-specific output

For propose, fill `feasibility_sketch` with the observable `inputs`, an `available_path` through acquisition and use, the material `key_assumption`, and `first_check`. The latter names the evidence or interface that would resolve that assumption, without an experiment plan. Write `idea_core.construction_path` as a connected explanation using the objects in `concrete_target`; preserve the important acquisition reasoning in `information_path`. Phase two can choose technical tools, while phase one should already explain where their decisive information would come from.

For develop, refine or review, follow the dependency path across training, inference and evaluation. For learned components, connect supervision, objective and parameter updates; for API access, use the exposed interface rather than assuming weights, token probabilities or gradients. Populate the existing schema:

- Each `required_signal` states `needed_at`, `availability`, `acquisition_plan` and `substitute`, consistent with the actual method. An evaluator's answer is not an inference-time signal. State when an alternative changes the scientific hypothesis.
- `feasibility.checks` contains the seven required dimensions: `data_access`, `inference_signal`, `interface`, `learning_signal`, `compute`, `evaluation`, `minimal_test`. Keep `requirement`, `status`, `evidence_ids`, `verification_plan` and `failure_action` brief. These capture implementation conditions, not additional scientific gates.
- Use `source_supported` for relevant cited evidence with its original conditions; it does not mean locally tested. Use `unverified` for uninspected access, interfaces or costs, and explain `not_applicable`. `verification_plan` identifies the evidence or interface needed to resolve the condition.

Update `construction_path`, `information_path`, the operational method and `capability_bridge` together when the route changes. `validation.weakest_assumption` may name the central unresolved premise; leave the other compatibility-only validation fields empty. Resolve known contradictions in the proposed route, keeping normal idea-stage uncertainty in the relevant design explanation. Return only the active task JSON, without extra scores, approval steps, worked examples or experiment protocols.
