"""Regression cases for confusing a paper's rhetoric with its demonstrated scope."""
from __future__ import annotations

import copy
import unittest

from research_idea.claims import assess_claims
from research_idea.schema import SCHEMAS, validate
from research_idea.store import digest


def example():
    claim_quote = "We introduce adaptive routing to improve every reasoning task."
    result_quote = "On Dataset A, Model B gains 2 points with 1000 tokens per item."
    paper = {"id": "paper-1", "content_kind": "full_text",
             "text": "Introduction\n" + claim_quote + "\nResults\n" + result_quote + "\nAppendix\nDetails."}
    evidence = []
    for ref, quote, kind, section in [("claim-1", claim_quote, "author_claim", "Introduction"),
                                      ("result-1", result_quote, "reported_result", "Results Table 1")]:
        start = paper["text"].index(quote)
        evidence.append({"id": ref, "paper_id": paper["id"], "source_kind": "full_text",
                         "source_hash": digest(paper["text"]), "quote": quote,
                         "start": start, "end": start + len(quote), "kind": kind,
                         "source_section": section, "conditions": "Dataset A; Model B; 1000 tokens per item."})
    audit = {"paper_id": paper["id"],
             "reading_coverage": {"experiments": "read", "appendix": "partial", "notes": "Only one appendix excerpt was supplied."},
             "claims": [{"claim": claim_quote, "claim_evidence_ids": ["claim-1"],
                         "tested_scope": {"tasks": "Arithmetic QA", "data": "Dataset A", "models": "Model B",
                                          "settings": "Zero-shot, one evaluation split", "budget": "1000 tokens per item"},
                         "result_evidence_ids": ["result-1"],
                         "warranted_conclusion": "Reported 2-point gain for Model B on Dataset A at 1000 tokens per item only.",
                         "limitations": ["One model and dataset; broad generalization is untested."],
                         "confounds": ["Prompt differences may affect the reported gain."],
                         "missing_controls": ["Matched-prompt baseline"],
                         "support_judgment": "supported_within_tested_scope",
                         "next_reading": ["Read Appendix B for prompt controls and variance."]}]}
    return audit, paper, evidence


class ClaimAuditTests(unittest.TestCase):
    def test_schema_registered_and_valid(self):
        audit, _, _ = example()
        validate(audit, SCHEMAS["audit_claims"])
        validate({"research_question": "Which routing target improves fixed-budget QA?", "scope": "Inference routing", "research_routes": [], "design_axes": [],
                  "queries": [{"query": "adaptive routing matched compute", "purpose": "counterevidence", "rationale": "Find negative controls", "route_ids": [], "axis_ids": []}],
                  "assumptions": []}, SCHEMAS["plan_search"])

    def test_claim_only_cannot_establish_empirical_support(self):
        audit, paper, evidence = example()
        audit["claims"][0]["result_evidence_ids"] = ["claim-1"]
        result = assess_claims(audit, paper, evidence)
        claim = result["claims"][0]
        self.assertEqual(claim["support_judgment"], "insufficient_evidence")
        self.assertEqual(claim["requested_support_judgment"], "supported_within_tested_scope")
        self.assertTrue(claim["full_text_claim_grounded"])
        self.assertEqual(claim["eligible_result_evidence_ids"], [])
        self.assertTrue(any("preexisting mechanism" in warning for warning in result["warnings"]))

    def test_narrow_result_preserves_scope_and_limitations_without_global_proof(self):
        audit, paper, evidence = example()
        original = copy.deepcopy(audit)
        result = assess_claims(audit, paper, evidence)
        claim = result["claims"][0]
        self.assertEqual(claim["support_judgment"], "supported_within_tested_scope")
        for field in ("tested_scope", "warranted_conclusion", "limitations", "confounds", "missing_controls", "next_reading"):
            self.assertEqual(claim[field], audit["claims"][0][field])
        self.assertTrue(any("not global proof" in warning for warning in result["warnings"]))
        self.assertTrue(any("not scientific entailment" in warning for warning in result["warnings"]))
        self.assertTrue(any("Appendix evidence is incomplete" in warning for warning in result["warnings"]))
        self.assertEqual(original, audit)

    def test_broad_overclaim_can_be_audited_against_narrow_results(self):
        audit, paper, evidence = example()
        audit["claims"][0]["support_judgment"] = "overstated"
        self.assertEqual(assess_claims(audit, paper, evidence)["claims"][0]["support_judgment"], "overstated")

    def test_absence_of_results_does_not_establish_paper_is_wrong(self):
        for judgment in ("supported_within_tested_scope", "overstated", "contradicted", "not_established"):
            audit, paper, evidence = example()
            audit["claims"][0].update(result_evidence_ids=[], support_judgment=judgment)
            with self.subTest(judgment=judgment):
                self.assertEqual(assess_claims(audit, paper, evidence)["claims"][0]["support_judgment"], "insufficient_evidence")

    def test_abstracts_never_establish_support_even_if_labelled_result(self):
        audit, paper, evidence = example()
        paper["content_kind"] = "abstract"
        for item in evidence:
            item["source_kind"] = "abstract"
        result = assess_claims(audit, paper, evidence)
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["reading_coverage"]["experiments"], "unavailable")
        self.assertEqual(result["reading_coverage"]["appendix"], "unavailable")

    def test_nonresult_sections_and_missing_conditions_do_not_count(self):
        for field, value in (("source_section", "Abstract"), ("source_section", "Introduction"),
                             ("conditions", "unknown"), ("kind", "author_claim"), ("kind", "limitation")):
            audit, paper, evidence = example()
            evidence[1][field] = value
            with self.subTest(field=field, value=value):
                self.assertEqual(assess_claims(audit, paper, evidence)["status"], "insufficient_evidence")

    def test_appendix_result_can_support_a_narrow_judgment(self):
        audit, paper, evidence = example()
        evidence[1]["source_section"] = "Appendix B.3"
        self.assertEqual(assess_claims(audit, paper, evidence)["status"], "audited")

    def test_missing_scope_cannot_support_bounded_result(self):
        for value in ("", "unknown", "not reported", "未知"):
            audit, paper, evidence = example()
            audit["claims"][0]["tested_scope"]["models"] = value
            with self.subTest(value=value):
                result = assess_claims(audit, paper, evidence)
                self.assertEqual(result["status"], "insufficient_evidence")
                self.assertTrue(any("models" in gap for gap in result["claims"][0]["audit_gaps"]))

    def test_dangling_and_crosspaper_references_rejected_in_either_role(self):
        for field in ("claim_evidence_ids", "result_evidence_ids"):
            for crosspaper in (False, True):
                audit, paper, evidence = example()
                audit["claims"][0][field] = ["foreign"]
                if crosspaper:
                    evidence.append(dict(evidence[1], id="foreign", paper_id="paper-2"))
                with self.subTest(field=field, crosspaper=crosspaper):
                    with self.assertRaisesRegex(ValueError, "different paper" if crosspaper else "Unknown evidence"):
                        assess_claims(audit, paper, evidence)

    def test_current_source_hash_and_quote_offsets_rechecked(self):
        for field, value in (("source_hash", "old-version"), ("quote", "A fabricated result that does not occur."),
                             ("start", -1), ("start", True), ("end", 100000)):
            audit, paper, evidence = example()
            evidence[1][field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    assess_claims(audit, paper, evidence)

    def test_duplicate_evidence_and_wrong_audit_paper_rejected(self):
        audit, paper, evidence = example()
        with self.assertRaisesRegex(ValueError, "Duplicate evidence"):
            assess_claims(audit, paper, evidence + [evidence[0]])
        audit["paper_id"] = "paper-2"
        with self.assertRaisesRegex(ValueError, "different paper"):
            assess_claims(audit, paper, evidence)

    def test_empty_and_excessive_audits(self):
        audit, paper, evidence = example()
        audit["claims"] *= 5
        with self.assertRaisesRegex(ValueError, "at most four"):
            assess_claims(audit, paper, evidence)
        audit["claims"] = []
        self.assertEqual(assess_claims(audit, paper, evidence)["status"], "insufficient_evidence")


if __name__ == "__main__":
    unittest.main()
