"""Stateful research reasoning: new evidence, source lineage and discussion memory."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from research_idea.citation_discovery import reference_passages, target_requests, validate_targets
from research_idea.config import DEFAULTS
from research_idea.controller import Controller
from research_idea.conversation import append_message, memory_text
from research_idea.demo import DemoBackend
from research_idea.discussion_sources import investigate_problem, research_requests
from research_idea.local_skills import BUILTIN_ROOT, builtin_skill_paths, load_selected_skills, task_guidance
from research_idea.problem_dialogue import discuss
from research_idea.problem_discovery import reconsider_after_reading
from research_idea.reasoning_memory import reasoning_context, revised_reasoning
from research_idea.search_scope import config_scope
from research_idea.store import Store
from tests.test_discussion_sources import SourceController


def payload(task):
    return json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])


class RecordingDemo(DemoBackend):
    def __init__(self, hook=lambda task, output: None):
        self.calls, self.hook = [], hook

    def generate(self, task):
        self.calls.append(task)
        result = super().generate(task)
        self.hook(task, result.output)
        return result


class ReasoningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.addCleanup(self.store.close)
        self.store.set('topic', '怎样让工具反馈更有用')
        self.config = dict(DEFAULTS, backend='demo', auto_search=False, builtin_skills=False,
                           max_candidates=1, max_seconds=60, max_calls=80)

    def controller(self, backend=None):
        return Controller(self.store, backend or RecordingDemo(), self.config)

    def note(self, **changes):
        return dict(kind='analysis_revision', problem_id='conflict', user_quote='',
                    judgment='反馈可靠也可能不及时', reason='有效反馈到达前，决策已经改变',
                    revisit_when='读到可随时撤销决策的工作时重新考虑', evidence_ids=[], replaces=[], **changes)

    def test_synthesis_and_distinct_causes_reach_selection_and_final_brief(self):
        synthesis = dict(approach_names=['反馈'], shared_premise='反馈在决策前到达',
            achieved_progress='可以纠正已观察错误', changing_condition='决策先发生',
            possible_consequence='正确反馈不再改变原决策', paper_ids=[], evidence_ids=[])
        def hook(task, output):
            if task.stage == 'explore_problems':
                output['cross_paper_synthesis'] = [synthesis]
            if task.stage == 'deepen_problem':
                self.assertEqual(payload(task)['cross_paper_synthesis'], [synthesis])
                # A legitimate revision changes the origin; it must not trigger repair.
                output['opportunity']['problem_origin'] = 'emerging_problem'
                output['revision_reason'] = '更可靠但更慢的反馈暴露时机问题'
                output['explanation_comparison'][0]['explanation'] = payload(task)['problem_seed']['id']
        backend = RecordingDemo(hook)
        self.controller(backend).run_questions()
        mapping = next(payload(t) for t in backend.calls if t.stage == 'map')
        self.assertEqual(mapping['cross_paper_synthesis'], [synthesis])
        for key, values in mapping['explanation_comparisons'].items():
            self.assertEqual(values[0]['explanation'], key)
        framed = next(payload(t) for t in backend.calls if t.stage == 'frame_question')
        chosen = framed['argument_handoff'][0]
        self.assertEqual(chosen['cross_paper_synthesis'], [synthesis])
        self.assertEqual(chosen['explanations'][0]['explanation'], chosen['opportunity_id'])
        revisions = self.store.get('problem_argument_revisions')
        self.assertTrue(all(r['reason'] for r in revisions.values()))
        self.assertEqual(len([t for t in backend.calls if t.stage == 'deepen_problem']), 2)

    def test_new_reading_can_replace_direction_once_and_resume_cached(self):
        def hook(task, output):
            if task.stage == 'reconsider_problems':
                old = output['pool']['problem_seeds'][0]['id']
                output['pool']['problem_seeds'] = [dict(output['pool']['problem_seeds'][0],
                    id='new-direction', question='新条件下什么反馈仍有用？')]
                output['changes'] = [dict(previous_ids=[old], current_ids=['new-direction'],
                                         reason='已有回应解决了原猜测，重点转向变化条件', evidence_ids=[])]
        backend = RecordingDemo(hook)
        controller = self.controller(backend)
        controller.run_questions(interactive=True)
        pool = deepcopy(self.store.get('problem_checkpoint')['current'])
        work = [{'readings': [{'paper_id': 'synthetic', 'evidence_ids': []}]}]
        context = controller.ideation_context()
        first = reconsider_after_reading(controller, pool, context, work)
        second = reconsider_after_reading(controller, pool, context, work)
        self.assertEqual(first, second)
        self.assertEqual(first['problem_seeds'][0]['id'], 'new-direction')
        self.assertEqual(len([t for t in backend.calls if t.stage == 'reconsider_problems']), 1)
        journal = list(self.store.get('problem_reconsiderations').values())
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0]['before'], pool)
        self.assertEqual(journal[0]['after'], first)

    def test_metadata_only_does_not_trigger_reconsideration(self):
        backend = RecordingDemo()
        pool = {'problem_seeds': []}
        self.assertEqual(reconsider_after_reading(self.controller(backend), pool, {},
            [{'readings': [], 'search_status': 'completed'}]), pool)
        self.assertEqual(backend.calls, [])

    def test_reasoning_survives_long_dialogue_and_replacement_preserves_history(self):
        first = append_message(self.store, 'user', '为什么可靠反馈仍然没用？')
        update = self.note()
        update.update(kind='user_objection', user_quote=first['content'])
        notes = revised_reasoning(self.store, [update], first, {'checkpoint_id': 'cp'})
        self.store.set('reasoning_notes', notes)
        for index in range(30):
            append_message(self.store, 'user', f'其他讨论 {index}')
        self.assertEqual(self.controller().ideation_context()['reasoning_notes'], notes)
        later = append_message(self.store, 'user', '有可撤销的决策时重新讨论')
        replacement = self.note()
        replacement['replaces'] = [notes[0]['id']]
        revised = revised_reasoning(self.store, [replacement], later, {'checkpoint_id': 'cp2'})
        self.assertTrue(self.store.get('reasoning_notes')[0]['active'])  # prepare, not commit
        self.store.set('reasoning_notes', revised)
        self.assertFalse(revised[0]['active'])
        self.assertEqual(len(reasoning_context(self.store)), 1)
        self.assertEqual(revised[1]['origin'], 'assistant_analysis')
        self.assertIn(replacement['reason'], memory_text(self.store))
        self.store.set('topic', '另一个研究主题')
        self.assertEqual(reasoning_context(self.store), [])

    def test_objection_cannot_be_attributed_to_words_user_did_not_say(self):
        message = append_message(self.store, 'user', '为什么？')
        update = self.note()
        update.update(kind='user_objection', user_quote='我同意缩小范围')
        with self.assertRaisesRegex(ValueError, 'current message'):
            revised_reasoning(self.store, [update], message, {})
        self.assertIsNone(self.store.get('reasoning_notes'))

    def test_failed_followup_does_not_commit_provisional_reasoning(self):
        def hook(task, output):
            if task.stage == 'discuss_direction':
                data = payload(task)
                if data.get('source_work_done'):
                    raise RuntimeError('interrupted after reading')
                output['reasoning_updates'] = [self.note()]
                output['research_requests'] = [dict(question='反馈时间有何作用？',
                    query='feedback delay', paper_ids=[])]
        controller = self.controller(RecordingDemo(hook))
        controller.run_questions(interactive=True)
        message = append_message(self.store, 'user', '看看延迟反馈的工作')
        with patch('research_idea.discussion_sources.research_requests', return_value={'readings': []}):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                discuss(controller, message)
        self.assertIsNone(self.store.get('reasoning_notes'))
        self.assertIsNotNone(self.store.get('pending_discussion'))

    def test_successful_discussion_commits_reason_and_later_stage_receives_it(self):
        def hook(task, output):
            if task.stage == 'discuss_direction':
                output['reasoning_updates'] = [self.note()]
        backend = RecordingDemo(hook)
        controller = self.controller(backend)
        controller.run_questions(interactive=True)
        discuss(controller, append_message(self.store, 'user', '请考虑反馈时机'))
        self.assertEqual(len(reasoning_context(self.store)), 1)
        controller.run_questions(interactive=True, continue_problem=True)
        data = next(payload(t) for t in backend.calls if t.stage == 'deepen_problem')
        self.assertEqual(data['reasoning_notes'][0]['reason'], self.note()['reason'])

    def target(self):
        return dict(title='Reliable Feedback Systems', source_paper_id='source',
                    source_quote='Smith. Reliable Feedback Systems. 2021.', question='原作怎样处理反馈延迟？')

    def test_reference_passages_keep_exact_locations_and_total_budget(self):
        text = '1 Introduction\n' + 'Background. ' * 100 + '\n2 Related Work\n' + 'Other work. ' * 100 + '\nReferences\n' + self.target()['source_quote'] * 80
        papers = [dict(id=str(i), title=str(i), text=text, content_kind='full_text') for i in range(4)]
        passages = reference_passages(papers, budget=3000)
        self.assertTrue(passages)
        self.assertLessEqual(sum(len(s['text']) for p in passages for s in p['passages']), 3000)
        for paper in passages:
            for span in paper['passages']:
                self.assertEqual(span['text'], text[span['start']:span['end']])

    def test_reference_title_requires_own_source_quote(self):
        target = self.target()
        passages = [dict(paper_id='source', passages=[dict(text=target['source_quote'])])]
        validate_targets([target], passages)
        for changed in (dict(target, title='A Different Paper'), dict(target, source_paper_id='other')):
            with self.assertRaises(ValueError):
                validate_targets([changed], passages)

    def test_already_recalled_reference_reuses_search_and_reading_selection(self):
        controller = SourceController(self.store)
        self.store.set('search_ledger', {'existing': dict(status='completed', metadata=[
            dict(id='new1', title=self.target()['title'])])})
        requests = target_requests(controller, [self.target()])
        result = research_requests(controller, requests, key='citation')
        self.assertEqual(result['search_keys'], ['existing'])
        self.assertFalse(any(call[0] == 'search' for call in controller.calls))
        self.assertLessEqual(len(result['selected_ids']), 2)

    def test_missing_reference_uses_lineage_and_resumes_after_download_failure(self):
        controller = SourceController(self.store)
        target = self.target()
        self.store.put('papers', dict(id='source', title='Review', content_kind='full_text',
            text='References\n' + target['source_quote']))
        def plan(stage, data, checker, **kwargs):
            output = dict(reason='追踪原作', requests=[], citation_targets=[target])
            checker(output)
            return output
        controller.task = plan
        controller.fail_download = True
        with self.assertRaisesRegex(RuntimeError, 'download interrupted'):
            investigate_problem(controller, {'id': 'question'})
        controller.fail_download = False
        # The new selected papers must not change the saved requests on resume.
        result = investigate_problem(controller, {'id': 'question'})
        searches = [c for c in controller.calls if c[0] == 'search']
        self.assertEqual(len(searches), 1)
        self.assertEqual(searches[0][1], '"Reliable Feedback Systems"')
        self.assertEqual(searches[0][3], 'lineage')
        self.assertTrue(result['completed'])
        fixed = dict(DEFAULTS, search_date_mode='fixed', search_since='2023-01-01', search_until='2026-01-01')
        self.assertEqual(config_scope(fixed, 'lineage')['since'], '2023-01-01')

    def test_builtin_guidance_is_task_specific_and_explicit_local_text_stays_intact(self):
        skills = load_selected_skills(builtin_skill_paths(), self.root, [])
        deep = task_guidance(skills, 'deepen_problem', {})
        motivation = next(s for s in deep if s['name'] == 'research-idea-motivation')
        self.assertIn('LOADED REFERENCE: explanations.md', motivation['content'])
        self.assertNotIn('LOADED REFERENCE: discussion.md', motivation['content'])
        initial = task_guidance(skills, 'inspect_source', {'purpose': 'background_orientation'})
        self.assertFalse({'research-idea-audit-claims', 'research-idea-compare-methods'} & {s['name'] for s in initial})
        local = dict(name='research-idea-audit-claims', origin='local', content='My explicit guidance',
                     stages=['inspect_source'], sha256='x', path='/selected/SKILL.md')
        self.assertEqual(task_guidance([local], 'inspect_source', {'purpose': 'background_orientation'}), [local])

    def test_changed_reference_invalidates_related_task_without_loading_other_reference(self):
        builtins = self.root / 'builtins'
        shutil.copytree(BUILTIN_ROOT, builtins)
        with patch('research_idea.local_skills.BUILTIN_ROOT', builtins):
            before = load_selected_skills(builtin_skill_paths(), self.root, [])
            def fingerprint(skills, stage):
                return next(s['sha256'] for s in task_guidance(skills, stage, {})
                            if s['name'] == 'research-idea-motivation')
            path = builtins / 'research-idea-motivation/references/explanations.md'
            path.write_text(path.read_text(encoding='utf-8') + '\nDifferent explanations matter.\n', encoding='utf-8')
            after = load_selected_skills(builtin_skill_paths(), self.root, [])
            original = next(s for s in before if s['name'] == 'research-idea-motivation')
            updated = next(s for s in after if s['name'] == 'research-idea-motivation')
            self.assertNotEqual(original['sha256'], updated['sha256'])
            self.assertNotEqual(fingerprint(before, 'deepen_problem'), fingerprint(after, 'deepen_problem'))
            self.assertIn('Different explanations matter.', next(s['content'] for s in task_guidance(after, 'deepen_problem', {})
                if s['name'] == 'research-idea-motivation'))
            self.assertEqual(fingerprint(before, 'explore_problems'), fingerprint(after, 'explore_problems'))
            self.assertNotIn('reference_contents', task_guidance(after, 'deepen_problem', {})[0])


if __name__ == '__main__':
    unittest.main()
