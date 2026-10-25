"""Explore a problem pool, develop each case, then hand all cases to selection.

These are reasoning tasks, not scientific acceptance tests. The controller only
checks identity, provenance and handoff completeness; no scores or vetoes.
"""
from __future__ import annotations

from copy import deepcopy


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
            'steps': [{'role': role, 'text': case[field]} for role, field in (
                ('existing_response', 'prior_art_delta'),
                ('causal_insight', 'bottleneck_hypothesis'),
                ('derivation', 'derivation'),
                ('goal_impact', 'why_it_matters'),
                ('research_need', 'research_need')) if case.get(field)],
            'selection_reason': choice['selection_reason'],
            'evidence_ids': list(case.get('evidence_ids', [])),
            'closest_work_ids': list(case.get('closest_work_ids', [])),
        })
    return arguments


def develop_problem_pool(controller, context, check_refs):
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
    controller.store.set('problem_exploration', pool)
    cases = []
    responses = {}
    controller.store.set('problem_response_analyses', responses)
    controller.store.set('problem_cases', cases)
    # Every direction gets the same neutral source context. Other cases and any
    # preferred candidate are deliberately absent, including on resume.
    for index, seed in enumerate(pool['problem_seeds'], 1):
        def check_case(value):
            check_refs(value)
            case = value['opportunity']
            if case['id'] != seed['id']:
                raise ValueError('Develop the assigned problem ID')
            if case['problem_origin'] != seed['problem_origin']:
                raise ValueError('Keep the assigned problem origin')
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
            'approach_landscape': pool['approach_landscape'], 'problem_seed': deepcopy(seed),
        }, check_case)
        case = result['opportunity']
        responses[case['id']] = result['response_analysis']
        controller.store.set('problem_response_analyses', dict(responses))
        cases.append(case)
        controller.store.set('problem_cases', list(cases))
    return pool, cases
