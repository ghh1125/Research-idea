"""Explore a problem pool, develop each case, then hand all cases to selection.

These are reasoning tasks, not scientific acceptance tests. The controller only
checks identity, provenance and handoff completeness; no scores or vetoes.
"""
from __future__ import annotations

from copy import deepcopy
from .store import digest


def _check_analysis(value, seed, context):
    from .controller import check_references
    check_references(value, {e['id'] for e in context['evidence']},
                     {p['id'] for p in context['papers']})
    case = value['opportunity']
    if case['id'] != seed['id']:
        raise ValueError('Develop the assigned problem ID')
    routes = {r['id'] for r in context.get('discovery_plan', {}).get('research_routes', [])}
    if not set(case['research_route_ids']) <= routes:
        raise ValueError('Use supplied research routes')
    if any(not case[key].strip() for key in (
            'question', 'derivation', 'bottleneck_hypothesis', 'why_it_matters',
            'prior_art_delta', 'research_need')):
        raise ValueError('Explain the problem, its consequences, existing responses and motivation')
    if case['basis'] == 'source_observation' and not case['evidence_ids']:
        raise ValueError('Source observations must cite supplied evidence')


def reconsider_after_reading(controller, pool, context, work, analyses):
    """Revise affected arguments once; preserve the other analyses unchanged."""
    if not any(entry and entry.get('readings') for entry in work):
        return pool, analyses
    from .controller import check_references
    previous = {seed['id']: seed for seed in pool['problem_seeds']}
    original = {item['opportunity']['id']: item for item in analyses}
    def check(value):
        revised = value['pool']
        current = {seed['id']: seed for seed in revised['problem_seeds']}
        if not current or len(current) != len(revised['problem_seeds']) or len(current) > 4:
            raise ValueError('Keep one to four distinct research directions')
        check_references(value, {e['id'] for e in context['evidence']}, {p['id'] for p in context['papers']})
        routes = {r['id'] for r in context.get('discovery_plan', {}).get('research_routes', [])}
        for seed in revised['problem_seeds']:
            if not set(seed['research_route_ids']) <= routes:
                raise ValueError('Use supplied research routes')
        changed_before, changed_after = set(), set()
        for change in value['changes']:
            if not set(change['previous_ids']) <= previous.keys() or not set(change['current_ids']) <= current.keys():
                raise ValueError('Revision links must name the before and after directions')
            if not change['reason'].strip():
                raise ValueError('Explain why the reading changes the argument')
            changed_before.update(change['previous_ids'])
            changed_after.update(change['current_ids'])
        updates = value['case_updates']
        update_ids = {item['opportunity']['id'] for item in updates}
        if len(updates) != len(update_ids) or not update_ids <= current.keys():
            raise ValueError('Update each affected current problem at most once')
        required = {pid for pid, seed in current.items() if previous.get(pid) != seed}
        if not required <= update_ids or not changed_after <= update_ids:
            raise ValueError('Changed directions need complete updated analyses')
        if not update_ids <= changed_after or not previous.keys() - current.keys() <= changed_before:
            raise ValueError('Record the reasons for updated or removed problems')
        for item in updates:
            _check_analysis(item, current[item['opportunity']['id']], context)
    controller.progress('[analysis] 把新读到的材料带回构思：保留、重述或更换问题方向。')
    from .source_understanding import reading_result_view
    result = controller.task('reconsider_problems', {**context, 'previous_pool': pool,
        'problem_analyses': analyses,
        'reading_results': [reading_result_view(item) for item in work]}, check)
    updated = {item['opportunity']['id']: item for item in result['case_updates']}
    final = [deepcopy(updated.get(seed['id'], original.get(seed['id'])))
             for seed in result['pool']['problem_seeds']]
    record = {'before': deepcopy(pool), 'after': deepcopy(result['pool']), 'changes': result['changes'],
              'analyses_before': deepcopy(analyses), 'analyses_after': deepcopy(final)}
    journal = controller.store.get('problem_reconsiderations', {})
    journal[digest(record)] = record
    controller.store.set_many({'problem_reconsiderations': journal, 'problem_exploration': result['pool']})
    return result['pool'], final


def argument_handoff(problem):
    """Carry the selected causal argument into writing, in explanatory order.

    These are starting arguments, not frozen scientific conclusions. New source
    details can change them; an implementation difficulty is not a substitute
    for the research need that motivated the selected problem.
    """
    cases = {case['id']: case for case in problem.get('opportunities', [])}
    arguments = []
    for choice in problem.get('selected_problems', []):
        case = cases[choice['opportunity_id']]
        arguments.append({
            'opportunity_id': case['id'],
            'user_goal': problem.get('research_frame', {}).get('user_goal', ''),
            'question': case['question'],
            'research_intent': deepcopy(problem.get('research_intent')),
            'formulation': deepcopy(problem.get('formulation', [])),
            'steps': [{'role': role, 'text': case[field]} for role, field in (
                ('existing_response', 'prior_art_delta'),
                ('causal_insight', 'bottleneck_hypothesis'),
                ('derivation', 'derivation'),
                ('goal_impact', 'why_it_matters'),
                ('research_need', 'research_need')) if case.get(field)],
            'selection_reason': choice['selection_reason'],
            'evidence_ids': list(case.get('evidence_ids', [])),
            'closest_work_ids': list(case.get('closest_work_ids', [])),
            'explanations': deepcopy(problem.get('explanation_comparisons', {}).get(case['id'], [])),
            'cross_paper_synthesis': deepcopy(problem.get('cross_paper_synthesis', [])),
        })
    return arguments


def explore_problem_pool(controller, context, check_refs):
    routes = {item['id'] for item in context.get('discovery_plan', {}).get('research_routes', [])}

    def check_pool(value):
        check_refs(value)
        seeds = value['problem_seeds']
        if len(seeds) > 4 or len({s['id'] for s in seeds}) != len(seeds):
            raise ValueError('Use unique problem IDs within four directions')
        if not value['background_logic'].strip():
            raise ValueError('Connect the background goal and existing progress')
        for seed in seeds:
            if any(not seed[key].strip() for key in ('id', 'question', 'entry_reason')):
                raise ValueError('Describe each problem and its connection to the goal')
            if not set(seed['research_route_ids']) <= routes:
                raise ValueError('Use supplied research route IDs')
        for approach in value['approach_landscape']:
            if any(not approach[key].strip() for key in ('name', 'principle', 'achieved_progress')):
                raise ValueError('Explain the main approaches and their achieved progress')

    pool = controller.task('explore_problems', context, check_pool)
    controller.store.set_many({'problem_exploration': pool,
                              'cross_paper_synthesis': pool.get('cross_paper_synthesis', [])})
    return pool


def _development_work(controller, pool, context):
    """Freeze starting material across source acquisition and interrupted runs."""
    from .discussion_sources import _reading_scope
    from .prompts import stage_version
    store = controller.store
    checkpoint = store.get('problem_checkpoint') or {}
    key = digest(['argument-first-v1', pool, _reading_scope(controller),
        (store.get('question_cycle') or {}).get('created_at'),
        [checkpoint.get(k) for k in ('checkpoint_id', 'revision', 'confirmed_revision')],
        [context.get(k) for k in ('topic', 'user_notes', 'constraints', 'reasoning_notes')],
        [stage_version(stage) for stage in ('deepen_problem', 'plan_problem_reading', 'reconsider_problems')],
        getattr(controller, 'skill_key', ''),
        {k: controller.config.get(k) for k in ('backend', 'model', 'reasoning_effort', 'api_provider',
                                             'base_url', 'codex_bin', 'codex_profile')}])
    saved = store.get('problem_development') or {}
    if saved.get('key') != key:
        saved = {'key': key, 'context': deepcopy(context), 'initial': {}, 'readings': {}}
        store.set('problem_development', saved)
    return saved


def _publish_analyses(controller, pool, analyses, initial=None):
    initial = initial or {}
    seeds = {s['id']: s for s in pool['problem_seeds']}
    revisions = {}
    for item in analyses:
        case = item['opportunity']
        record = {'before': deepcopy(seeds[case['id']]), 'after': deepcopy(case),
                  'reason': item.get('revision_reason', '')}
        if case['id'] in initial and initial[case['id']] != item:
            record['initial_analysis'] = deepcopy(initial[case['id']])
        revisions[case['id']] = record
    controller.store.set_many({
        'problem_cases': [item['opportunity'] for item in analyses],
        'problem_response_analyses': {i['opportunity']['id']: i['response_analysis'] for i in analyses},
        'problem_explanations': {i['opportunity']['id']: i.get('explanation_comparison', []) for i in analyses},
        'problem_argument_revisions': revisions,
        'cross_paper_synthesis': pool.get('cross_paper_synthesis', []),
    })


def develop_problem_pool(controller, context, check_refs, pool=None):
    supplied_pool = pool is not None
    pool = pool or explore_problem_pool(controller, context, check_refs)
    work = _development_work(controller, pool, context) if supplied_pool else None
    context = work['context'] if work else context
    analyses = []
    # Give every candidate the same source snapshot before planning more reading.
    for index, seed in enumerate(pool['problem_seeds'], 1):
        result = work['initial'].get(seed['id']) if work else None
        if result is None:
            controller.progress(f"[analysis] 深入问题 {index}/{len(pool['problem_seeds'])} · {seed['question']}")
            result = controller.task('deepen_problem', {
                **context, 'background_logic': pool['background_logic'],
                'cross_paper_synthesis': pool.get('cross_paper_synthesis', []),
                'approach_landscape': pool['approach_landscape'], 'problem_seed': deepcopy(seed),
                'related_problem_seeds': deepcopy(pool['problem_seeds']),
            }, lambda value: _check_analysis(value, seed, context))
            if work is not None:
                work['initial'][seed['id']] = deepcopy(result)
                controller.store.set('problem_development', work)
        analyses.append(result)
        _publish_analyses(controller, pool, analyses)
    if work is not None:
        from .discussion_sources import investigate_problem
        for seed, analysis in zip(pool['problem_seeds'], analyses):
            if seed['id'] not in work['readings']:
                work['readings'][seed['id']] = investigate_problem(controller, seed, analysis=analysis)
                controller.store.set('problem_development', work)
        readings = [work['readings'][seed['id']] for seed in pool['problem_seeds']]
        if any(entry and entry.get('readings') for entry in readings):
            if 'revision_context' not in work:
                work['revision_context'] = controller.ideation_context()
                controller.store.set('problem_development', work)
            pool, analyses = reconsider_after_reading(controller, pool, work['revision_context'], readings, analyses)
        _publish_analyses(controller, pool, analyses, work['initial'])
    return pool, [item['opportunity'] for item in analyses]
