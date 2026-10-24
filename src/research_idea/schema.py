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
PLAN_SEARCH = obj(research_question=STR, scope=STR,
    queries=array(obj(query=STR, purpose=string(["background", "motivation", "mechanism", "implementation", "evaluation", "counterevidence"]), rationale=STR)),
    assumptions=STRINGS)
SCREEN_PAPERS = obj(selection_summary=STR,
    selected=array(obj(paper_id=STR, reason=STR, reading_question=STR)))
EVIDENCE = obj(observations=array(obj(statement=STR, quote=STR, kind=string(["reported_result", "author_claim", "limitation"]), conditions=STR, source_section=STR)))
CLAIM_AUDIT = obj(
    paper_id=STR,
    reading_coverage=obj(experiments=string(["read", "partial", "unavailable"]),
        appendix=string(["read", "partial", "unavailable", "not_present"]), notes=STR),
    claims=array(obj(claim=STR, claim_evidence_ids=STRINGS,
        tested_scope=obj(tasks=STR, data=STR, models=STR, settings=STR, budget=STR),
        result_evidence_ids=STRINGS, warranted_conclusion=STR,
        limitations=STRINGS, confounds=STRINGS, missing_controls=STRINGS,
        support_judgment=string(["supported_within_tested_scope", "overstated", "not_established",
            "contradicted", "insufficient_evidence"]), next_reading=STRINGS)),
)
MAP = obj(problem=STR, observations=STRINGS, competing_explanations=STRINGS, unresolved_questions=STRINGS, opportunity_types=STRINGS, evidence_ids=STRINGS)
MOTIVATION = obj(basis=string(["source_observation", "research_hypothesis"]), background=STR, problem_observation=STR, evidence_ids=STRINGS, importance=STR, existing_approach_limit=STR,
    causal_explanation=STR, why_this_method=STR, expected_progress=STR, simplest_alternative=STR, necessity_test=STR)
POSITIONING = obj(paper_id=STR, addressed_problem=STR, remaining_question=STR, contribution=STR, evidence_ids=STRINGS)
FEASIBILITY_SKETCH = obj(inputs=STR, available_path=STR, key_assumption=STR, first_check=STR)
PROPOSE = obj(candidates=array(obj(title=STR, problem=STR, hypothesis=STR, mechanism=STR, intervention=STR,
    prediction=STR, falsifier=STR, evidence_ids=STRINGS, closest_work_ids=STRINGS, why_it_matters=STR,
    motivation=MOTIVATION, positioning=array(POSITIONING), feasibility_sketch=FEASIBILITY_SKETCH)), no_candidate_reason=STR)
DESIGN_OPTION = obj(question=STR, source_technique=STR, shared_structure=STR, source_conditions=STR,
    adaptation=STR, why_it_helps=STR, simpler_alternative=STR, first_test=STR, evidence_ids=STRINGS)
DESIGN_TRANSFER = obj(paper_id=STR, options=array(DESIGN_OPTION), reading_gaps=STRINGS)
DESIGN_DECISION = obj(question=STR, choice=STR, rationale=STR, adaptation=STR,
    alternative=STR, first_test=STR, evidence_ids=STRINGS)
METHOD = obj(
    summary=STR, base_implementation=STR, changes=STRINGS, inputs=STR, outputs=STR,
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
VALIDATION = obj(summary=STR, weakest_assumption=STR, first_test=STR, baselines=STRINGS, controls=STRINGS,
    positive=STR, negative=STR, inconclusive=STR, budget_estimate=STR)
ACTION = obj(kind=string(["search", "read_source", "inspect_code", "run_experiment", "revise", "stop"]), description=STR, decision_impact=STR)
RESPONSE = obj(issue=STR, decision=string(["adopt", "adapt", "decline", "test"]), change=STR, reason=STR, evidence_ids=STRINGS)
DEVELOP = obj(method=METHOD, motivation=MOTIVATION, prior_art=PRIOR, novelty_claim=NOVELTY, feasibility=FEASIBILITY, validation=VALIDATION, next_action=ACTION,
              design_decisions=array(DESIGN_DECISION), review_responses=array(RESPONSE))
REVIEW = obj(verdict=string(["continue", "refine", "covered", "blocked"]),
    issues=array(obj(severity=string(["critical", "important", "minor"]), issue=STR, evidence_ids=STRINGS, action=STR)),
    unresolved_questions=STRINGS, revision_instructions=STR, next_action=ACTION,
    motivation_assessment=obj(problem_significance=string(["substantial", "limited", "unclear"]),
        causal_link=string(["plausible", "unsupported", "unclear"]), progress=string(["substantive", "incremental", "unclear"]), reason=STR, decisive_test=STR))
PAPER_CARD = obj(paper_id=STR, paper_type=string(["method", "empirical", "theory", "resource", "review", "mixed"]),
    framework=array(obj(dimension=string(["problem", "motivation", "insight", "method", "prior_work_delta", "experiment_design", "results", "conclusion_boundary", "idea_relevance"]),
        status=string(["source_supported", "analysis", "not_assessable", "not_applicable"]), summary=STR, evidence_ids=STRINGS)),
    components=array(obj(name=STR, function=STR, inputs=STR, outputs=STR, necessity=STR,
        assumptions=STRINGS, contribution_test=STR, evidence_ids=STRINGS)),
    experiments=array(obj(name=STR, tested_claim=STR, setup=STR, comparator=STR, controls=STR,
        reported_result=STR, supported_conclusion=STR, unsupported_inference=STR, evidence_ids=STRINGS, asset_ids=STRINGS)),
    author_limitations=array(obj(statement=STR, evidence_ids=STRINGS)),
    analyst_concerns=array(obj(concern=STR, evidence_ids=STRINGS, alternative_explanation=STR, discriminating_test=STR)),
    opportunities=array(obj(hypothesis=STR, evidence_ids=STRINGS, why_meaningful=STR, first_test=STR, falsifier=STR)),
    reading_gaps=STRINGS,
    followup_requests=array(obj(target_id=STR, question=STR, decision_impact=STR)))
SCHEMAS = {"plan_search": PLAN_SEARCH, "screen_papers": SCREEN_PAPERS, "extract": EVIDENCE, "read_section": EVIDENCE, "paper_card": PAPER_CARD, "design_transfer": DESIGN_TRANSFER,
    "inspect_source": EVIDENCE, "audit_claims": CLAIM_AUDIT, "map": MAP, "propose": PROPOSE, "develop": DEVELOP, "refine": DEVELOP, "review": REVIEW}


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
