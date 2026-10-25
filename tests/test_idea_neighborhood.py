"""Candidate-directed retrieval must change the actual first-phase handoff."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_idea.backend_types import BackendResult
from research_idea.config import DEFAULTS
from research_idea.controller import Controller, make_evidence, OutputValidationError
from research_idea.demo import DemoBackend
from research_idea.idea_neighborhood import normalize_comparison_search
from research_idea.presentation import argument_markdown
from research_idea.report import export_report
from research_idea.search_scope import config_scope
from research_idea.store import Store

QUOTE = 'Our method obtains its labels by executing the available program and records failed executions.'
PAPER = {'id': 'arxiv:2501.01234', 'title': 'Executable supervision for structured reasoning',
         'url': 'https://arxiv.org/abs/2501.01234', 'year': 2025, 'authors': ['Fixture Author'],
         'source': 'arxiv', 'content_kind': 'abstract', 'abstract': QUOTE}
SEARCH = {'acquisition_requests': [], 'method_family': 'executable supervision', 'comparison_need': 'How are labels actually obtained?',
          'queries': [{'query': 'executable supervision reasoning', 'rationale': 'Find the actual label source', 'time_scope': 'lineage'}]}
INPUT = dict(information='判断标签', source='输入程序', construction='执行程序并记录返回值',
             reliability_basis='语言语义规定返回值，执行超时不提供答案', error_handling='保留异常类型，错误标签不进入学习',
             applicability='具有可执行程序的材料', evidence_ids=[])


def payload(task):
    return json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])


class Backend(DemoBackend):
    def __init__(self, search=True):
        self.calls, self.search, self.requests = [], search, []

    def generate(self, task):
        data = payload(task)
        self.calls.append((task.stage, copy.deepcopy(data)))
        if task.stage == 'inspect_source':
            return BackendResult({'observations': [dict(statement=QUOTE, quote=QUOTE, kind='author_claim',
                conditions='Synthetic executable program fixture', source_section='Method')]})
        result = super().generate(task)
        if task.stage == 'propose':
            candidate = result.output['candidates'][0]
            candidate['comparison_search'] = copy.deepcopy(SEARCH)
            candidate['comparison_search']['acquisition_requests'] = copy.deepcopy(self.requests)
            if not self.search or data['proposal_mode'] == 'complete':
                candidate['comparison_search']['queries'] = []
            if data['proposal_mode'] == 'complete':
                candidate['comparison_search']['acquisition_requests'] = []
            candidate['idea_core']['information_path'] = [copy.deepcopy(INPUT)]
            if data['proposal_mode'] == 'complete':
                candidate['idea_core']['information_path'][0]['evidence_ids'] = [e['id'] for e in data['evidence']]
        return result


class NeighborhoodTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        self.store.set('topic', 'Improve useful reasoning from available information')
        self.cfg = dict(DEFAULTS, backend='codex', builtin_skills=False, max_candidates=1, max_seconds=60)
        self.backend = Backend()
        self.events = []
        self.controller = Controller(self.store, self.backend, self.cfg,
            activity=lambda stage, result, cached: self.events.append((stage, copy.deepcopy(result), cached)))

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def hydrate(self, ids):
        for p in self.store.rows('papers'):
            if p['id'] in ids:
                self.store.put('papers', dict(p, content_kind='full_text', text=QUOTE))
        return True

    def run_idea(self, hydrate=None):
        with patch('research_idea.literature.discover', return_value=[copy.deepcopy(PAPER)]) as discover, \
             patch.object(self.controller, 'retrieve_full_texts', side_effect=hydrate or self.hydrate):
            result = self.controller.form_ideas()
        return result, discover

    def test_draft_search_read_complete_and_only_final_idea_is_published(self):
        result, discover = self.run_idea()
        self.assertEqual([s for s, _ in self.backend.calls], ['explore_problems', 'deepen_problem', 'deepen_problem', 'map', 'propose', 'screen_papers', 'inspect_source', 'propose'])
        first, final = [p for s, p in self.backend.calls if s == 'propose']
        self.assertEqual(first['problem_model'], final['problem_model'])
        self.assertEqual(first['evidence'], [])
        self.assertEqual(final['evidence'][0]['quote'], QUOTE)
        self.assertEqual(final['papers'][0]['id'], PAPER['id'])
        self.assertEqual(final['idea_neighborhoods'][0]['search'], SEARCH)
        self.assertEqual(discover.call_args.kwargs['since'], '')
        self.assertEqual([r for s, r, _ in self.events if s == 'propose'], [result])
        self.assertEqual(self.store.rows('candidates'), [])
        self.assertEqual(self.controller.initial_paper_ids(), [])
        self.assertEqual(self.controller.ideation_context()['evidence'], [])
        self.assertEqual(self.store.rows('papers')[0]['selection']['phase'], 'neighbor')
        before = len(self.backend.calls)
        again, search_again = self.run_idea()
        self.assertEqual(again, result)
        self.assertEqual(len(self.backend.calls), before)
        search_again.assert_not_called()
        self.assertTrue(self.events[-1][2])

    def test_stopped_download_resumes_selected_sources_without_rescreening(self):
        with self.assertRaises(KeyboardInterrupt):
            self.run_idea(hydrate=lambda ids: (_ for _ in ()).throw(KeyboardInterrupt()))
        state = next(iter(self.store.get('idea_neighborhoods').values()))
        self.assertTrue(state['selection_complete'])
        self.assertEqual(state['paper_ids'], [PAPER['id']])
        result, _ = self.run_idea()
        self.assertEqual(sum(s == 'screen_papers' for s, _ in self.backend.calls), 1)
        self.assertEqual(len([r for s, r, _ in self.events if s == 'propose']), 1)
        self.assertTrue(result['candidates'])

    def test_no_missing_comparison_means_no_search_or_extra_proposal(self):
        self.backend.search = False
        _, discover = self.run_idea()
        discover.assert_not_called()
        self.assertEqual([s for s, _ in self.backend.calls], ['explore_problems', 'deepen_problem', 'deepen_problem', 'map', 'propose'])

    def test_no_reading_capacity_still_passes_metadata_as_leads(self):
        self.cfg['max_papers'] = 1
        self.store.put('papers', dict(PAPER, id='existing', title='Different background', url=''))
        _, _ = self.run_idea()
        final = self.backend.calls[-1][1]
        self.assertEqual(final['idea_neighborhoods'][0]['metadata_only'][0]['id'], PAPER['id'])
        self.assertNotIn(PAPER['id'], [p['id'] for p in final['papers']])
        self.assertEqual(final['evidence'], [])
        self.assertNotIn('inspect_source', [s for s, _ in self.backend.calls])

    def test_information_path_survives_report_and_argument_order(self):
        result, _ = self.run_idea()
        proposal = result['candidates'][0]
        candidate = dict(id='idea', proposal=proposal, versions=[], execution_status='completed',
                         research_status='proposed', empirical_status='untested')
        self.store.put('candidates', candidate)
        markdown, datafile = export_report(self.store, self.store.project)
        report = json.loads(datafile.read_text())
        self.assertEqual(report['candidates'][0]['proposal']['idea_core'], proposal['idea_core'])
        self.assertTrue(report['idea_neighborhoods'])
        rendered = argument_markdown(proposal['motivation'], proposal)
        for key, text in INPUT.items():
            if key != 'evidence_ids':
                self.assertIn(text, rendered)
        labels = ['Background ·', 'Existing methods ·', 'Possible problem ·', 'Motivation ·', 'Idea ·']
        positions = [rendered.index(label) for label in labels]
        self.assertEqual(positions, sorted(positions))
        self.assertIn(INPUT['reliability_basis'], markdown.read_text())

    def test_fixed_dates_and_cs_scope_are_not_changed_by_lineage(self):
        fixed = dict(self.cfg, search_date_mode='fixed', search_since='2025-02-01', search_until='2026-01-01')
        self.assertEqual(config_scope(fixed, 'lineage'), config_scope(fixed, 'strategy'))
        rolling = config_scope(self.cfg, 'lineage')
        self.assertEqual(rolling['since'], '')
        self.assertTrue(rolling['cs_only'])
        self.assertEqual(rolling['arxiv_categories'], ['cs.*'])

    def test_query_normalization_retains_first_scope(self):
        search = copy.deepcopy(SEARCH)
        search['queries'][0]['query'] = 'executable   supervision reasoning'
        search['queries'].append(dict(search['queries'][0], query='EXECUTABLE supervision reasoning', time_scope='recent'))
        normalized = normalize_comparison_search(search)
        self.assertEqual(len(normalized['queries']), 1)
        self.assertEqual(normalized['queries'][0]['time_scope'], 'lineage')

    def test_acquisition_request_reopens_known_source_offline_and_keeps_neutral_evidence(self):
        self.cfg['auto_search'] = False
        self.backend.search = False
        paper = dict(PAPER, content_kind='full_text', text=QUOTE)
        self.store.put('papers', paper)
        obs = dict(statement=QUOTE, quote=QUOTE, kind='author_claim',
                   conditions='Synthetic executable program fixture', source_section='Method')
        neutral = make_evidence(paper, [obs], QUOTE)[0]
        neutral.update(extraction_stage='read_section', guidance_key='earlier-neutral-reading-guidance')
        self.store.replace_evidence(paper['id'], [neutral])
        initial = self.controller.ideation_context()
        self.backend.requests = [dict(information='Execution feedback', question='How is the label obtained?',
            paper_ids=[paper['id']], search_terms=['executing', 'failed executions'])]
        result, discover = self.run_idea(hydrate=lambda ids: False)
        discover.assert_not_called()
        stages = [stage for stage, _ in self.backend.calls]
        self.assertEqual(stages, ['explore_problems', 'deepen_problem', 'deepen_problem', 'map', 'propose', 'inspect_source', 'propose'])
        inspection = next(data for stage, data in self.backend.calls if stage == 'inspect_source')
        self.assertEqual(inspection['acquisition_requests'], self.backend.requests)
        self.assertIn('reading_selection', inspection)
        final = self.backend.calls[-1][1]
        ids = {item['id'] for item in final['evidence']}
        self.assertIn(neutral['id'], ids)
        self.assertEqual(len(ids), 2)
        self.assertEqual(self.controller.ideation_context(), initial)
        self.assertTrue(final['idea_neighborhoods'][0]['readings'][0]['selection']['spans'])
        self.assertTrue(self.store.get('focused_readings'))
        before = len(self.backend.calls)
        again, _ = self.run_idea(hydrate=lambda ids: False)
        self.assertEqual(again, result)
        self.assertEqual(len(self.backend.calls), before)

    def test_unknown_acquisition_source_is_repaired_before_reading(self):
        self.backend.search = False
        self.backend.requests = [dict(information='Feedback', question='How is it obtained?',
            paper_ids=['invented-paper'], search_terms=['feedback'])]
        with patch.object(self.controller, 'focus_sources') as reading:
            with self.assertRaisesRegex(OutputValidationError, 'Unknown closest-work paper ID'):
                self.controller.form_ideas()
        reading.assert_not_called()
