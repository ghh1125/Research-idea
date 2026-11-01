"""Explicit question readings can reuse a source from an older design workflow."""
from pathlib import Path
import tempfile
import unittest
import json

from research_idea.config import DEFAULTS
from research_idea.controller import Controller, check_references
from research_idea.demo import DemoBackend
from research_idea.literature import normalize_paper
from research_idea.problem_dialogue import source_key
from research_idea.store import Store


class QuestionSourceContextTests(unittest.TestCase):
    def test_new_reading_request_supersedes_old_selection_and_keeps_paper_specific_questions(self):
        from research_idea.backend_types import BackendResult
        class Reader:
            name = 'source-test'
            def __init__(self):
                self.payloads = []
            def generate(self, task):
                data = json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
                self.payloads.append(data)
                quote = 'The update retains the observed state.'
                return BackendResult({'observations': [dict(statement='Updates retain the observed state.',
                    quote=quote, kind='author_claim', conditions='Specified update rule.', source_section='Algorithm 1')],
                    'reading_points': [dict(role='processing', text='The source specifies an update rule.',
                        information_type='paper_claim', observation_indices=['0'])]})
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp))
            try:
                for pid in ('a', 'b'):
                    paper = normalize_paper({'id': pid, 'title': pid, 'content_kind': 'full_text',
                        'text': 'Introduction\nBroad preference learning.\n\n' * 300 +
                        'Algorithm 1 UPDATE\nThe update retains the observed state.\n\nMore details.'})
                    paper['selection'] = {'phase': 'problem', 'reading_question': 'OLD question about motivation'}
                    store.put('papers', paper)
                backend = Reader()
                controller = Controller(store, backend, dict(DEFAULTS, builtin_skills=False, source_chars=1500))
                controller.phase = 'problem'
                candidate = {'proposal': {'title': 'current question', 'closest_work_ids': []},
                             'retrieved_work_ids': ['a', 'b']}
                requests = [{'paper_ids': [pid], 'question': f'核对 Algorithm 1 的更新规则，论文 {pid}',
                             'search_terms': ['broad preference']} for pid in ('a', 'b')]
                controller.focus_sources(candidate, ['a', 'b'], reading_question='Combined questions',
                                         acquisition_requests=requests)
                self.assertEqual([p['reading_question'] for p in backend.payloads], [r['question'] for r in requests])
                for payload in backend.payloads:
                    self.assertIn('The update retains the observed state.', payload['excerpt'])
                    self.assertTrue(payload['reading_selection']['section_context'][0]['explicitly_requested'])
                self.assertEqual(len(store.rows('evidence')), 2)
                self.assertEqual(len(store.get('source_understandings')), 2)
            finally:
                store.close()

    def test_reread_design_source_has_metadata_and_invalidates_when_its_text_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp))
            try:
                store.set('topic', '理解已有方法之后的重要问题')
                for paper_id in ('initial', 'reread-design', 'unrelated-design'):
                    store.put('papers', normalize_paper({
                        'id': paper_id, 'title': paper_id,
                        'text': 'The source explains how its method uses available information.',
                        'content_kind': 'full_text'}))
                store.set('initial_selection_paper_ids', ['initial'])
                store.set('design_paper_ids', ['reread-design', 'unrelated-design'])
                store.replace_evidence('reread-design', [{
                    'id': 'ev_question', 'paper_id': 'reread-design',
                    'statement': 'A source detail read for the current research question.',
                    'quote': 'The source explains how its method uses available information.',
                    'source_kind': 'full_text', 'extraction_stage': 'inspect_source'}])
                controller = Controller(store, DemoBackend(), dict(
                    DEFAULTS, backend='demo', builtin_skills=False, auto_search=False))
                before = controller.ideation_context()
                self.assertEqual([p['id'] for p in before['papers']], ['initial'])

                # Only this explicit question reading promotes the old source;
                # the unrelated legacy design corpus remains excluded.
                store.set('question_source_evidence', ['ev_question'])
                context = controller.ideation_context()
                self.assertEqual({p['id'] for p in context['papers']}, {'initial', 'reread-design'})
                self.assertEqual([e['id'] for e in context['evidence']], ['ev_question'])
                check_references({'closest_work_ids': ['reread-design'], 'evidence_ids': ['ev_question']},
                                 {e['id'] for e in context['evidence']},
                                 {p['id'] for p in context['papers']})
                key = source_key(controller)
                paper = next(p for p in store.rows('papers') if p['id'] == 'reread-design')
                paper['text'] += '\nThe source was corrected to describe a different condition.'
                store.put('papers', paper)
                self.assertNotEqual(source_key(controller), key)
            finally:
                store.close()


if __name__ == '__main__':
    unittest.main()
