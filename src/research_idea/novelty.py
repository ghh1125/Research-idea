"""Bound novelty judgments to explicit, source-grounded comparisons.

These checks establish the completeness and provenance of an argument, not its
scientific truth. Empirical coverage additionally requires reported-result
evidence for the evaluation comparison. A model's similarities or differences
still need expert review; insufficient performance evidence does not establish
that a described mechanism is new.
"""
from __future__ import annotations


DIMENSIONS = ("problem", "mechanism", "information", "objective", "evaluation", "claim")
KEY_DIMENSIONS = ("mechanism", "information", "objective", "claim")
CLAIM_TYPES = ("mechanism", "explanation", "boundary", "efficiency", "evaluation")
CLAIM_FIELDS = ("claim", "changed_variable", "observable_consequence", "falsifier", "nontriviality")
_PLACEHOLDERS = {"", "unknown", "tbd", "todo", "n/a", "na", "none", "same", "different",
                 "similar", "yes", "no", "not applicable", "未知", "待定", "相同", "不同", "同上", "无"}


def _concrete(value):
    return isinstance(value, str) and " ".join(value.split()).casefold() not in _PLACEHOLDERS


def validate_comparisons(overlaps: list) -> None:
    """Require one typed comparison for each of the six dimensions per paper.

Unknown comparisons are legitimate: their details and evidence may be empty.
Semantic adequacy and supporting evidence are checked by ``assess_novelty``.
"""
    if not isinstance(overlaps, list):
        raise ValueError("Prior-art overlaps must be an array")
    for i, overlap in enumerate(overlaps):
        if not isinstance(overlap, dict):
            raise ValueError(f"Overlap {i} must be an object")
        comparisons = overlap.get("comparisons")
        if not isinstance(comparisons, list):
            raise ValueError(f"Overlap {i} requires six-dimensional comparisons")
        seen = set()
        for comparison in comparisons:
            if not isinstance(comparison, dict):
                raise ValueError(f"Overlap {i}: comparison must be an object")
            dimension = comparison.get("dimension")
            if not isinstance(dimension, str) or dimension not in DIMENSIONS or dimension in seen:
                raise ValueError(f"Overlap {i}: invalid or duplicate comparison dimension")
            seen.add(dimension)
            if comparison.get("relation") not in ("same", "different", "unknown"):
                raise ValueError(f"Overlap {i}/{dimension}: invalid comparison relation")
            for field in ("prior_detail", "proposed_detail"):
                if not isinstance(comparison.get(field), str):
                    raise ValueError(f"Overlap {i}/{dimension}: {field} must be a string")
            refs = comparison.get("evidence_ids")
            if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref for ref in refs):
                raise ValueError(f"Overlap {i}/{dimension}: evidence_ids must be an array of IDs")
        missing = set(DIMENSIONS) - seen
        if missing:
            raise ValueError(f"Overlap {i}: missing comparison dimensions: {', '.join(sorted(missing))}")


def assess_novelty(spec: dict, evidence: list) -> dict:
    """Return a cautious assessment within the supplied corpus only.

Incomplete comparisons yield gaps and uncertainty, never rejection. Dangling or
cross-paper citations raise ValueError so the caller can request a repair.
"""
    indexed = {}
    for item in evidence:
        ref = item["id"]
        if ref in indexed:
            raise ValueError("Duplicate evidence ID in novelty assessment")
        indexed[ref] = item

    prior = spec.get("prior_art", {})
    overlaps = prior.get("overlaps", [])
    warnings, gaps = [], []
    coverage_supported = False
    core_overlap_argued = False
    difference_supported = False

    def check_refs(refs, paper_id):
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            raise ValueError("Comparison evidence_ids must be an array of IDs")
        for ref in refs:
            if ref not in indexed:
                raise ValueError("Unknown evidence ID in novelty comparison")
            if indexed[ref].get("paper_id") != paper_id:
                raise ValueError("Novelty comparison cites evidence from a different paper")
        return any(indexed[ref].get("source_kind") == "full_text" for ref in refs)

    if not isinstance(overlaps, list):
        overlaps = []
        gaps.append("prior_art.overlaps: a comparison array is required.")
    if not overlaps:
        gaps.append("No prior-work comparisons are supplied; absence of matches does not establish novelty.")

    for i, overlap in enumerate(overlaps):
        if not isinstance(overlap, dict):
            gaps.append(f"overlap[{i}]: missing comparison object.")
            continue
        paper_id = overlap.get("paper_id")
        label = paper_id if isinstance(paper_id, str) and paper_id else f"overlap[{i}]"
        check_refs(overlap.get("evidence_ids", []), paper_id)
        comparisons = overlap.get("comparisons", [])
        if not isinstance(comparisons, list):
            comparisons = []
        # Check provenance even when other structure is incomplete.
        for comparison in comparisons:
            if isinstance(comparison, dict):
                check_refs(comparison.get("evidence_ids", []), paper_id)
        try:
            validate_comparisons([overlap])
        except ValueError as exc:
            gaps.append(f"{label}: {exc}.")
            # A malformed comparison cannot justify either coverage or a difference.
            continue

        all_same_and_grounded = True
        any_key_difference = False
        evaluation_has_reported_result = False
        known_mechanism_argued = False
        for comparison in comparisons:
            dimension = comparison["dimension"]
            relation = comparison["relation"]
            prefix = f"{label}/{dimension}"
            grounded = check_refs(comparison["evidence_ids"], paper_id)
            detailed = all(_concrete(comparison[field]) for field in ("prior_detail", "proposed_detail"))
            if relation == "unknown":
                gaps.append(f"{prefix}: comparison is unknown; read or inspect the relevant source.")
            if not detailed:
                gaps.append(f"{prefix}: concrete prior and proposed details are required.")
            if not grounded:
                gaps.append(f"{prefix}: no full-text evidence from this paper supports the comparison.")
            same_text = " ".join(comparison["prior_detail"].split()).casefold() == " ".join(comparison["proposed_detail"].split()).casefold()
            if relation == "different" and same_text:
                gaps.append(f"{prefix}: a difference is asserted but both descriptions are identical.")
            all_same_and_grounded &= relation == "same" and detailed and grounded
            if dimension == "evaluation":
                evaluation_has_reported_result = any(
                    indexed[ref].get("source_kind") == "full_text"
                    and indexed[ref].get("kind") == "reported_result"
                    for ref in comparison["evidence_ids"]
                )
            if dimension == "mechanism" and relation == "same" and detailed and grounded:
                known_mechanism_argued = True
            if dimension in KEY_DIMENSIONS and relation == "different" and detailed and grounded and not same_text:
                any_key_difference = True
        if overlap.get("level") == "core_claim" and _concrete(overlap.get("covered_claim")) and all_same_and_grounded:
            core_overlap_argued = True
            coverage_supported |= evaluation_has_reported_result
        if overlap.get("level") == "core_claim" and not evaluation_has_reported_result:
            gaps.append(f"{label}/evaluation: the comparison lacks a reported_result from this paper's full text; author claims alone cannot establish empirical core-claim coverage.")
            warnings.append(f"{label}: empirical coverage remains unconfirmed without reported experimental support for the evaluation comparison; retain the candidate as uncertain where coverage is the proposed verdict.")
        if known_mechanism_argued and not evaluation_has_reported_result:
            warnings.append(f"{label}: the supplied comparison identifies a potentially pre-existing mechanism; unestablished performance does not make that mechanism novel.")
        if overlap.get("level") == "core_claim" and not _concrete(overlap.get("covered_claim")):
            gaps.append(f"{label}: the allegedly covered core claim is not specified.")
        if overlap.get("level") in ("topic", "title"):
            warnings.append(f"{label}: title/topic similarity alone cannot reject the branch.")
        difference_supported |= any_key_difference

    claim = spec.get("novelty_claim", {})
    if not isinstance(claim, dict):
        claim = {}
    claim_complete = claim.get("type") in CLAIM_TYPES
    if not claim_complete:
        gaps.append("novelty_claim.type: specify mechanism, explanation, boundary, efficiency or evaluation.")
    for field in CLAIM_FIELDS:
        if not _concrete(claim.get(field)):
            claim_complete = False
            gaps.append(f"novelty_claim.{field}: a concrete statement is required.")

    verdict = prior.get("verdict", "uncertain")
    status = "uncertain"
    if verdict == "covered":
        if coverage_supported:
            status = "covered"
        else:
            warnings.append("Core-claim coverage lacks a complete six-dimensional full-text argument with reported evaluation results; branch was not rejected.")
    elif verdict == "difference_supported":
        if core_overlap_argued:
            warnings.append("A full-text core-claim overlap conflicts with the proposed difference; resolve it before claiming differentiation, even if prior performance is unestablished.")
        elif difference_supported and claim_complete:
            status = "difference_argued_in_supplied_corpus"
        else:
            warnings.append("The proposed difference lacks a grounded substantive comparison or a concrete novelty claim; retain candidate as uncertain.")
    if not any(e.get("source_kind") == "full_text" for e in evidence):
        warnings.append("Only abstracts/notes are available. Mechanism and novelty analysis require full-text follow-up.")
    warnings.append("This checks comparison structure and evidence provenance, not scientific entailment or global novelty.")
    return {"status": status, "warnings": list(dict.fromkeys(warnings)),
            "comparison_gaps": list(dict.fromkeys(gaps))}
