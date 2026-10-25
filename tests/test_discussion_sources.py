"""Real persistence around question-directed search and targeted source reading."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_idea.backend_types import BackendResult
from research_idea.config import DEFAULTS
from research_idea.controller import Controller
from research_idea.discussion_sources import investigate_problem, research_requests, validate_requests
from research_idea.literature import normalize_paper
from research_idea.store import Store


class SourceController:
    """Match actual controller return contracts, including selection's bool."""
    def __init__(self, store, *, auto_search=True, backend='codex'):
        self.store = store
        self.config = dict(auto_search=auto_search, backend=backend, search_source='hybrid',
                           search_venues=['ACL', 'ICLR'])
        self.guidance_keys = {'inspect_source': 'v1'}
        self.phase = 'ideation'
        self.calls = []
        self.events = []
        self.fail_reading = False
        self.fail_download = False
        self.available = ['new1', 'new2']
        self.search_fail = False

    def context(self):
        return {'search_windows': {'novelty': {'since': '2026-04-25', 'until': '2026-10-25'}}}

    def progress(self, text):
        self.events.append(text)

    def search_once(self, query, reason, max_new=None, purpose='strategy', candidate=None):
        self.calls.append(('search', query, reason, purpose, max_new))
        key = 'search:' + query
        ledger = self.store.get('search_ledger', {})
        ledger[key] = {'status': 'failed' if self.search_fail else 'completed',
                       'metadata': [] if self.search_fail else [{'id': pid} for pid in self.available]}
        self.store.set('search_ledger', ledger)
        return key

    def ideation_context(self):
        return {'papers': self.store.rows('papers')}

    def task(self, stage, payload, checker, *, publish=True):
        self.calls.append(('task', stage, deepcopy(payload)))
        result = {'requests': [{'question': '已有方法在状态变化后仍能共享哪些信息？',
                                'query': 'agent shared state', 'paper_ids': []}]}
        checker(result)
        return result

    def select_search_results(self, keys, limit, candidate=None, *, checkpoint_design=False, selection_phase=None):
        self.calls.append(('select', keys, limit, selection_phase))
        selected = self.available[:limit]
        for paper_id in selected:
            self.store.put('papers', {'id': paper_id, 'title': paper_id,
                'text': 'Original source passage.', 'content_kind': 'full_text'})
        candidate['retrieved_work_ids'] = selected
        return bool(selected)

    def retrieve_full_texts(self, selected):
        self.calls.append(('retrieve', list(selected)))
        if self.fail_download:
            raise RuntimeError('download interrupted')

    def focus_sources(self, candidate, selected_ids=None, reading_question='', acquisition_requests=None):
        self.calls.append(('read', list(selected_ids), reading_question, deepcopy(acquisition_requests), self.phase))
        if self.fail_reading:
            raise RuntimeError('model failed after source selection')
        readings = []
        for paper_id in selected_ids:
            evidence_id = 'ev_' + paper_id
            self.store.replace_evidence(paper_id, [{'id': evidence_id, 'paper_id': paper_id,
                'quote': 'Original source passage.', 'statement': 'A grounded source detail.'}])
            readings.append({'paper_id': paper_id, 'evidence_ids': [evidence_id],
                             'reading_question': reading_question})
        return readings


class DiscussionSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))
        self.controller = SourceController(self.store)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def request(self, *, query='agent shared state', paper_ids=None):
        return [{'question': '已有方法在状态变化后仍能共享哪些信息？',
                 'query': query, 'paper_ids': paper_ids or []}]

    def test_search_selects_two_and_passes_question_into_actual_reading(self):
        requests = self.request()
        result = research_requests(self.controller, requests, key='turn-1')
        self.assertEqual(result['selected_ids'], ['new1', 'new2'])
        self.assertEqual(self.controller.calls[0], ('search', 'agent shared state',
            requests[0]['question'], 'novelty', 0))
        reading = next(call for call in self.controller.calls if call[0] == 'read')
        self.assertEqual(reading[1], ['new1', 'new2'])
        self.assertEqual(reading[2], requests[0]['question'])
        self.assertEqual(reading[-1], 'problem')
        self.assertEqual(self.store.get('question_source_evidence'), ['ev_new1', 'ev_new2'])
        self.assertEqual(self.controller.phase, 'ideation')
        self.assertTrue(result['completed'])
        self.assertTrue(result['performed'])
        self.assertEqual(result['search_status'], 'completed')
        self.assertEqual(result['reading_status'], 'completed')

    def test_completed_request_reuses_sources_without_new_calls(self):
        first = research_requests(self.controller, self.request(), key='turn-1')
        calls = deepcopy(self.controller.calls)
        again = research_requests(self.controller, self.request(), key='turn-1')
        self.assertEqual(first, again)
        self.assertEqual(self.controller.calls, calls)

    def test_failed_reading_reuses_persisted_selection_and_restores_phase(self):
        self.controller.fail_reading = True
        with self.assertRaisesRegex(RuntimeError, 'model failed'):
            research_requests(self.controller, self.request(), key='turn-1')
        self.assertEqual(self.controller.phase, 'ideation')
        entry = next(iter(self.store.get('problem_research_ledger').values()))
        self.assertFalse(entry['completed'])
        self.assertEqual(entry['selected_ids'], ['new1', 'new2'])
        self.controller.fail_reading = False
        self.controller.available = ['different']
        result = research_requests(self.controller, self.request(), key='turn-1')
        self.assertEqual(result['selected_ids'], ['new1', 'new2'])
        self.assertEqual(len([call for call in self.controller.calls if call[0] == 'search']), 1)
        self.assertEqual(len([call for call in self.controller.calls if call[0] == 'select']), 1)

    def test_source_revision_invalidates_completed_reading(self):
        research_requests(self.controller, self.request(), key='turn-1')
        self.store.set('source_revision', 1)
        research_requests(self.controller, self.request(), key='turn-1')
        self.assertEqual(len([call for call in self.controller.calls if call[0] == 'read']), 2)

    def test_download_interruption_keeps_same_selection(self):
        self.controller.fail_download = True
        with self.assertRaisesRegex(RuntimeError, 'download interrupted'):
            research_requests(self.controller, self.request(), key='download-turn')
        saved = next(iter(self.store.get('problem_research_ledger').values()))
        self.assertEqual(saved['selected_ids'], ['new1', 'new2'])
        self.controller.fail_download = False
        self.controller.available = ['different']
        result = research_requests(self.controller, self.request(), key='download-turn')
        self.assertEqual(result['selected_ids'], ['new1', 'new2'])
        self.assertEqual(len([call for call in self.controller.calls if call[0] == 'select']), 1)

    def test_disabled_search_reports_no_search_but_can_read_existing_sources(self):
        self.controller.config['auto_search'] = False
        self.store.put('papers', {'id': 'local', 'title': 'Local supplied source',
                                 'content_kind': 'full_text', 'text': 'Original source passage.'})
        result = research_requests(self.controller, self.request(paper_ids=['local']), key='local-turn')
        self.assertFalse(result['search_enabled'])
        self.assertEqual(result['search_status'], 'disabled')
        self.assertTrue(result['reading_performed'])
        self.assertEqual(result['search_keys'], [])
        self.assertEqual(result['selected_ids'], ['local'])
        self.assertEqual(self.store.get('question_source_evidence'), ['ev_local'])
        self.assertNotIn('search', [call[0] for call in self.controller.calls])

    def test_disabled_search_with_query_does_not_invent_results(self):
        self.controller.config['auto_search'] = False
        result = research_requests(self.controller, self.request(), key='off-turn')
        self.assertFalse(result['search_enabled'])
        self.assertFalse(result['performed'])
        self.assertEqual(result['search_status'], 'disabled')
        self.assertEqual(result['search_keys'], [])
        self.assertEqual(result['selected_ids'], [])
        self.assertEqual(result['readings'], [])
        self.assertNotIn('search', [call[0] for call in self.controller.calls])
        self.assertNotIn('read', [call[0] for call in self.controller.calls])

    def test_query_only_no_results_produces_no_evidence(self):
        self.controller.available = []
        result = research_requests(self.controller, self.request(), key='nothing-found')
        self.assertEqual(result['selected_ids'], [])
        self.assertEqual(result['readings'], [])
        self.assertEqual(self.store.get('question_source_evidence'), [])
        self.assertEqual(result['search_status'], 'no_results')

    def test_failed_search_is_distinct_from_success_with_no_hits(self):
        self.controller.available = []
        self.controller.search_fail = True
        result = research_requests(self.controller, self.request(), key='search-failed')
        self.assertTrue(result['search_performed'])
        self.assertEqual(result['search_status'], 'failed')
        self.assertEqual(result['readings'], [])

    def test_enabling_search_invalidates_disabled_run(self):
        self.controller.config['auto_search'] = False
        disabled = research_requests(self.controller, self.request(), key='same-turn')
        self.assertFalse(disabled['performed'])
        self.controller.config['auto_search'] = True
        enabled = research_requests(self.controller, self.request(), key='same-turn')
        self.assertTrue(enabled['search_performed'])
        self.assertEqual(enabled['selected_ids'], ['new1', 'new2'])

    def test_problem_reading_plan_is_reused_after_new_sources_and_restart(self):
        seed = {'id': 'p1', 'question': '信息在变化时哪些已有关系仍成立？'}
        first = investigate_problem(self.controller, seed)
        self.assertEqual(len([call for call in self.controller.calls if call[0] == 'task']), 1)
        self.assertEqual(len(self.store.rows('papers')), 2)
        # A fresh controller has no in-memory task cache. Persisted planning is enough.
        restarted = SourceController(self.store)
        result = investigate_problem(restarted, seed)
        self.assertEqual(result, first)
        self.assertEqual(restarted.calls, [])

    def test_problem_plan_survives_failure_after_selecting_sources(self):
        seed = {'id': 'p1', 'question': '信息变化后已有关系还成立吗？'}
        self.controller.fail_reading = True
        with self.assertRaises(RuntimeError):
            investigate_problem(self.controller, seed)
        restarted = SourceController(self.store)
        result = investigate_problem(restarted, seed)
        self.assertEqual(result['selected_ids'], ['new1', 'new2'])
        self.assertNotIn('task', [call[0] for call in restarted.calls])
        self.assertNotIn('search', [call[0] for call in restarted.calls])
        self.assertNotIn('select', [call[0] for call in restarted.calls])

    def test_supplied_papers_use_remaining_total_reading_allowance(self):
        self.store.put('papers', {'id': 'known', 'title': 'Known', 'content_kind': 'full_text'})
        result = research_requests(self.controller, self.request(paper_ids=['known']), key='mixed')
        self.assertEqual(result['selected_ids'], ['known', 'new1'])
        self.assertEqual(next(call for call in self.controller.calls if call[0] == 'select')[2], 1)

    def test_invalid_paper_reference_is_rejected_before_any_source_calls(self):
        with self.assertRaisesRegex(ValueError, 'supplied paper'):
            research_requests(self.controller, self.request(query='', paper_ids=['invented']), key='invalid')
        self.assertEqual(self.controller.calls, [])
        self.assertEqual(self.controller.phase, 'ideation')

    def test_at_most_two_focused_requests(self):
        with self.assertRaisesRegex(ValueError, 'At most two'):
            validate_requests(self.request() * 3, set())
        with self.assertRaisesRegex(ValueError, 'question'):
            validate_requests([{'question': 'why?', 'query': '', 'paper_ids': []}], set())

    def test_investigate_skips_backend_demo_or_disabled_auto_search(self):
        for controller in (SourceController(self.store, auto_search=False),
                           SourceController(self.store, backend='demo')):
            self.assertIsNone(investigate_problem(controller, {'question': '问题'}))
            self.assertEqual(controller.calls, [])

    def test_real_selection_can_add_two_after_initial_cap_without_fake_candidate(self):
        records = [normalize_paper({'id': name, 'title': 'Shared state ' + name,
                   'abstract': 'Source on changing shared state.', 'publication_date': '2026-10-01'})
                   for name in ('existing', 'new1', 'new2')]
        self.store.put('papers', records[0])
        self.store.set('search_ledger', {'s': {'query': 'shared state', 'status': 'completed', 'metadata': records}})
        class Backend:
            name = 'selection-test'
            def generate(self, task):
                return BackendResult({'selection_summary': 'Read two sources relevant to the question.',
                    'selected': [{'paper_id': pid, 'reason': 'Directly addresses the question.',
                        'reading_question': 'What remains after the method works?',
                        'reading_role': 'method', 'route_ids': []} for pid in ('new1', 'new2')]})
        controller = Controller(self.store, Backend(), dict(DEFAULTS, max_papers=1,
            builtin_skills=False, fetch_full_text=False))
        candidate = {'id': 'question_test', 'proposal': {'problem': 'What remains?'}, 'retrieved_work_ids': []}
        with patch('research_idea.controller.enrich_screening_pool',
                   side_effect=lambda pool, **kw: (pool, {'attempted': 0, 'enriched': 0, 'pages': []})), \
             patch.object(controller, 'retrieve_full_texts', return_value=False) as retrieve:
            self.assertTrue(controller.select_search_results(['s'], 2, candidate, selection_phase='problem'))
        self.assertEqual({p['id'] for p in self.store.rows('papers')}, {'existing', 'new1', 'new2'})
        self.assertEqual(candidate['retrieved_work_ids'], ['new1', 'new2'])
        retrieve.assert_not_called()  # The caller saves selected IDs before downloading.
        self.assertEqual(self.store.rows('candidates'), [])
        self.assertIn('new1', controller.initial_paper_ids())


if __name__ == '__main__':
    unittest.main()
