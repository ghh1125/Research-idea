"""Paper-claim audits bounded by the actual source and reported experiments.

These gates validate structure and quotation provenance, not entailment. The
model must read experiment details, controls and appendices to judge whether a
result warrants its conclusion. Neither an audit nor implementation feasibility
establishes that a proposed method will work.
"""
from __future__ import annotations

from copy import deepcopy
import re

from .schema import CLAIM_AUDIT, validate
from .store import digest


_UNKNOWN = {"", "unknown", "unspecified", "not reported", "not supplied", "n/a", "na",
            "none", "tbd", "todo", "未知", "未报告", "未提供", "待定", "无"}
_RESULT_SECTION = re.compile(
    r"experiment|result|evaluat|ablation|appendix|supplement|table|figure|实验|结果|评估|消融|附录|补充|表\s*\d|图\s*\d",
    re.I,
)


def _concrete(value: str) -> bool:
    return " ".join(value.split()).casefold().rstrip(".。") not in _UNKNOWN


def current_claim_audits(papers: list[dict], evidence: list[dict], saved: dict) -> dict:
    """Expose only audits grounded in the current source and retained citations."""
    current = {}
    refs = {item["id"] for item in evidence}
    for paper in papers:
        paper_id = paper["id"]
        source_hash = digest(paper.get("text") or paper.get("abstract", ""))
        audit = saved.get(paper_id)
        cited = {ref for claim in (audit or {}).get("claims", [])
                 for field in ("claim_evidence_ids", "result_evidence_ids") for ref in claim.get(field, [])}
        full_text = paper.get("content_kind") == "full_text"
        if audit and audit.get("source_hash") == source_hash and cited <= refs and (full_text or not audit.get("claims")):
            current[paper_id] = audit
            continue
        current[paper_id] = {"paper_id": paper_id, "source_hash": source_hash,
            "status": "pending" if full_text else "insufficient_evidence", "claims": [],
            "reading_coverage": {"experiments": "unavailable", "appendix": "unavailable",
                                 "notes": "No completed audit matching the current source and evidence is available."},
            "warnings": ["Current full-text claim audit is pending or its evidence changed." if full_text
                         else "Abstracts/notes cannot establish experimental support; full-text reading is required."]}
    return current


def assess_claims(audit: dict, paper: dict, evidence: list[dict]) -> dict:
    """Validate one paper's model audit and return conservative normalized records.

    Dangling, cross-paper and stale quotation references raise ``ValueError`` for
    bounded output repair. Abstract-only evidence, author claims, and unavailable
    result details cannot establish experimental support. A supported result is
    limited to ``tested_scope``; its scientific entailment remains model assessed.
    The input is not mutated. Audits do not decide mechanism novelty.
    """
    validate(audit, CLAIM_AUDIT)
    if len(audit["claims"]) > 4:
        raise ValueError("Audit at most four substantive claims per paper")
    if not isinstance(paper, dict) or not isinstance(paper.get("id"), str) or not paper["id"]:
        raise ValueError("Claim audit requires a paper with a nonempty ID")
    if audit["paper_id"] != paper["id"]:
        raise ValueError("Claim audit refers to a different paper")
    if not isinstance(evidence, list):
        raise ValueError("Claim audit evidence must be an array")
    indexed = {}
    for item in evidence:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise ValueError("Claim audit evidence requires nonempty string IDs")
        if item["id"] in indexed:
            raise ValueError("Duplicate evidence ID in claim audit")
        indexed[item["id"]] = item

    text = paper.get("text") or paper.get("abstract", "")
    if not isinstance(text, str):
        raise ValueError("Claim audit paper text must be a string")
    source_hash = digest(text)
    is_full_text = paper.get("content_kind") == "full_text" and bool(text.strip())
    warnings = [
        "Claim audit checks structure and quotation provenance, not scientific entailment; support judgments remain source-based model assessments.",
        "Reported support applies only to the stated tested scope; it is not global proof or evidence that this project's proposed method will work.",
        "An unproven performance claim does not make a described preexisting mechanism novel. Compare mechanism identity separately from empirical support.",
        "Reading coverage is model-reported, not a mechanical verification of complete experiment or appendix reading.",
    ]

    def references(refs: list[str]) -> list[dict]:
        records = []
        for ref in refs:
            if ref not in indexed:
                raise ValueError("Unknown evidence ID in claim audit")
            item = indexed[ref]
            if item.get("paper_id") != paper["id"]:
                raise ValueError("Claim audit cites evidence from a different paper")
            # A reference must still point to the exact current source, not to
            # an earlier version, abstract replacement, or invented quotation.
            if item.get("source_hash") != source_hash:
                raise ValueError("Claim audit cites stale or unverified source evidence")
            start, end = item.get("start"), item.get("end")
            quote = item.get("quote")
            if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text)
                    or not isinstance(quote, str) or len(quote.strip()) < 15
                    or " ".join(text[start:end].split()) != " ".join(quote.split())):
                raise ValueError("Claim audit evidence quotation does not match the current source offsets")
            records.append(item)
        return records

    result = deepcopy(audit)
    coverage = result["reading_coverage"]
    if not is_full_text:
        coverage.update(experiments="unavailable", appendix="unavailable")
        warnings.append("Full text is unavailable: abstract/title/notes cannot establish experimental support.")
    if coverage["experiments"] != "read":
        warnings.append("Experiment reading is incomplete; obtain the relevant setups, baselines, controls and results.")
    if coverage["appendix"] in {"partial", "unavailable"}:
        warnings.append("Appendix evidence is incomplete or unavailable; retain this limitation and request targeted reading.")

    for record in result["claims"]:
        claim_refs = references(record["claim_evidence_ids"])
        result_refs = references(record["result_evidence_ids"])
        full_claim = is_full_text and any(item.get("source_kind") == "full_text" for item in claim_refs)
        eligible = [item["id"] for item in result_refs
                    if is_full_text and item.get("source_kind") == "full_text"
                    and item.get("kind") == "reported_result"
                    and isinstance(item.get("source_section"), str)
                    and _RESULT_SECTION.search(item["source_section"])
                    and isinstance(item.get("conditions"), str) and _concrete(item["conditions"])]
        gaps = []
        if not _concrete(record["claim"]):
            gaps.append("A concrete claim is required.")
        if not full_claim:
            gaps.append("The claim has no full-text quotation from this paper.")
        if not eligible:
            gaps.append("No eligible full-text reported result from an experiment/result/appendix section with stated conditions supports this judgment.")
        if len(eligible) < len(set(record["result_evidence_ids"])):
            gaps.append("Some result references are author claims, non-result sections, abstracts or lack tested conditions; they do not count as experimental support.")
        scope_gaps = [key for key, value in record["tested_scope"].items() if not _concrete(value)]
        if scope_gaps:
            gaps.append("Tested scope is unspecified for: " + ", ".join(scope_gaps) + ".")
        if not _concrete(record["warranted_conclusion"]):
            gaps.append("A concrete scope-bounded warranted conclusion is required.")
        requested = record["support_judgment"]
        # No result is also insufficient to assert contradiction or overclaiming;
        # failure to retrieve evidence is not evidence that the paper is wrong.
        if (not eligible or not full_claim or not _concrete(record["claim"])
                or not _concrete(record["warranted_conclusion"])
                or (requested == "supported_within_tested_scope" and scope_gaps)):
            record["support_judgment"] = "insufficient_evidence"
        record.update(requested_support_judgment=requested, audit_gaps=gaps,
                      full_text_claim_grounded=bool(full_claim),
                      eligible_result_evidence_ids=list(dict.fromkeys(eligible)))
        if requested != record["support_judgment"]:
            warnings.append("An unsupported claim judgment was downgraded to insufficient_evidence; obtain the missing paper evidence.")

    result["status"] = ("audited" if result["claims"] and any(
        claim["support_judgment"] != "insufficient_evidence" for claim in result["claims"])
        else "insufficient_evidence")
    if not result["claims"]:
        warnings.append("No claims were audited; absence of an audit establishes neither coverage nor novelty.")
    result["warnings"] = list(dict.fromkeys(warnings))
    return result
