"""Check a problem–motivation–method argument without claiming scientific value.

No keyword heuristic decides whether a contribution matters. This gate checks
the structured argument and citation identities, then records the reviewer's
explicit assessments as revisable opinions rather than verified conclusions.
"""
from __future__ import annotations


MOTIVATION_FIELDS = (
    "problem_observation", "importance", "existing_approach_limit",
    "causal_explanation", "why_this_method", "expected_progress",
    "simplest_alternative", "necessity_test",
)
ASSESSMENTS = {
    "problem_significance": {"substantial", "limited", "unclear"},
    "causal_link": {"plausible", "unsupported", "unclear"},
    "progress": {"substantive", "incremental", "unclear"},
}
_REVISE = {"limited", "unsupported", "incremental"}


def _nonempty(record: dict, field: str, label: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}.{field} must be a nonempty string")
    return value


def assess_motivation(proposal: dict, review: dict, evidence: list[dict]) -> dict:
    """Assess an explicit motivation chain and a reviewer's structured opinion.

    Missing arguments, missing citations and malformed classifications raise
    ValueError for bounded output repair. Plausibility and significance remain
    judgments: even an entirely positive review yields argued_not_validated.
    """
    motivation = proposal.get("motivation") if isinstance(proposal, dict) else None
    if not isinstance(motivation, dict):
        raise ValueError("Proposal requires a motivation object")
    for field in MOTIVATION_FIELDS:
        _nonempty(motivation, field, "motivation")
    if not isinstance(evidence, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in evidence
    ):
        raise ValueError("Evidence must contain records with string IDs")
    known = {item["id"] for item in evidence}
    refs = motivation.get("evidence_ids")
    if not isinstance(refs, list) or (not refs and motivation.get('basis', 'source_observation') != 'research_hypothesis'):
        raise ValueError("Motivation requires supporting evidence IDs")
    if any(not isinstance(ref, str) or ref not in known for ref in refs):
        raise ValueError("Motivation contains an unknown evidence ID")

    assessment = review.get("motivation_assessment") if isinstance(review, dict) else None
    if not isinstance(assessment, dict):
        raise ValueError("Review requires a motivation_assessment object")
    reason = _nonempty(assessment, "reason", "motivation_assessment")
    decisive_test = _nonempty(assessment, "decisive_test", "motivation_assessment")
    unresolved = []
    needs_revision = False
    uncertain = False
    for dimension, allowed in ASSESSMENTS.items():
        value = assessment.get(dimension)
        if not isinstance(value, str) or value not in allowed:
            raise ValueError(f"motivation_assessment.{dimension} has an invalid classification")
        if value in _REVISE or value == "unclear":
            unresolved.append({"dimension": dimension, "assessment": value,
                               "reason": reason, "decisive_test": decisive_test})
        needs_revision = needs_revision or value in _REVISE
        uncertain = uncertain or value == "unclear"

    if needs_revision:
        status = "needs_revision"
    elif uncertain:
        status = "motivation_unresolved"
    else:
        status = "argued_not_validated"
    warnings = [
        "Motivation assessment records model review opinions, not verified problem significance, causality, novelty, or research value.",
        "Citation identities were checked; this does not establish that the sources support the full motivation or that the proposed method is necessary.",
    ]
    if needs_revision:
        warnings.append("The reviewer identifies a weak motivation link; revise or test the specific concern rather than automatically abandoning the research direction.")
    elif uncertain:
        warnings.append("The motivation remains unresolved; the decisive test is proposed and has not been executed by this assessment.")
    else:
        warnings.append("A positive motivation review is an argued case only; necessity and substantive progress still require discriminating evidence.")
    return {"status": status, "warnings": warnings, "unresolved": unresolved}
