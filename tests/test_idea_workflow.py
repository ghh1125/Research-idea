"""Behavioral acceptance tests for a constructive, readable ideation workflow."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_idea.backend_types import BackendError, BackendResult
from research_idea.chat import Chat, fragments
from research_idea.config import DEFAULTS, write_config
from research_idea.controller import Controller, BudgetExhausted
from research_idea.demo import DemoBackend, DEMO_PAPERS
from research_idea.motivation import assess_motivation
from research_idea.presentation import activity_summary, idea_markdown, error_summary
from research_idea.prompts import stage_version
from research_idea.report import export_report
from research_idea.store import Store


class RecordingBackend(DemoBackend):
    def __init__(self, change=None):
        self.calls, self.change = [], change

    def generate(self, task):
        self.calls.append(task)
        result = super().generate(task)
        if self.change:
            self.change(task, result.output)
        return result


class IdeaWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        self.store = Store(self.project)
        self.store.set('topic', '如何设计帮助 agent 发现新规则的环境')
        self.config = dict(DEFAULTS, backend='demo', auto_search=False, builtin_skills=False,
                           max_candidates=1, max_rounds=2, max_seconds=60)
        write_config(self.project, self.config)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def run_flow(self, backend=None):
        backend = backend or RecordingBackend()
        Controller(self.store, backend, self.config).run()
        return self.store.rows('candidates')[0], backend

    def test_sparse_literature_still_delivers_a_hypothesis_and_real_method_plan(self):
        candidate, backend = self.run_flow()
        self.assertEqual(self.store.get('status'), 'completed')
        self.assertEqual(candidate['spec']['motivation']['basis'], 'research_hypothesis')
        self.assertEqual(candidate['spec']['motivation']['evidence_ids'], [])
        self.assertEqual(candidate['empirical_status'], 'untested')
        self.assertIn('refine', [task.stage for task in backend.calls])
        response = candidate['spec']['review_responses'][0]
        self.assertEqual(response['issue'], candidate['versions'][0]['review']['issues'][0]['issue'])
        self.assertEqual(response['decision'], 'adopt')
        self.assertIn(response['change'], candidate['spec']['method']['changes'])
        self.assertEqual([m['from'] for m in candidate['dialogue']], ['designer', 'reviewer', 'designer', 'reviewer'])
        reviews = [t for t in backend.calls if t.stage == 'review']
        second_review = json.loads(reviews[1].prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
        self.assertEqual(second_review['previous_review'], candidate['versions'][0]['review'])
        self.assertEqual(second_review['method_spec']['review_responses'][0]['issue'],
                         second_review['previous_review']['issues'][0]['issue'])
        self.assertIn('previous_revision_record', second_review)
        export_report(self.store, self.store.project)
        front = (self.project / self.store.get('output_folder') / 'report.md').read_text().split('<details>')[0]
        for label in ('Problem · 要解决的问题与原因', 'Motivation · 为什么需要这项研究', 'Idea · 基于动机提出核心想法', '参考路线'):
            self.assertIn(label, front)
        for label in ('第一步验证', '资源与规模', '值得继续的结果'):
            self.assertNotIn(label, front)
        self.assertIn('执行步骤', (self.project / self.store.get('output_folder') / (candidate['id'] + '.md')).read_text())
        for internal in ('prerequisites_unverified', 'motivation_unresolved', '待补证', 'blocked', 'pending'):
            self.assertNotIn(internal, front)
        self.assertTrue(candidate['spec']['validation']['first_test'])

    def test_observations_still_need_real_references_but_hypotheses_do_not(self):
        candidate, _ = self.run_flow()
        idea = copy.deepcopy(candidate['spec'])
        critique = candidate['review']
        assess_motivation(idea, critique, [])
        idea['motivation']['basis'] = 'source_observation'
        with self.assertRaisesRegex(ValueError, 'supporting evidence'):
            assess_motivation(idea, critique, [])
        idea['motivation']['basis'] = 'research_hypothesis'
        idea['motivation']['evidence_ids'] = ['fabricated']
        with self.assertRaisesRegex(ValueError, 'unknown evidence'):
            assess_motivation(idea, critique, [])

    def test_literature_directions_reach_ideation_and_selection_is_saved(self):
        candidate, backend = self.run_flow()
        problem = self.store.get('problem_model')
        self.assertGreater(len(problem['opportunities']), 1)
        proposal_task = next(task for task in backend.calls if task.stage == 'propose')
        payload = json.loads(proposal_task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
        self.assertEqual(payload['problem_model']['opportunities'], problem['opportunities'])
        self.assertEqual(payload['problem_model']['research_frame'], problem['research_frame'])
        self.assertEqual(problem['research_frame']['user_goal'], self.store.get('topic'))
        summary = activity_summary('map', problem)
        self.assertIn(problem['research_frame']['literature_logic'], summary)
        self.assertIn('把相关研究连起来看', summary)
        chosen = next(o for o in problem['opportunities'] if o['id'] == candidate['proposal']['opportunity_id'])
        self.assertEqual(set(problem['opportunity_types']), {'unresolved_need', 'emerging_problem'})
        self.assertIn(chosen['problem_origin'], problem['opportunity_types'])
        self.assertIn('问题来源', summary)
        self.assertTrue(chosen['derivation'])
        self.assertTrue(chosen['prior_art_delta'])
        self.assertTrue(candidate['proposal']['selection_reason'])
        export_report(self.store, self.store.project)
        saved = json.loads((self.project / self.store.get('output_folder') / 'report.json').read_text())
        self.assertEqual(saved['problem_model']['opportunities'], problem['opportunities'])
        self.assertEqual(saved['problem_model']['research_frame'], problem['research_frame'])
        self.assertEqual(sum(t.stage == 'map' for t in backend.calls), 1)
        self.assertEqual(sum(t.stage == 'propose' for t in backend.calls), 1)

    def test_both_problem_origins_produce_an_explained_idea_and_preserve_its_source(self):
        self.config['max_candidates'] = 2
        self.run_flow()
        candidates = self.store.rows('candidates')
        self.assertEqual(len(candidates), 2)
        self.assertEqual({c['proposal']['motivation']['problem_origin'] for c in candidates},
                         {'unresolved_need', 'emerging_problem'})
        opportunities = {item['id']: item for item in self.store.get('problem_model')['opportunities']}
        for candidate in candidates:
            with self.subTest(origin=candidate['proposal']['motivation']['problem_origin']):
                chosen = opportunities[candidate['proposal']['opportunity_id']]
                motive = candidate['proposal']['motivation']
                self.assertEqual(motive['problem_origin'], chosen['problem_origin'])
                self.assertTrue(motive['problem_derivation'].strip())
                self.assertEqual(candidate['selected_opportunity'],
                    {field: chosen[field] for field in
                     ('id', 'question', 'problem_origin', 'derivation', 'basis', 'prior_art_delta')})
                summary = activity_summary('propose', {'candidates': [candidate['proposal']]})
                self.assertIn(motive['problem_derivation'], summary)
                self.assertLess(summary.index(motive['problem_derivation']),
                                summary.index(motive['problem_observation']))

    def test_conditional_hypotheses_with_cited_premises_survive_both_origin_paths(self):
        from research_idea.literature import normalize_paper
        self.config['max_candidates'] = 2
        premise = 'A retriever returns passages with source identifiers and allows another retrieval request.'
        self.store.put('papers', normalize_paper({
            'id': 'conditional-premise', 'title': 'Synthetic retrieval capability premise',
            'content_kind': 'notes', 'source': 'synthetic_demo',
            'text': 'Synthetic fixture; not a real scientific paper.\n' + premise +
                    '\nNo observations of the proposed difficulties are reported.'}))
        derivations = {
            'unresolved_need': '如果来源的适用条件不同，回答时混用这些条件可能使已有信息无法被正确使用；这是由信息使用过程推导的假设，文献前提只说明系统能取得段落并继续检索。',
            'emerging_problem': '如果新旧来源的适用条件不一致，为扩大覆盖而持续追加来源可能增加条件混用；这是关于扩展后果的假设，材料并未报告这种困难。',
        }
        existing_response = '已有方法可以追加检索并取得新来源；需要分析何时这些正常操作足以澄清条件，何时追加内容仍保留相互冲突的适用条件。'
        def inject_hypotheses(task, output):
            if task.stage == 'extract':
                output['observations'] = [{'statement': premise, 'quote': premise, 'kind': 'author_claim',
                    'conditions': 'Synthetic description of an available operation, not a failure observation.',
                    'source_section': 'capability premise'}]
            elif task.stage == 'map':
                for direction in output['opportunities']:
                    direction.update(basis='research_hypothesis',
                        derivation=derivations[direction['problem_origin']], prior_art_delta=existing_response)
            elif task.stage == 'propose':
                for candidate in output['candidates']:
                    motive = candidate['motivation']
                    motive.update(basis='research_hypothesis',
                        problem_derivation=derivations[motive['problem_origin']],
                        existing_approach_limit=existing_response)
        _, backend = self.run_flow(RecordingBackend(inject_hypotheses))
        evidence = self.store.rows('evidence')
        self.assertTrue(evidence)
        self.assertEqual({item['kind'] for item in evidence}, {'author_claim'})
        self.assertEqual({item['quote'] for item in evidence}, {premise})
        directions = {item['id']: item for item in self.store.get('problem_model')['opportunities']}
        for task in backend.calls:
            payload = json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
            if task.stage == 'propose':
                for direction in payload['problem_model']['opportunities']:
                    self.assertEqual(direction['basis'], 'research_hypothesis')
                    self.assertTrue(direction['evidence_ids'])
                    self.assertEqual(direction['derivation'], derivations[direction['problem_origin']])
                    self.assertEqual(direction['prior_art_delta'], existing_response)
            elif task.stage in {'plan_search', 'develop', 'refine', 'review'}:
                selected = payload['selected_opportunity']
                original = directions[selected['id']]
                self.assertEqual(selected, {key: original[key] for key in
                    ('id', 'question', 'problem_origin', 'derivation', 'basis', 'prior_art_delta')})
                current = payload.get('method_spec') or payload.get('previous_spec') or payload['candidate']
                self.assertEqual(current['motivation']['basis'], 'research_hypothesis')
                self.assertTrue(current['motivation']['evidence_ids'])
        stages = [task.stage for task in backend.calls]
        self.assertEqual({stage: stages.count(stage) for stage in set(stages)},
                         {'extract': 1, 'map': 1, 'propose': 1, 'plan_search': 2,
                          'develop': 2, 'refine': 2, 'review': 4})
        export_report(self.store, self.store.project)
        target = self.project / self.store.get('output_folder')
        front = (target / 'report.md').read_text().split('<details>')[0]
        saved = json.loads((target / 'report.json').read_text())
        for candidate in saved['candidates']:
            motive = candidate['spec']['motivation']
            self.assertEqual(motive['basis'], 'research_hypothesis')
            self.assertEqual(motive['problem_derivation'], derivations[motive['problem_origin']])
            self.assertIn(motive['problem_derivation'], front)
            self.assertEqual(candidate['selected_opportunity']['basis'], 'research_hypothesis')
            self.assertEqual(candidate['selected_opportunity']['prior_art_delta'], existing_response)

    def test_four_field_problem_snapshot_resumes_without_extra_calls_and_exports(self):
        backend = RecordingBackend()
        with self.assertRaises(BudgetExhausted):
            Controller(self.store, backend, dict(self.config, max_calls=4)).run()
        candidate = self.store.rows('candidates')[0]
        legacy = {key: candidate['selected_opportunity'][key]
                  for key in ('id', 'question', 'problem_origin', 'derivation')}
        candidate['selected_opportunity'] = legacy
        self.store.put('candidates', candidate)
        before = len(backend.calls)
        Controller(self.store, backend, self.config).run()
        self.assertEqual([task.stage for task in backend.calls[before:]], ['review', 'refine', 'review'])
        for task in backend.calls[before:]:
            payload = json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
            self.assertEqual(payload['selected_opportunity'], legacy)
        export_report(self.store, self.store.project)
        target = self.project / self.store.get('output_folder')
        saved = json.loads((target / 'report.json').read_text())
        self.assertEqual(saved['status'], 'completed')
        self.assertEqual(saved['candidates'][0]['selected_opportunity'], legacy)
        self.assertIn(candidate['proposal']['title'], (target / 'report.md').read_text())

    def test_valid_but_mismatched_proposal_origin_is_repaired_once(self):
        attempts = []
        def mismatch_origin(task, output):
            if task.stage == 'propose':
                attempts.append(task)
                if len(attempts) == 1:
                    motive = output['candidates'][0]['motivation']
                    motive['problem_origin'] = ('emerging_problem' if motive['problem_origin'] == 'unresolved_need'
                                                else 'unresolved_need')
        candidate, backend = self.run_flow(RecordingBackend(mismatch_origin))
        self.assertEqual(len(attempts), 2)
        self.assertEqual(candidate['proposal']['motivation']['problem_origin'],
                         candidate['selected_opportunity']['problem_origin'])
        self.assertEqual(sum(task.stage == 'map' for task in backend.calls), 1)
        self.assertEqual(sum(task.stage == 'develop' for task in backend.calls), 1)

    def test_empty_problem_derivation_is_repaired_in_each_existing_design_step(self):
        attempts = {stage: [] for stage in ('propose', 'develop', 'refine')}
        def omit_first_derivation(task, output):
            if task.stage in attempts:
                attempts[task.stage].append(task)
                if len(attempts[task.stage]) == 1:
                    result = output['candidates'][0] if task.stage == 'propose' else output
                    result['motivation']['problem_derivation'] = ''
        candidate, backend = self.run_flow(RecordingBackend(omit_first_derivation))
        self.assertEqual({stage: len(calls) for stage, calls in attempts.items()},
                         {'propose': 2, 'develop': 2, 'refine': 2})
        self.assertTrue(candidate['proposal']['motivation']['problem_derivation'].strip())
        self.assertTrue(candidate['spec']['motivation']['problem_derivation'].strip())
        self.assertEqual(sum(task.stage == 'map' for task in backend.calls), 1)
        self.assertEqual(sum(task.stage == 'review' for task in backend.calls), 2)

    def test_selected_problem_snapshot_reaches_design_and_review(self):
        candidate, backend = self.run_flow()
        selected = candidate['selected_opportunity']
        stages = {'plan_search', 'develop', 'refine', 'review'}
        seen = set()
        for task in backend.calls:
            if task.stage in stages:
                payload = json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
                self.assertEqual(payload['selected_opportunity'], selected)
                seen.add(task.stage)
        self.assertEqual(seen, stages)
        export_report(self.store, self.store.project)
        saved = json.loads((self.project / self.store.get('output_folder') / 'report.json').read_text())
        self.assertEqual(saved['candidates'][0]['selected_opportunity'], selected)

    def test_reframed_problem_updates_the_report_while_preserving_the_selected_source(self):
        original = 'Original rationale: the background need motivates the selected unresolved problem.'
        revised = 'Revised rationale: using the existing approach exposes a new difficulty within that need.'
        updated_problem = 'Revised problem statement linked to the original research need.'
        def reframe(task, output):
            if task.stage == 'propose':
                output['candidates'][0]['motivation']['problem_derivation'] = original
            elif task.stage == 'refine':
                output['motivation'].update(problem_origin='emerging_problem',
                    problem_derivation=revised, problem_observation=updated_problem)
                output['review_responses'][0]['reason'] = revised
        candidate, _ = self.run_flow(RecordingBackend(reframe))
        self.assertEqual(candidate['selected_opportunity']['problem_origin'], 'unresolved_need')
        self.assertEqual(candidate['proposal']['motivation']['problem_derivation'], original)
        self.assertEqual(candidate['spec']['motivation']['problem_origin'], 'emerging_problem')
        chosen = next(item for item in self.store.get('problem_model')['opportunities']
                      if item['id'] == candidate['proposal']['opportunity_id'])
        self.assertEqual(candidate['selected_opportunity']['derivation'], chosen['derivation'])
        changed = {item['field'] for item in candidate['versions'][-1]['revision_record']['changed_fields']}
        self.assertTrue({'motivation.problem_origin', 'motivation.problem_derivation',
                         'motivation.problem_observation'} <= changed)
        export_report(self.store, self.store.project)
        front = (self.project / self.store.get('output_folder') / 'report.md').read_text().split('<details>')[0]
        self.assertIn(revised, front)
        self.assertNotIn(original, front)
        self.assertLess(front.index('Problem ·'), front.index(revised))
        self.assertLess(front.index(revised), front.index(updated_problem))
        self.assertLess(front.index(updated_problem), front.index('Motivation ·'))

    def test_legacy_saved_problem_without_origin_or_derivation_still_exports(self):
        candidate, _ = self.run_flow()
        candidate.pop('selected_opportunity')
        for record in (candidate['proposal'], candidate['spec'],
                       *(version['spec'] for version in candidate['versions'])):
            record['motivation'].pop('problem_origin', None)
            record['motivation'].pop('problem_derivation', None)
        self.store.put('candidates', candidate)
        summary = activity_summary('propose', {'candidates': [candidate['proposal']]})
        self.assertIn(candidate['proposal']['motivation']['problem_observation'], summary)
        export_report(self.store, self.store.project)
        target = self.project / self.store.get('output_folder')
        front = (target / 'report.md').read_text().split('<details>')[0]
        self.assertIn(candidate['spec']['motivation']['problem_observation'], front)
        saved = json.loads((target / 'report.json').read_text())['candidates'][0]
        self.assertNotIn('selected_opportunity', saved)
        for record in (saved['proposal'], saved['spec']):
            self.assertNotIn('problem_origin', record['motivation'])
            self.assertNotIn('problem_derivation', record['motivation'])

    def test_problem_source_is_limited_to_two_origins_and_repaired_in_existing_step(self):
        attempts = []
        def missing_comparison_is_not_a_problem_source(task, output):
            if task.stage == 'map':
                attempts.append(task)
                if len(attempts) == 1:
                    output['opportunities'][0]['problem_origin'] = 'untested_factor'
        candidate, backend = self.run_flow(RecordingBackend(missing_comparison_is_not_a_problem_source))
        self.assertEqual(len(attempts), 2)
        self.assertEqual(sum(t.stage == 'propose' for t in backend.calls), 1)
        origins = {o['problem_origin'] for o in self.store.get('problem_model')['opportunities']}
        self.assertEqual(origins, {'unresolved_need', 'emerging_problem'})
        self.assertTrue(candidate['proposal']['motivation']['research_need'])

    def test_problem_source_summary_matches_the_directions(self):
        attempts = []
        def omit_used_source(task, output):
            if task.stage == 'map':
                attempts.append(task)
                if len(attempts) == 1:
                    output['opportunity_types'] = ['unresolved_need']
        self.run_flow(RecordingBackend(omit_used_source))
        self.assertEqual(len(attempts), 2)
        self.assertIn('Problem origins must match', attempts[1].prompt)

    def test_unknown_origin_is_repaired_before_the_idea_is_presented(self):
        attempts = []
        def invalid_origin(task, output):
            if task.stage == 'propose':
                attempts.append(task)
                if len(attempts) == 1:
                    output['candidates'][0]['opportunity_id'] = 'invented-origin'
        candidate, _ = self.run_flow(RecordingBackend(invalid_origin))
        self.assertEqual(len(attempts), 2)
        self.assertIn(candidate['proposal']['opportunity_id'],
                      {item['id'] for item in self.store.get('problem_model')['opportunities']})

    def test_direction_evidence_must_exist_but_hypothesis_can_be_uncited(self):
        def fabricated_reference(task, output):
            if task.stage == 'map':
                output['opportunities'][0]['evidence_ids'] = ['invented-evidence']
        backend = RecordingBackend(fabricated_reference)
        with self.assertRaisesRegex(BackendError, 'Unknown evidence'):
            self.run_flow(backend)
        self.assertEqual([t.stage for t in backend.calls], ['map', 'map'])
        self.assertEqual(self.store.rows('candidates'), [])

    def test_idea_cannot_defer_named_closest_work_comparison_to_technical_design(self):
        from research_idea.literature import normalize_paper
        self.store.put('papers', normalize_paper(DEMO_PAPERS[0]))
        attempts = []
        def omit_first_comparison(task, output):
            if task.stage == 'propose':
                attempts.append(task)
                if len(attempts) == 1:
                    output['candidates'][0]['positioning'] = []
        candidate, backend = self.run_flow(RecordingBackend(omit_first_comparison))
        self.assertEqual(len(attempts), 2)
        self.assertIn('Compare each named closest work during ideation', attempts[1].prompt)
        self.assertEqual(set(candidate['proposal']['closest_work_ids']),
                         {p['paper_id'] for p in candidate['proposal']['positioning']})
        stages = [task.stage for task in backend.calls]
        self.assertLess(stages.index('propose'), stages.index('develop'))

    def test_idea_includes_a_working_path_before_detailed_design(self):
        attempts = []
        def omit_first_path(task, output):
            if task.stage == 'propose':
                attempts.append(task)
                if len(attempts) == 1:
                    output['candidates'][0]['feasibility_sketch']['available_path'] = ''
        candidate, _ = self.run_flow(RecordingBackend(omit_first_path))
        self.assertEqual(len(attempts), 2)
        sketch = candidate['proposal']['feasibility_sketch']
        self.assertTrue(sketch['inputs'])
        self.assertTrue(sketch['available_path'])
        self.assertTrue(sketch['first_check'])
        summary = activity_summary('propose', {'candidates': [candidate['proposal']]})
        self.assertNotIn(sketch['available_path'], summary)
        self.assertIn(sketch['key_assumption'], summary)
        self.assertIn('Idea → Method', summary)
        self.assertIn(candidate['proposal']['motivation']['background'], summary)

    def test_idea_repairs_an_empty_construction_path_in_the_existing_proposal_step(self):
        attempts = []
        def omit_first_construction(task, output):
            if task.stage == 'propose':
                attempts.append(task)
                if len(attempts) == 1:
                    output['candidates'][0]['idea_core']['construction_path'] = ''
        candidate, backend = self.run_flow(RecordingBackend(omit_first_construction))
        self.assertEqual(len(attempts), 2)
        self.assertTrue(candidate['proposal']['idea_core']['construction_path'].strip())
        self.assertEqual(sum(task.stage == 'map' for task in backend.calls), 1)
        self.assertEqual(sum(task.stage == 'develop' for task in backend.calls), 1)
        self.assertLess(backend.calls.index(attempts[1]),
                        next(i for i, task in enumerate(backend.calls) if task.stage == 'develop'))

    def test_concrete_idea_reaches_technical_design_and_the_readable_report(self):
        candidate, backend = self.run_flow()
        original = candidate['proposal']['idea_core']
        self.assertEqual(set(original), {'concrete_target', 'construction_path',
                                         'capability_bridge', 'essential_difference'})
        design_plan = next(task for task in backend.calls if task.stage == 'plan_search')
        develop = next(task for task in backend.calls if task.stage == 'develop')
        for task in (design_plan, develop):
            payload = json.loads(task.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
            self.assertEqual(payload['candidate']['idea_core'], original)
        summary = activity_summary('propose', {'candidates': [candidate['proposal']]})
        for passage in original.values():
            self.assertIn(passage, summary)
        export_report(self.store, self.store.project)
        target = self.project / self.store.get('output_folder')
        front = (target / 'report.md').read_text().split('<details>')[0]
        idea_part, _ = front.split('#### 第二部分 · Idea → Method', 1)
        for passage in candidate['spec']['idea_core'].values():
            self.assertIn(passage, idea_part)
        saved = json.loads((target / 'report.json').read_text())
        self.assertEqual(saved['candidates'][0]['spec']['idea_core'], candidate['spec']['idea_core'])

    def test_revised_idea_core_replaces_the_initial_core_and_is_tracked(self):
        fields = ('concrete_target', 'construction_path', 'capability_bridge', 'essential_difference')
        original = {field: 'Original idea passage: ' + field for field in fields}
        revised = {field: 'Revised idea passage: ' + field for field in fields}
        def revise_core(task, output):
            if task.stage == 'propose':
                output['candidates'][0]['idea_core'] = dict(original)
            elif task.stage == 'refine':
                output['idea_core'] = dict(revised)
        candidate, _ = self.run_flow(RecordingBackend(revise_core))
        self.assertEqual(candidate['proposal']['idea_core'], original)
        self.assertEqual(candidate['spec']['idea_core'], revised)
        rendered = idea_markdown(candidate)
        idea_part, _ = rendered.split('#### 第二部分 · Idea → Method', 1)
        for passage in revised.values():
            self.assertIn(passage, idea_part)
        for passage in original.values():
            self.assertNotIn(passage, rendered)
        changed = {item['field'] for item in candidate['versions'][-1]['revision_record']['changed_fields']}
        self.assertTrue({'idea_core.' + field for field in fields} <= changed)

    def test_legacy_saved_idea_without_core_still_exports_without_inventing_one(self):
        candidate, _ = self.run_flow()
        candidate['proposal'].pop('idea_core')
        candidate['spec'].pop('idea_core')
        for version in candidate['versions']:
            version['spec'].pop('idea_core', None)
        self.store.put('candidates', candidate)
        export_report(self.store, self.store.project)
        target = self.project / self.store.get('output_folder')
        front = (target / 'report.md').read_text().split('<details>')[0]
        self.assertIn(candidate['proposal']['title'], front)
        self.assertIn(candidate['spec']['motivation']['background'], front)
        self.assertIn('第二部分 · Idea → Method', front)
        saved = json.loads((target / 'report.json').read_text())['candidates'][0]
        self.assertNotIn('idea_core', saved['proposal'])
        self.assertNotIn('idea_core', saved['spec'])

    def test_refinement_must_answer_the_actual_objection_and_repair_is_bounded(self):
        def remove_response(task, output):
            if task.stage == 'refine':
                output['review_responses'] = []
        backend = RecordingBackend(remove_response)
        with self.assertRaisesRegex(BackendError, 'Respond once'):
            self.run_flow(backend)
        self.assertEqual(sum(t.stage == 'refine' for t in backend.calls), 2)
        # The previously useful idea survives a malformed revision.
        self.assertTrue(self.store.rows('candidates')[0]['spec']['validation']['first_test'])

    def test_technical_design_repairs_a_route_without_a_reason_before_review(self):
        attempts = []
        def omit_first_rationale(task, output):
            if task.stage == 'develop':
                attempts.append(task)
                if len(attempts) == 1:
                    output['design_decisions'][0]['rationale'] = ''
        candidate, backend = self.run_flow(RecordingBackend(omit_first_rationale))
        self.assertEqual(len(attempts), 2)
        self.assertIn('design choices with rationale', attempts[1].prompt)
        self.assertTrue(candidate['spec']['design_decisions'][0]['rationale'])
        review = next(t for t in backend.calls if t.stage == 'review')
        payload = json.loads(review.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
        self.assertTrue(payload['method_spec']['design_decisions'][0]['rationale'])

    def test_technical_reference_completes_without_an_experiment_plan(self):
        def omit_plan(task, output):
            if task.stage in {'develop', 'refine'}:
                output['validation'] = {key: [] if isinstance(value, list) else ''
                                        for key, value in output['validation'].items()}
                for choice in output['design_decisions']:
                    choice['first_test'] = ''
        candidate, backend = self.run_flow(RecordingBackend(omit_plan))
        self.assertTrue(candidate['development_complete'])
        self.assertEqual(candidate['spec']['validation']['first_test'], '')
        self.assertEqual(sum(t.stage == 'develop' for t in backend.calls), 1)
        self.assertEqual(sum(t.stage == 'refine' for t in backend.calls), 1)
        self.assertTrue(candidate['spec']['feasibility']['required_signals'])
        export_report(self.store, self.store.project)
        front = (self.project / self.store.get('output_folder') / 'report.md').read_text().split('<details>')[0]
        self.assertIn('技术参考', front)
        self.assertNotIn('第一步验证', front)
        self.assertNotIn('完整首测', front)

    def test_report_uses_current_intervention_after_reframing_and_keeps_phase_boundary(self):
        candidate, _ = self.run_flow()
        candidate['proposal']['intervention'] = 'Abandoned intervention from the original idea'
        candidate['spec']['method']['summary'] = ''
        candidate['spec']['method']['changes'] = ['Current mechanism after review']
        rendered = idea_markdown(candidate)
        self.assertIn('Current mechanism after review', rendered)
        self.assertNotIn('Abandoned intervention', rendered)
        idea_part, method_part = rendered.split('#### 第二部分 · Idea → Method', 1)
        self.assertNotIn('Current mechanism after review', idea_part)
        self.assertIn('Current mechanism after review', method_part)
        for heading in ('Problem · 要解决的问题与原因', 'Motivation · 为什么需要这项研究', 'Idea · 基于动机提出核心想法'):
            self.assertIn(heading, idea_part)
            self.assertNotIn(heading, method_part)
        candidate['spec'] = {}
        rendered = idea_markdown(candidate)
        self.assertIn(candidate['proposal']['intervention'], rendered)
        self.assertNotIn('第一项值得做的实验', rendered)
        self.assertNotIn(candidate['proposal']['feasibility_sketch']['available_path'], rendered)

    def test_discussion_notes_reach_the_designer_and_invalidate_old_proposals(self):
        first, backend = self.run_flow()
        before = len(backend.calls)
        self.store.set('chat_messages', [{'role': 'user', 'content': '方法可以沿用，重点是环境如何提供可区分的观察。'},
                                         {'role': 'assistant', 'content': 'Do not treat this answer as a user decision.'}])
        self.run_flow(backend)
        proposal = next(t for t in backend.calls[before:] if t.stage == 'propose')
        payload = json.loads(proposal.prompt.split('BEGIN_RESEARCH_DATA\n')[1].split('\nEND_RESEARCH_DATA')[0])
        self.assertEqual(payload['user_notes'], ['方法可以沿用，重点是环境如何提供可区分的观察。'])

    def test_missing_resources_request_redesign_instead_of_dropping_the_idea(self):
        def unavailable(task, output):
            if task.stage == 'develop':
                output['feasibility']['required_signals'][0]['availability'] = 'unavailable'
            if task.stage == 'review':
                output.update(verdict='continue', issues=[], revision_instructions='')
        candidate, backend = self.run_flow(RecordingBackend(unavailable))
        self.assertIn('refine', [t.stage for t in backend.calls])
        self.assertEqual(candidate['development_complete'], True)
        self.assertEqual(candidate['spec']['feasibility']['required_signals'][0]['availability'], 'unverified')
        self.assertTrue(candidate['spec']['method']['changes'])

    def test_readable_findings_and_narrow_terminal_preserve_navigation_and_budget(self):
        candidate, _ = self.run_flow()
        text = activity_summary('develop', candidate['spec'])
        self.assertIn('针对本场景的改造', text)
        self.assertNotIn('第一步验证', text)
        self.assertNotIn('required_signals', text)
        chat = Chat(self.project)
        from prompt_toolkit.utils import get_cwidth
        with patch('research_idea.chat.shutil.get_terminal_size', return_value=__import__('os').terminal_size((52, 24))):
            lines = ''.join(value for _, value in chat.toolbar()).splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(all(get_cwidth(line) <= 52 for line in lines))
        self.assertIn('调用', lines[1])
        self.assertIn('/intro', lines[2])
        rendered = ''.join(value for _, value in fragments('idea', idea_markdown(candidate)))
        self.assertNotIn('**', rendered)
        self.assertIn('参考路线', rendered)

    def test_argument_is_ordered_and_old_saved_ideas_still_render(self):
        candidate, _ = self.run_flow()
        motive = candidate['spec']['motivation']
        fields = ('background', 'existing_work', 'problem_observation', 'importance',
                  'causal_explanation', 'existing_approach_limit', 'research_need',
                  'why_this_method', 'expected_progress')
        for index, field in enumerate(fields):
            motive[field] = f'Unique argument passage {index}.'
        rendered = idea_markdown(candidate)
        positions = [rendered.index(motive[field]) for field in fields]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(positions[-1], rendered.index('第二部分'))
        for axis in candidate['spec']['design_axes']:
            self.assertLess(rendered.index(axis['required_function']), rendered.index('可借鉴的技术'))
        del motive['existing_work'], motive['research_need']
        del candidate['spec']['design_axes']
        candidate.pop('design_search_plan', None)
        legacy = idea_markdown(candidate)
        self.assertIn(motive['background'], legacy)
        self.assertNotIn('Unique argument passage 6.', legacy)

    def test_ideation_update_reuses_unchanged_reader_version(self):
        self.assertEqual(stage_version('read_section'), '8')
        self.assertNotEqual(stage_version('develop'), stage_version('read_section'))

    def test_budget_before_review_keeps_method_and_resume_does_not_regenerate_it(self):
        backend = RecordingBackend()
        with self.assertRaises(BudgetExhausted):
            Controller(self.store, backend, dict(self.config, max_calls=4)).run()
        self.assertTrue(self.store.rows('candidates')[0]['spec']['method']['changes'])
        export_report(self.store, self.store.project)
        self.assertIn('参考路线', (self.project / self.store.get('output_folder') / 'report.md').read_text())
        Controller(self.store, backend, self.config).run()
        self.assertEqual(sum(t.stage == 'develop' for t in backend.calls), 1)
        self.assertEqual(self.store.get('status'), 'completed')

    def test_timeout_explains_the_setting_and_resume_action(self):
        message = error_summary(BackendError('/private/model exceeded the 599.9s task timeout'))
        self.assertIn('10.0 分钟', message)
        self.assertIn('/budget timeout_s', message)
        self.assertIn('/run', message)
        self.assertNotIn('/private/model', message)

    def test_resume_keeps_design_sources_out_of_first_round_full_reading(self):
        class DesignBackend(RecordingBackend):
            def generate(self, task):
                if task.stage in {'inspect_source', 'design_transfer'}:
                    self.calls.append(task)
                    return BackendResult({'observations': []} if task.stage == 'inspect_source' else
                                         {'paper_id': 'new-technique', 'options': [], 'reading_gaps': []})
                return super().generate(task)
        backend = DesignBackend()
        first = Controller(self.store, backend, self.config)
        def pause_search(candidate):
            self.store.put('papers', {'id': 'new-technique', 'title': 'A synthetic technical source',
                                      'content_kind': 'full_text', 'text': 'Method details for a focused design question.'})
            candidate['retrieved_work_ids'] = ['new-technique']
            self.store.put('candidates', candidate)
            raise BudgetExhausted('Paused in technical exploration')
        first.search_for_candidate = pause_search
        with self.assertRaises(BudgetExhausted):
            first.run()
        self.assertEqual(self.store.get('cohort')['initial_paper_ids'], [])
        self.assertNotIn('spec', self.store.rows('candidates')[0])
        resumed = Controller(self.store, backend, self.config)
        with patch.object(resumed, 'read_papers', wraps=resumed.read_papers) as read:
            resumed.run()
        read.assert_called_once_with([])
        stages = [t.stage for t in backend.calls]
        self.assertEqual(stages.count('propose'), 1)
        self.assertNotIn('paper_card', stages)
        self.assertNotIn('extract', stages)
        self.assertIn('design_transfer', stages)
        self.assertEqual(self.store.get('status'), 'completed')
