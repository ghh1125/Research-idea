"""Explore a problem pool, develop each case, then hand all cases to selection.

These are reasoning tasks, not scientific acceptance tests. The controller only
checks identity, provenance and handoff completeness; no scores or vetoes.
"""
from __future__ import annotations

from copy import deepcopy
from .store import digest


def reconsider_after_reading(controller, pool, context, work):
    """One resumable reconsideration when focused reading supplied evidence."""
    if not any(entry and entry.get('readings') for entry in work):
        return pool
    from .controller import check_references
    previous_ids = {seed['id'] for seed in pool['problem_seeds']}
    def check(value):
        revised = value['pool']
        current_ids = {seed['id'] for seed in revised['problem_seeds']}
        if not current_ids or len(current_ids) != len(revised['problem_seeds']) or len(current_ids) > 4:
            raise ValueError('Keep one to four distinct research directions')
        check_references(value, {e['id'] for e in context['evidence']}, {p['id'] for p in context['papers']})
        routes = {r['id'] for r in context.get('discovery_plan', {}).get('research_routes', [])}
        for seed in revised['problem_seeds']:
            if not set(seed['research_route_ids']) <= routes:
                raise ValueError('Use supplied research routes')
        for change in value['changes']:
            if not set(change['previous_ids']) <= previous_ids or not set(change['current_ids']) <= current_ids:
                raise ValueError('Revision links must name the before and after directions')
    controller.progress('[analysis] 把新读到的材料带回构思：保留、重述或更换问题方向。')
    result = controller.task('reconsider_problems', {**context, 'previous_pool': pool,
        'reading_results': work}, check)
    record = {'before': deepcopy(pool), 'after': deepcopy(result['pool']), 'changes': result['changes']}
    journal = controller.store.get('problem_reconsiderations', {})
    journal[digest(record)] = record
    controller.store.set_many({'problem_reconsiderations': journal, 'problem_exploration': result['pool']})
    return result['pool']


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


def develop_problem_pool(controller, context, check_refs, pool=None):
    routes = {item['id'] for item in context.get('discovery_plan', {}).get('research_routes', [])}
    supplied_pool = pool is not None
    pool = pool or explore_problem_pool(controller, context, check_refs)
    cases = []
    responses = {}
    explanations = {}
    controller.store.set_many({'problem_response_analyses': responses, 'problem_cases': cases,
                              'problem_explanations': {}, 'problem_argument_revisions': {}})
    # Complete focused acquisition for every direction before comparing any,
    # so later candidates do not receive a systematically richer source set.
    if supplied_pool:
        from .discussion_sources import investigate_problem
        work = [investigate_problem(controller, seed) for seed in pool['problem_seeds']]
        context = controller.ideation_context()
        pool = reconsider_after_reading(controller, pool, context, work)
        from .controller import check_references
        check_refs = lambda value: check_references(value,
            {e['id'] for e in context['evidence']}, {p['id'] for p in context['papers']})
    for index, seed in enumerate(pool['problem_seeds'], 1):
        def check_case(value):
            check_refs(value)
            case = value['opportunity']
            if case['id'] != seed['id']:
                raise ValueError('Develop the assigned problem ID')
            if not set(case['research_route_ids']) <= routes:
                raise ValueError('Use supplied research route IDs')
            if any(not case[key].strip() for key in (
                    'question', 'derivation', 'bottleneck_hypothesis', 'why_it_matters',
                    'prior_art_delta', 'research_need')):
                raise ValueError('Explain the problem, its consequences, existing responses and motivation')
            if case['basis'] == 'source_observation' and not case['evidence_ids']:
                raise ValueError('Source observations must cite supplied evidence')

        controller.progress(f"[analysis] 深入问题 {index}/{len(pool['problem_seeds'])} · {seed['question']}")
        result = controller.task('deepen_problem', {
            **context, 'background_logic': pool['background_logic'],
            'cross_paper_synthesis': pool.get('cross_paper_synthesis', []),
            'approach_landscape': pool['approach_landscape'], 'problem_seed': deepcopy(seed), 'related_problem_seeds': deepcopy(pool['problem_seeds']),
        }, check_case)
        case = result['opportunity']
        responses[case['id']] = result['response_analysis']
        explanations[case['id']] = result.get('explanation_comparison', [])
        revisions = controller.store.get('problem_argument_revisions', {})
        revisions[case['id']] = {'before': deepcopy(seed), 'after': deepcopy(case),
                                'reason': result.get('revision_reason', '')}
        controller.store.set_many({'problem_explanations': dict(explanations),
                                  'problem_argument_revisions': revisions,
                                  'cross_paper_synthesis': pool.get('cross_paper_synthesis', [])})
        controller.store.set('problem_response_analyses', dict(responses))
        cases.append(case)
        controller.store.set('problem_cases', list(cases))
    return pool, cases
