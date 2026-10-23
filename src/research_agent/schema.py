"""Small, explicit JSON Schema subset shared by prompts and local validators."""
from __future__ import annotations


def string(enum=None):
    schema = {"type": "string"}
    if enum is not None:
        schema["enum"] = list(enum)
    return schema


def array(items):
    return {"type": "array", "items": items}


def obj(**properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


STR = string()
STRINGS = array(STR)
EVIDENCE = obj(observations=array(obj(statement=STR, quote=STR, kind=string(["reported_result", "author_claim", "limitation"]), conditions=STR, source_section=STR)))
MAP = obj(problem=STR, observations=STRINGS, competing_explanations=STRINGS, unresolved_questions=STRINGS, opportunity_types=STRINGS, evidence_ids=STRINGS)
MOTIVATION = obj(problem_observation=STR, evidence_ids=STRINGS, importance=STR, existing_approach_limit=STR,
    causal_explanation=STR, why_this_method=STR, expected_progress=STR, simplest_alternative=STR, necessity_test=STR)
PROPOSE = obj(candidates=array(obj(title=STR, problem=STR, hypothesis=STR, mechanism=STR, intervention=STR,
    prediction=STR, falsifier=STR, evidence_ids=STRINGS, closest_work_ids=STRINGS, why_it_matters=STR, motivation=MOTIVATION)), no_candidate_reason=STR)
METHOD = obj(
    base_implementation=STR, changes=STRINGS, inputs=STR, outputs=STR,
    trainable_parameters=STR, frozen_parameters=STR, objective=STR,
    supervision=STR, inference_steps=STRINGS, resource_requirements=STR,
    assumptions=array(obj(statement=STR, status=string(["unverified", "source_supported"]), evidence_ids=STRINGS, check=STR)),
)
COMPARISON = obj(dimension=string(["problem", "mechanism", "information", "objective", "evaluation", "claim"]),
    prior_detail=STR, proposed_detail=STR, relation=string(["same", "different", "unknown"]), evidence_ids=STRINGS)
PRIOR = obj(verdict=string(["uncertain", "difference_supported", "covered"]), justification=STR,
    overlaps=array(obj(paper_id=STR, level=string(["topic", "problem", "mechanism", "core_claim"]), covered_claim=STR,
        evidence_ids=STRINGS, remaining_gap=STR, comparisons=array(COMPARISON))), search_queries=STRINGS)
NOVELTY = obj(type=string(["mechanism", "explanation", "boundary", "efficiency", "evaluation"]),
    claim=STR, changed_variable=STR, observable_consequence=STR, falsifier=STR, nontriviality=STR)
FEASIBILITY = obj(
    checks=array(obj(dimension=string(["data_access", "inference_signal", "interface", "learning_signal", "compute", "evaluation", "minimal_test"]),
        status=string(["source_supported", "unverified", "blocked", "not_applicable"]), requirement=STR,
        evidence_ids=STRINGS, verification_plan=STR, failure_action=STR)),
    required_signals=array(obj(name=STR, needed_at=string(["training", "inference", "evaluation"]),
        availability=string(["source_supported", "unverified", "unavailable"]), evidence_ids=STRINGS,
        acquisition_plan=STR, substitute=STR)),
)
VALIDATION = obj(weakest_assumption=STR, first_test=STR, baselines=STRINGS, controls=STRINGS,
    positive=STR, negative=STR, inconclusive=STR, budget_estimate=STR)
ACTION = obj(kind=string(["search", "read_source", "inspect_code", "run_experiment", "revise", "stop"]), description=STR, decision_impact=STR)
DEVELOP = obj(method=METHOD, motivation=MOTIVATION, prior_art=PRIOR, novelty_claim=NOVELTY, feasibility=FEASIBILITY, validation=VALIDATION, next_action=ACTION)
REVIEW = obj(verdict=string(["continue", "refine", "covered", "blocked"]),
    issues=array(obj(severity=string(["critical", "important", "minor"]), issue=STR, evidence_ids=STRINGS, action=STR)),
    unresolved_questions=STRINGS, revision_instructions=STR, next_action=ACTION,
    motivation_assessment=obj(problem_significance=string(["substantial", "limited", "unclear"]),
        causal_link=string(["plausible", "unsupported", "unclear"]), progress=string(["substantive", "incremental", "unclear"]), reason=STR, decisive_test=STR))
SCHEMAS = {"extract": EVIDENCE, "inspect_source": EVIDENCE, "map": MAP, "propose": PROPOSE, "develop": DEVELOP, "refine": DEVELOP, "review": REVIEW}


def validate(value, schema, path="$", depth=0):
    if depth > 40:
        raise ValueError("Response nesting exceeds limit")
    kind = schema["type"]
    if kind == "object":
        if not isinstance(value, dict):
            raise ValueError(f"{path}: expected object")
        properties = schema["properties"]
        missing = set(schema["required"]) - set(value)
        extra = set(value) - set(properties)
        if missing or extra:
            raise ValueError(f"{path}: missing={sorted(missing)}, unexpected={sorted(extra)}")
        for key, child in properties.items():
            validate(value[key], child, path + "." + key, depth + 1)
    elif kind == "array":
        if not isinstance(value, list) or len(value) > 200:
            raise ValueError(f"{path}: expected array of at most 200 entries")
        for i, item in enumerate(value):
            validate(item, schema["items"], f"{path}[{i}]", depth + 1)
    elif kind == "string":
        if not isinstance(value, str) or len(value) > 50000:
            raise ValueError(f"{path}: expected string of at most 50000 characters")
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError(f"{path}: invalid enum value")
    else:
        raise ValueError(f"Unsupported schema type: {kind}")
