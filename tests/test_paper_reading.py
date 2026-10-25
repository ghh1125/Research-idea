"""Grounding, targeted reading, coverage and checkpoint integration (synthetic text)."""
import copy
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import tempfile
import unittest

from research_idea.backend_types import BackendResult
from research_idea.cli import main
from research_idea.config import DEFAULTS, write_config, load_config
from research_idea.controller import BudgetExhausted, Controller, make_evidence
from research_idea.paper_reading import FACETS, chunks, current_cards, initial_chunks, inventory, validate_card, with_coverage
from research_idea.report import export_report
from research_idea.store import Store, digest


def block(heading, quote):
    prefix = heading + "\nOBS: " + quote + "\n"
    return prefix + "x" * (511 - len(prefix)) + "\n"


def source():
    return {"id": "p1", "title": "Synthetic paper, not scientific evidence", "content_kind": "full_text",
        "text": block("1 Introduction", "The authors hypothesize that feedback improves routing.")
              + block("2 Method", "The router uses entropy available during inference.")
              + block("Appendix A", "The appendix reports only one model and one dataset.")}


def landscape_source():
    text = block("Abstract", "This source briefly advertises a new reasoning approach.")
    text += block("1 Introduction", "The goal requires several distinct ways of obtaining useful feedback.")
    text += block("2 Method", "The representative method learns from execution feedback.")
    text += block("3 Experiments", "The source reports an experiment in its own task setting.")
    for index in range(10):
        text += block(f"4.{index} Supporting material", "This section contains other source details.")
    text += block("5 Related Work", "Earlier approaches use additional data, inference search, or external feedback.")
    text += block("Appendix A", "The appendix discusses the source conditions.")
    return dict(id="p1", title="Synthetic landscape source", content_kind="full_text", text=text)


def card_for(payload):
    refs = [e["id"] for e in payload["evidence"]]
    return {"paper_id": payload["paper_id"], "paper_type": "method",
        "framework": [{"dimension": dim, "status": "analysis" if dim == "problem" else "not_assessable",
                       "summary": "Synthetic evidence is bounded; other details remain unverified.",
                       "evidence_ids": refs if dim == "problem" else []} for dim in FACETS],
        "components": [], "experiments": [], "author_limitations": [], "analyst_concerns": [],
        "opportunities": [], "reading_gaps": ["No visual inspection or independent reproduction."], "followup_requests": []}


class ReadingBackend:
    name = "reading-fixture"

    def __init__(self, followup=True):
        self.calls = []
        self.followup = followup

    def generate(self, task):
        data = json.loads(task.prompt.split("BEGIN_RESEARCH_DATA\n")[1].split("\nEND_RESEARCH_DATA")[0])
        self.calls.append((task.stage, copy.deepcopy(data)))
        if task.stage == "read_section":
            output = {"observations": [{"statement": "A synthetic source statement.", "quote": line[5:],
                "kind": "author_claim", "conditions": "Synthetic example only.", "source_section": "Supplied section"}
                for line in data["excerpt"].splitlines() if line.startswith("OBS: ")]}
        elif task.stage == "paper_card":
            output = card_for(data)
            if self.followup and not data["followup_attempts"]:
                appendix = next(s for s in data["inventory"]["sections"] if s["family"] == "appendix")
                output["followup_requests"] = [{"target_id": appendix["id"],
                    "question": "What experimental scope is stated in the appendix?",
                    "decision_impact": "Determine whether the broad claim was actually tested."}]
        else:
            raise AssertionError(task.stage)
        return BackendResult(output)


class ReadingInventoryTests(unittest.TestCase):
    def test_sections_assets_and_prose_references_are_distinguished(self):
        paper = {"id": "p", "text": "1 Introduction\nSee Table 1 for results.\n2 Method\nx = y (1)\n"
                 "3 Experiments\nTable 1: Matched budgets\nA 72 B 74\nFigure 2: Routing\nAppendix A\nDetails\n"}
        inv = inventory(paper)
        self.assertEqual([s["family"] for s in inv["sections"]], ["introduction", "method", "experiments", "appendix"])
        self.assertEqual([a["kind"] for a in inv["assets"]], ["equation", "table", "figure"])
        table = inv["assets"][1]
        self.assertIn("A 72 B 74", paper["text"][table["start"]:table["context_end"]])
        self.assertTrue(all(a["visual_status"] == "not_inspected" for a in inv["assets"]))

    def test_unstructured_text_is_not_reported_as_missing_paper(self):
        inv = inventory({"id": "p", "text": "Unstructured source text with no detected headings."})
        self.assertEqual(len(inv["sections"]), 1)
        self.assertEqual(inv["sections"][0]["family"], "other")
        self.assertTrue(any("do not claim" in gap for gap in inv["inventory_gaps"]))

    def test_chunks_preserve_source_without_gaps_or_stitched_quotes(self):
        text = source()["text"]
        parts = chunks(text, 512)
        self.assertEqual([(p["start"], p["end"]) for p in parts], [(0, 512), (512, 1024), (1024, 1536)])
        self.assertEqual("".join(text[p["start"]:p["end"]] for p in parts), text)
        self.assertEqual(chunks(text, 512), parts)

    def test_landscape_prioritizes_real_introduction_and_late_related_work_within_limit(self):
        paper = landscape_source()
        parts, inv = chunks(paper['text'], 512), inventory(paper)
        selected = initial_chunks(parts, inv, 3, reading_role='landscape')
        self.assertEqual([part['start'] for part in selected], [512, 14 * 512, 2 * 512])
        self.assertEqual(initial_chunks(parts, inv, 2, reading_role='landscape'), selected[:2])
        self.assertEqual(len({part['id'] for part in selected}), len(selected))

    def test_default_method_priority_is_unchanged(self):
        paper = landscape_source()
        parts, inv = chunks(paper['text'], 512), inventory(paper)
        selected = initial_chunks(parts, inv, 3)
        self.assertEqual(selected, initial_chunks(parts, inv, 3, reading_role='method'))
        self.assertEqual([part['start'] for part in selected], [0, 2 * 512, 3 * 512])

    def test_landscape_falls_back_without_introduction_or_related_work(self):
        paper = dict(id='p', text=block('Abstract', 'The abstract offers an overview of the supplied source.')
                     + block('2 Method', 'The method describes a source-specific operation.'))
        parts = chunks(paper['text'], 512)
        self.assertEqual(initial_chunks(parts, inventory(paper), 3, reading_role='landscape'), parts)

    def test_coverage_unions_spans_and_does_not_certify_visuals(self):
        inv = inventory(source())
        cov = with_coverage(inv, [{"start": 0, "end": 400}, {"start": 200, "end": 512}])
        self.assertEqual(cov["characters_supplied"], 512)
        self.assertEqual([s["text_coverage"] for s in cov["sections"]], ["complete", "unread", "unread"])
        self.assertEqual(cov["text_coverage"], "partial")
        self.assertIn("not proof of comprehension", cov["coverage_meaning"])

    def test_inventory_cap_is_explicit(self):
        inv = inventory({"id": "p", "text": "\n".join(f"{n} Heading\nTable {n}: Caption" for n in range(1, 205))})
        self.assertEqual(len(inv["sections"]), 200)
        self.assertEqual(len(inv["assets"]), 200)
        self.assertTrue(any("truncated" in gap for gap in inv["inventory_gaps"]))


class CardValidationTests(unittest.TestCase):
    def setUp(self):
        self.paper = source()
        self.inv = inventory(self.paper)
        quote = "The authors hypothesize that feedback improves routing."
        self.evidence = make_evidence(self.paper, [{"quote": quote, "statement": "Authors hypothesize a benefit.",
            "kind": "author_claim", "conditions": "Synthetic example", "source_section": "Introduction"}], self.paper["text"])
        self.card = card_for({"paper_id": "p1", "evidence": self.evidence})

    def validate(self, card=None, evidence=None):
        return validate_card(card or self.card, self.paper, evidence if evidence is not None else self.evidence, self.inv)

    def test_nine_dimensions_must_be_unique_and_explain_unknowns(self):
        self.validate()
        self.card["framework"][-1] = copy.deepcopy(self.card["framework"][0])
        with self.assertRaisesRegex(ValueError, "exactly once"):
            self.validate()

    def test_grounded_fields_cannot_omit_evidence(self):
        self.card["framework"][0]["evidence_ids"] = []
        with self.assertRaisesRegex(ValueError, "require source"):
            self.validate()

    def test_unknown_cross_paper_stale_and_bad_offset_evidence_rejected(self):
        for change in ({"id": "unknown"}, {"paper_id": "another-paper"}, {"source_hash": "stale"}, {"start": 0}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.validate(evidence=[{**self.evidence[0], **change}])

    def test_followup_cannot_invent_location(self):
        self.card["followup_requests"] = [{"target_id": "imagined-appendix", "question": "Read it", "decision_impact": "Check claim"}]
        with self.assertRaisesRegex(ValueError, "existing section"):
            self.validate()

    def test_author_claim_cannot_stand_in_for_reported_result_or_limitation(self):
        self.card["experiments"] = [{key: "Synthetic field" for key in ("name", "tested_claim", "setup", "comparator", "controls", "reported_result", "supported_conclusion", "unsupported_inference")}]
        self.card["experiments"][0].update(evidence_ids=[self.evidence[0]["id"]], asset_ids=[])
        with self.assertRaisesRegex(ValueError, "reported_result"):
            self.validate()
        self.card["experiments"] = []
        self.card["author_limitations"] = [{"statement": "An analyst suspicion.", "evidence_ids": [self.evidence[0]["id"]]}]
        with self.assertRaisesRegex(ValueError, "explicit limitation"):
            self.validate()

    def test_theory_paper_can_mark_experiments_inapplicable(self):
        self.card["paper_type"] = "theory"
        for facet in self.card["framework"]:
            if facet["dimension"] in {"experiment_design", "results"}:
                facet.update(status="not_applicable", summary="This supplied theoretical argument contains no empirical experiment.")
        self.validate()


class PaperReadingIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        self.store = Store(self.project)
        self.store.set("topic", "Feedback reliability in language models")
        self.store.put("papers", source())
        self.config = dict(DEFAULTS, backend="api", builtin_skills=False, auto_search=False,
            source_chars=512, max_paper_read_chunks=1, max_followup_reads=1, max_calls=30)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def run_read(self, backend=None, **overrides):
        backend = backend or ReadingBackend()
        controller = Controller(self.store, backend, dict(self.config, **overrides))
        controller.read_papers()
        return controller, backend

    def test_followup_reads_late_appendix_then_rebuilds_card_and_context(self):
        controller, backend = self.run_read()
        self.assertEqual([stage for stage, _ in backend.calls], ["read_section", "paper_card", "read_section", "paper_card"])
        reads = [data for stage, data in backend.calls if stage == "read_section"]
        self.assertEqual([r["source_span"]["start"] for r in reads], [0, 1024])
        self.assertIn("appendix", reads[-1]["question"])
        card = controller.context()["paper_cards"][0]
        self.assertEqual(card["status"], "analyzed")
        self.assertEqual(card["inventory"]["characters_supplied"], 1024)
        self.assertEqual(card["inventory"]["sections"][1]["text_coverage"], "unread")
        self.assertEqual(card["followup_attempts"][0]["status"], "additional_text_supplied")
        self.assertEqual(len(self.store.rows("evidence")), 2)
        card_payload = [data for stage, data in backend.calls if stage == 'paper_card'][-1]
        self.assertEqual(card_payload['citation_groups']['reported_result_ids'], [])
        self.assertEqual(card_payload['citation_groups']['author_limitation_ids'], [])

    def test_selection_question_and_research_routes_reach_initial_reading(self):
        paper = source()
        paper['selection'] = {'reading_question': 'Which information does the router actually use?',
                              'reason': 'Understand the source mechanism.', 'route_ids': ['information']}
        self.store.put('papers', paper)
        route = {'id': 'information', 'question': 'What information is available to the decision?'}
        self.store.set('search_plans', {'initial': {'research_routes': [route,
            {'id': 'optimization', 'question': 'How is optimization affected?'}]},
            'candidate-old': {'research_routes': [{'id': 'information', 'question': 'An old candidate route.'}]}})
        self.store.set('chat_messages', [{'role': 'user', 'content': 'Keep the original broad research goal.'}])
        _, backend = self.run_read()
        reads = [data for stage, data in backend.calls if stage == 'read_section']
        self.assertEqual(reads[0]['question'], paper['selection']['reading_question'])
        self.assertEqual(reads[1]['question'], 'What experimental scope is stated in the appendix?')
        for stage, payload in backend.calls:
            if stage in {'read_section', 'paper_card'}:
                self.assertEqual(payload['reading_intent'], {**paper['selection'], 'research_routes': [route],
                                                             'reading_role': 'method'})
            if stage == 'paper_card':
                self.assertEqual(payload['user_notes'], ['Keep the original broad research goal.'])
        # Observations still come from the original source, not the route or user notes.
        self.assertTrue(all(e['quote'] in paper['text'] for e in self.store.rows('evidence')))

    def test_legacy_paper_without_selection_keeps_neutral_reading(self):
        _, backend = self.run_read(ReadingBackend(followup=False))
        read = next(payload for stage, payload in backend.calls if stage == 'read_section')
        card = next(payload for stage, payload in backend.calls if stage == 'paper_card')
        self.assertEqual(read['question'], '')
        self.assertEqual(card['reading_intent'], {'reading_question': '', 'reason': '',
                                                 'route_ids': [], 'research_routes': [], 'reading_role': 'method'})
        self.assertEqual(card['user_notes'], [])

    def test_landscape_role_and_late_background_evidence_reach_card_and_context(self):
        paper = landscape_source()
        paper['selection'] = dict(reading_role='landscape', reading_question='Which broad approaches pursue the goal?',
                                  reason='Understand the field-level approaches.', route_ids=[])
        self.store.put('papers', paper)
        controller, backend = self.run_read(ReadingBackend(followup=False), max_paper_read_chunks=3)
        reads = [payload for stage, payload in backend.calls if stage == 'read_section']
        self.assertEqual([read['source_span']['start'] for read in reads], [512, 14 * 512, 2 * 512])
        self.assertEqual(len(reads), 3)
        card = next(payload for stage, payload in backend.calls if stage == 'paper_card')
        for payload in reads + [card]:
            self.assertEqual(payload['reading_intent']['reading_role'], 'landscape')
            self.assertEqual(payload['reading_intent']['reading_question'], paper['selection']['reading_question'])
        quote = 'Earlier approaches use additional data, inference search, or external feedback.'
        self.assertTrue(any(e['quote'] == quote for e in card['evidence']))
        self.assertTrue(any(e['quote'] == quote for e in controller.ideation_context()['evidence']))
        self.assertEqual(controller.context()['paper_cards'][0]['inventory']['text_coverage'], 'partial')

    def test_changed_reading_role_invalidates_tasks_then_resumes_from_role_cache(self):
        paper = landscape_source()
        self.store.put('papers', paper)
        self.run_read(ReadingBackend(followup=False), max_paper_read_chunks=3)
        paper['selection'] = {'reading_role': 'landscape'}
        self.store.put('papers', paper)
        _, changed = self.run_read(ReadingBackend(followup=False), max_paper_read_chunks=3)
        self.assertEqual([stage for stage, _ in changed.calls], ['read_section'] * 3 + ['paper_card'])
        self.assertTrue(all(payload['reading_intent']['reading_role'] == 'landscape'
                            for _, payload in changed.calls))
        _, resumed = self.run_read(ReadingBackend(followup=False), max_paper_read_chunks=3)
        self.assertEqual(resumed.calls, [])

    def test_old_selection_keeps_its_route_meaning_after_replanning(self):
        paper = source()
        old_route = {'id': 'R1', 'question': 'The earlier source reading question.'}
        paper['selection'] = {'reading_question': 'Understand the earlier mechanism.',
                              'route_ids': ['R1'], 'research_routes': [old_route]}
        self.store.put('papers', paper)
        self.store.set('search_plans', {'initial': {'research_routes': [
            {'id': 'R1', 'question': 'A different route that happens to reuse the ID.'}]}})
        _, backend = self.run_read(ReadingBackend(followup=False))
        for stage, payload in backend.calls:
            if stage in {'read_section', 'paper_card'}:
                self.assertEqual(payload['reading_intent']['research_routes'], [old_route])

    def test_resume_replays_followup_without_new_backend_calls(self):
        self.run_read()
        before = self.store.get("paper_cards")
        _, backend = self.run_read(max_calls=1)
        self.assertEqual(backend.calls, [])
        self.assertEqual(self.store.get("paper_cards"), before)
        self.assertEqual(self.store.get("calls_used"), 4)

    def test_invalid_summary_keeps_exact_evidence_and_does_not_loop_on_resume(self):
        class InvalidSummary(ReadingBackend):
            def generate(self, task):
                result = super().generate(task)
                if task.stage == 'paper_card':
                    result.output['framework'][0]['evidence_ids'] = ['made-up-reference']
                return result
        backend = InvalidSummary(followup=False)
        controller, _ = self.run_read(backend)
        self.assertEqual(sum(stage == 'paper_card' for stage, _ in backend.calls), 2)
        self.assertEqual(len(self.store.rows('evidence')), 1)
        evidence = self.store.rows('evidence')[0]
        self.assertEqual(evidence['quote'], source()['text'][evidence['start']:evidence['end']])
        self.assertNotIn('p1', self.store.get('paper_cards', {}))
        _, resumed = self.run_read(InvalidSummary(followup=False))
        self.assertEqual(resumed.calls, [])
        self.assertTrue(controller.context()['evidence'])

    def test_zero_followup_budget_retains_explicit_unread_request(self):
        _, backend = self.run_read(max_followup_reads=0)
        self.assertEqual(sum(stage == "read_section" for stage, _ in backend.calls), 1)
        self.assertEqual(sum(stage == "paper_card" for stage, _ in backend.calls), 1)
        card = self.store.get("paper_cards")["p1"]
        self.assertEqual(card["followup_attempts"][0]["status"], "reading_limit_reached")
        self.assertEqual(card["inventory"]["characters_supplied"], 512)
        _, resumed = self.run_read(max_followup_reads=0, max_calls=2)
        self.assertEqual(resumed.calls, [])
        self.assertEqual(self.store.get("paper_cards")["p1"], card)

    def test_already_supplied_target_does_not_repeat_identical_text(self):
        _, backend = self.run_read(max_paper_read_chunks=3)
        self.assertEqual(sum(stage == "read_section" for stage, _ in backend.calls), 3)
        self.assertEqual(sum(stage == "paper_card" for stage, _ in backend.calls), 1)
        card = self.store.get("paper_cards")["p1"]
        self.assertEqual(card["followup_attempts"][0]["status"], "no_unread_target_text")
        self.assertEqual(card["inventory"]["text_coverage"], "complete_supplied_text")
        _, resumed = self.run_read(max_paper_read_chunks=3, max_calls=4)
        self.assertEqual(resumed.calls, [])
        self.assertEqual(self.store.get("paper_cards")["p1"], card)

    def test_budget_stop_after_new_evidence_does_not_export_old_card(self):
        with self.assertRaises(BudgetExhausted):
            self.run_read(max_calls=3)
        _, report_file = export_report(self.store, self.store.project)
        report = json.loads(report_file.read_text())
        self.assertEqual(report["paper_cards"]["p1"]["status"], "pending")
        self.assertEqual(report["paper_cards"]["p1"]["inventory"]["characters_supplied"], 1024)
        _, backend = self.run_read()
        self.assertEqual([stage for stage, _ in backend.calls], ["paper_card"])

    def test_source_change_invalidates_card_and_reextracts(self):
        controller, _ = self.run_read()
        changed = source()
        changed["text"] = changed["text"].replace("one model", "two models")
        self.store.put("papers", changed)
        self.assertEqual(controller.context()["paper_cards"][0]["status"], "pending")
        _, backend = self.run_read()
        self.assertEqual(sum(stage == "read_section" for stage, _ in backend.calls), 2)
        self.assertTrue(all(e["source_hash"] == digest(changed["text"]) for e in self.store.rows("evidence")))

    def test_skill_change_reextracts_instead_of_preserving_withdrawn_evidence(self):
        skill = self.project / "custom.md"
        skill.write_text("Investigate the routing assumption.")
        self.run_read(skill_paths=[str(skill)])
        first_ids = {e["guidance_key"] for e in self.store.rows("evidence")}
        skill.write_text("Investigate the routing assumption and matching compute budgets.")
        _, backend = self.run_read(skill_paths=[str(skill)])
        self.assertEqual(len(backend.calls), 4)
        self.assertTrue(first_ids.isdisjoint({e["guidance_key"] for e in self.store.rows("evidence")}))

    def test_duplicate_quote_offsets_point_to_the_chunk_actually_read(self):
        paper = source()
        quote = "The authors hypothesize that feedback improves routing."
        paper["text"] = block("1 Introduction", quote) + block("Appendix A", quote)
        self.store.put("papers", paper)
        self.run_read()
        evidence = self.store.rows("evidence")
        self.assertEqual(len(evidence), 2)
        self.assertEqual(sorted(e["start"] for e in evidence), [paper["text"].index(quote), paper["text"].rindex(quote)])

    def test_removing_an_evidence_record_invalidates_synthesis(self):
        controller, _ = self.run_read()
        self.store.replace_evidence("p1", self.store.rows("evidence")[:1])
        self.assertEqual(controller.context()["paper_cards"][0]["status"], "pending")

    def test_export_and_cli_inspect_show_same_framework_and_coverage(self):
        self.run_read()
        _, machine = export_report(self.store, self.store.project)
        report = json.loads(machine.read_text())
        self.assertEqual(report["schema_version"], 13)
        card_path = machine.parent / report["paper_card_files"]["p1"]
        markdown = card_path.read_text()
        self.assertIn("九维分析框架", markdown)
        self.assertIn("1024 / 1536", markdown)
        self.assertIn("图像、表格布局和公式渲染均未视觉核查", markdown)
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            code = main(["inspect", "--project", str(self.project), "p1", "--paper-card"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), report["paper_cards"]["p1"])

    def test_reading_configuration_is_bounded_and_round_trips(self):
        write_config(self.project, {"max_followup_reads": 0, "max_paper_read_chunks": 4})
        self.assertEqual(load_config(self.project)["max_followup_reads"], 0)
        for values in ({"max_followup_reads": -1}, {"max_followup_reads": True}, {"max_followup_reads": 11},
                       {"max_paper_read_chunks": 51}, {"max_paper_read_chunks": 0}, {"deep_reading": "yes"}, {"source_chars": 255}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                write_config(self.project, values)


if __name__ == "__main__":
    unittest.main()
