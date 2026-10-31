"""Durable pause between problem discovery and idea construction."""
from copy import deepcopy

from .conversation import MEMORY_INSTRUCTIONS, memory_context, revised_memory, finish_turn, supplied_user_ids, bind_discussion_memory
from .store import digest, now

WAITING = 'awaiting_problem_discussion'
WAITING_BY_KIND = {'direction': 'awaiting_direction_discussion', 'problem': WAITING}
DISCUSSION_INSTRUCTIONS = """
研究停在问题讨论阶段，尚未提出 idea。围绕用户本轮消息，结合当前问题、已有方法和原文资料进行讨论。
先直接解释用户困惑的地方：到底什么事情做不到，为什么重要，现有方法正常发挥以后为什么仍可能留下它。
支持纠正原因、重新选择问题、提出新切口。只问问题不代表用户同意你的建议；保留其他候选的原论证。
合理猜想可以大胆推进，区分来源报告和推演。不能把“让模型准确判断/发现问题”当作解决难点的理由。
不要在此展开技术方案、实验计划或宣称检索已完成。引用事实使用提供的论文和 evidence IDs。
updated_problems 仅给出需要改动或新增的问题完整记录，未改动的留在原处；selected_problems
仅在实际调整重点时填写完整选择及理由，否则 []。追问需要解释时可以只答复，两者均为 []。
当前 problem_model 是正在讨论的工作版本，不代表用户已认可。你可以根据本轮讨论主动修改问题和
优先建议，无须用户逐字段批准；/continue 才会按当前版本推进。如果本轮分析改变了对原因或优先级的判断，
同步返回 updated_problems 或 selected_problems，不能只在 answer 口头否定旧论证、让后续仍沿用它。
answer 说明改了哪里、为什么，把自己的推荐标为当前建议，不伪装为用户已经选择。只解释而判断未变时可不改记录。
程序只在用户输入 /continue 后往下运行；普通对话即便提到“继续”也保持讨论状态。
""" + MEMORY_INSTRUCTIONS


def source_key(controller):
    ids = set(controller.initial_paper_ids())
    question_refs = set(controller.store.get('question_source_evidence', []))
    ids.update(e['paper_id'] for e in controller.store.rows('evidence') if e['id'] in question_refs)
    # Model/account changes do not erase the human's problem choice. Source or
    # scope changes do require updating the problem discussion on the new basis.
    return digest([controller.store.get('source_revision', 0), controller.store.get('topic'), controller.config['constraints'],
        controller.config['max_candidates'],
        {k: controller.config.get(k) for k in ('search_source', 'search_venues', 'max_papers',
            'search_date_mode', 'search_since', 'search_until', 'strategy_months', 'novelty_months',
            'conference_policy', 'search_cs_only', 'arxiv_categories', 'deep_reading',
            'source_chars', 'max_paper_read_chunks', 'max_followup_reads')},
        [{k: p.get(k) for k in ('id', 'text', 'abstract', 'content_kind')} for p in controller.store.rows('papers') if p['id'] in ids]])


def open_checkpoint(controller, problem, kind='problem'):
    store = controller.store
    old = store.get('problem_checkpoint')
    if old:
        store.event('problem_checkpoint_archived', old)
    history = store.get('discussion_checkpoints', [])
    if old:
        history.append(deepcopy(old))
    created = now()
    checkpoint = dict(research_intent=deepcopy(store.get('research_intent')), kind=kind, checkpoint_id=digest([kind, created, problem, len(history)])[:20],
        state='discussing', revision=1, source_key=source_key(controller),
        original=deepcopy(problem), current=deepcopy(problem), revisions=[], created_at=now(),
        confirmed_revision=None, user_notes_at_open=controller.user_notes())
    store.set_many({'conversation_memory': bind_discussion_memory(store),
                    'discussion_checkpoints': history, 'problem_checkpoint': checkpoint,
                    'status': WAITING_BY_KIND[kind]})
    return checkpoint


def problem_text(store, detail=False):
    checkpoint = store.get('problem_checkpoint') or {}
    problem = checkpoint.get('current', {})
    if not problem:
        return '还没有调研后的候选问题。输入 /run 开始。'
    if checkpoint.get('kind') == 'direction':
        return direction_text(store, problem, detail=detail)
    from .citations import Citations
    citations = Citations.from_store(store)
    lines = ['## 调研后的问题 · 先讨论，再构思', '',
             '**背景：** ' + problem.get('research_frame', {}).get('literature_logic', '')]
    for route in problem.get('approach_landscape', []):
        lines += ['', '**现有方法 · ' + route['name'] + '**', route['principle'], route['achieved_progress']]
    chosen = {c['opportunity_id']: c['selection_reason'] for c in problem.get('selected_problems', [])}
    for i, case in enumerate(problem.get('opportunities', []), 1):
        lines += ['', f"### 问题 {i}：{case['question']}"]
        for field, label in [('prior_art_delta', '现有办法已经做了什么，为什么还会遇到困难'),
                             ('bottleneck_hypothesis', '我们对原因的判断'), ('derivation', '怎样影响原目标'),
                             ('why_it_matters', '为什么值得研究'), ('research_need', '由此需要推进什么')]:
            if detail or field in {'prior_art_delta', 'why_it_matters', 'research_need'}:
                lines += ['', f'**{label}：** ' + (case[field] if detail else concise(case[field]))]
        if case.get('closest_work_ids'):
            lines += ['', '**相关论文：** ' + '；'.join(citations.paper(pid) for pid in case['closest_work_ids'])]
        if case['id'] in chosen:
            lines += ['', '**优先考虑这个问题的理由：** ' + chosen[case['id']]]
        if detail:
            for explanation in problem.get('explanation_comparisons', {}).get(case['id'], []):
                lines += ['', '**考虑过的原因：** ' + explanation['explanation'],
                          explanation['how_it_arises'],
                          '**已有回应：** ' + explanation['strongest_response'],
                          '**仍值得追问：** ' + explanation['remaining_obstacle'],
                          '**对研究重点的影响：** ' + explanation['implication']]
    lines += ['', '直接输入你的意见，可以追问、纠正或换一个问题。输入 /continue 后，按当前讨论结果整理动机与研究主张。/problems detail 查看完整推导。']
    return citations.text('\n'.join(lines), compact=not detail)


def _discuss_legacy(controller, message):
    from .controller import check_references
    store = controller.store
    checkpoint = store.get('problem_checkpoint')
    context = controller.ideation_context()
    memory = memory_context(store, message['content'])
    supplied = supplied_user_ids(memory)

    def revise(value):
        check_references(value, {e['id'] for e in context['evidence']}, {p['id'] for p in context['papers']})
        revised_memory(store, value['memory_updates'], supplied)
        working = deepcopy(checkpoint['current'])
        if not value['updated_problems'] and not value['selected_problems']:
            return working
        cases = {p['id']: p for p in working['opportunities']}
        updates = value['updated_problems']
        if len({p['id'] for p in updates}) != len(updates):
            raise ValueError('Update each problem once')
        routes = {r['id'] for r in context.get('discovery_plan', {}).get('research_routes', [])}
        for item in updates:
            if any(not item[k].strip() for k in ('id', 'question', 'prior_art_delta', 'bottleneck_hypothesis',
                    'derivation', 'why_it_matters', 'research_need')):
                raise ValueError('Explain the revised problem and why it matters')
            if not set(item['research_route_ids']) <= routes:
                raise ValueError('Use actual discovery route IDs')
            if item['basis'] == 'source_observation' and not item['evidence_ids']:
                raise ValueError('Observed problems need source evidence; inferred problems are hypotheses')
            cases[item['id']] = deepcopy(item)
        choices = value['selected_problems'] or working['selected_problems']
        ids = [c['opportunity_id'] for c in choices]
        if len(set(ids)) != len(ids) or not set(ids) <= set(cases) or len(ids) > controller.config['max_candidates']:
            raise ValueError('Choose existing problems within max_candidates')
        if not choices or any(not c['selection_reason'].strip() for c in choices):
            raise ValueError('Explain the current problem choice')
        working.update(opportunities=list(cases.values()), selected_problems=deepcopy(choices))
        working['problem'] = '；'.join(cases[c]['question'] for c in ids)
        working['research_frame']['research_question'] = working['problem']
        working['opportunity_types'] = list(dict.fromkeys(c['problem_origin'] for c in cases.values()))
        # Comparisons predate the dialogue; do not present them as re-evaluated.
        working['problem_comparisons'] = []
        return working

    result = controller.task('discuss_problem', {**context, **memory,
        'problem_model': checkpoint['current'], 'current_user_message': message}, revise, publish=False)
    working = revise(result)
    checkpoint = deepcopy(checkpoint)
    checkpoint['revision'] += 1
    checkpoint['current'] = working
    checkpoint['revisions'].append(dict(revision=checkpoint['revision'], source_message_id=message['id'],
        answer=result['answer'], updated_problems=result['updated_problems'],
        selected_problems=result['selected_problems'], time=now()))
    checkpoint['state'] = 'discussing'
    finish_turn(store, result, supplied, model=controller.config['model'],
        reasoning_effort=controller.config['reasoning_effort'],
        problem_checkpoint=checkpoint, problem_model=working, status=WAITING)
    return result['answer']


def concise(text, limit=420):
    if len(text) <= limit:
        return text
    end = max(text.rfind('。', 0, limit), text.rfind('；', 0, limit))
    return text[:end + 1] if end > limit // 2 else text[:limit] + '…'


def direction_text(store, pool, detail=False):
    from .citations import Citations
    citations = Citations.from_store(store)
    lines = ['## 方向讨论 · 先看看哪些问题值得深入', '', '**背景：** ' + pool['background_logic']]
    for route in pool['approach_landscape']:
        lines += ['', '**现有思路 · ' + route['name'] + '**', route['principle'], route['achieved_progress']]
    if detail:
        for synthesis in pool.get('cross_paper_synthesis', []):
            lines += ['', '**把这些研究连起来看：** ' + synthesis['achieved_progress'],
                      '**共同依赖的条件：** ' + synthesis['shared_premise'],
                      '**条件如何变化：** ' + synthesis['changing_condition'],
                      '**由此可能发生什么：** ' + synthesis['possible_consequence']]
    for seed in pool['problem_seeds']:
        lines += ['', '### ' + seed['id'] + ' · ' + seed['question'], '', seed['entry_reason']]
    lines += ['', '可以纠正背景、补充你关心的困难，或调整要深入的方向。/continue 后逐个深入比较这些问题。']
    return citations.text('\n'.join(lines), compact=not detail)


def apply_discussion(controller, checkpoint, result, context):
    """Update a working version, never infer agreement from a user's question."""
    from .controller import check_references
    from .discussion_sources import validate_requests
    check_references(result, {e['id'] for e in context['evidence']}, {p['id'] for p in context['papers']})
    validate_requests(result['research_requests'], {p['id'] for p in context['papers']})
    routes = {r['id'] for r in context.get('discovery_plan', {}).get('research_routes', [])}
    working = deepcopy(checkpoint['current'])
    if checkpoint.get('kind') == 'direction':
        if len(result['updated_pool']) > 1:
            raise ValueError('Return zero or one revised direction pool')
        if result['updated_pool']:
            working = deepcopy(result['updated_pool'][0])
        cases = working['problem_seeds']
        if not cases or len(cases) > 4 or len({c['id'] for c in cases}) != len(cases):
            raise ValueError('Keep one to four distinct research directions')
        for case in cases:
            if not all(case[k].strip() for k in ('id', 'question', 'entry_reason')):
                raise ValueError('Explain each direction and its connection to the goal')
            if not set(case['research_route_ids']) <= routes:
                raise ValueError('Use actual research route IDs')
    else:
        background = result['updated_background']
        if len(background) > 1:
            raise ValueError('Return zero or one revised background and approach landscape')
        if background:
            frame = deepcopy(background[0]['research_frame'])
            if any(not text.strip() for text in frame.values()):
                raise ValueError('Connect the updated background, question and research scope')
            frame['user_goal'] = controller.store.get('topic') or ''
            working.update(research_frame=frame,
                           approach_landscape=deepcopy(background[0]['approach_landscape']))
        if not result['updated_problems'] and not result['selected_problems'] and not background:
            return working
        cases = {c['id']: c for c in working['opportunities']}
        updates = result['updated_problems']
        if len({p['id'] for p in updates}) != len(updates):
            raise ValueError('Update each problem once')
        for item in updates:
            if not all(item[k].strip() for k in ('id', 'question', 'prior_art_delta', 'derivation',
                                               'bottleneck_hypothesis', 'why_it_matters', 'research_need')):
                raise ValueError('Explain the revised question and its research value')
            if not set(item['research_route_ids']) <= routes:
                raise ValueError('Use actual research route IDs')
            if item['basis'] == 'source_observation' and not item['evidence_ids']:
                raise ValueError('Observed problems need source evidence; inferred problems are hypotheses')
            cases[item['id']] = deepcopy(item)
        choices = result['selected_problems'] or working['selected_problems']
        ids = [c['opportunity_id'] for c in choices]
        if not ids or len(ids) > controller.config['max_candidates'] or len(set(ids)) != len(ids) or not set(ids) <= cases.keys():
            raise ValueError('Choose existing problems within max_candidates')
        if any(not c['selection_reason'].strip() for c in choices):
            raise ValueError('Explain the research priority')
        working.update(opportunities=list(cases.values()), selected_problems=deepcopy(choices))
        working['problem'] = '；'.join(cases[i]['question'] for i in ids)
        working['research_frame']['research_question'] = working['problem']
        working['opportunity_types'] = list(dict.fromkeys(c['problem_origin'] for c in cases.values()))
        if updates or result['selected_problems'] or background:
            working['problem_comparisons'] = []
            working['formulation'] = []
    return working


def discuss(controller, message):
    from .reasoning_memory import revised_reasoning
    from .research_intent import revised_intent
    store = controller.store
    checkpoint = deepcopy(store.get('problem_checkpoint'))
    if store.get('workflow') != 'question':
        return _discuss_legacy(controller, message)
    if checkpoint.get('source_key') != source_key(controller):
        raise ValueError('论文或研究范围已变化，请 /run 更新讨论。原话与研究要点已保存。')
    kind = checkpoint.get('kind', 'problem')
    stage = 'discuss_direction' if kind == 'direction' else 'discuss_question'
    memory = memory_context(store, message['content'])
    supplied = supplied_user_ids(memory)
    context = controller.ideation_context()
    pending = store.get('pending_discussion') or {}
    token = digest([checkpoint['checkpoint_id'], checkpoint['revision'], message['id']]) if checkpoint.get('checkpoint_id') else digest([checkpoint, message['id']])
    def checked(value):
        revised_intent(controller, value, message)
        apply_discussion(controller, checkpoint, value, context)
        revised_reasoning(store, value.get('reasoning_updates', []), message, checkpoint)
        revised_memory(store, value['memory_updates'], supplied)
    if pending.get('key') == token:
        result = pending['result']
    else:
        result = controller.task(stage, {**context, **memory, 'discussion_kind': kind,
            'problem_model': checkpoint['current'], 'current_user_message': message,
            'source_work_done': False}, checked, publish=False)
        store.set('pending_discussion', {'key': token, 'result': result})
    working = apply_discussion(controller, checkpoint, result, context)
    if result['research_requests']:
        from .discussion_sources import research_requests
        from .source_understanding import understanding_context, reading_result_view
        effective_intent = (result.get('updated_intent') or [context.get('research_intent')])[0]
        reading_options = {'reading_context': {'research_intent': effective_intent,
                           'user_goal': effective_intent['goal']}} if result.get('updated_intent') else {}
        try:
            work = research_requests(controller, result['research_requests'], key=['discussion', message['id']], **reading_options)
        finally:
            # Only this operation's own source acquisition changes the saved
            # fingerprint; external scope changes still invalidate the pause.
            saved = deepcopy(store.get('problem_checkpoint'))
            saved['source_key'] = source_key(controller)
            store.set('problem_checkpoint', saved)
        context = controller.ideation_context()
        view = understanding_context(controller, intent_key=digest(effective_intent))
        context['source_understandings'] = view['readings']
        context['source_understanding_coverage'] = view['coverage']
        working_checkpoint = {**checkpoint, 'current': working}
        def checked_followup(value):
            revised_intent(controller, value, message)
            apply_discussion(controller, working_checkpoint, value, context)
            revised_reasoning(store, value.get('reasoning_updates', []), message, checkpoint)
            if value['research_requests']:
                raise ValueError("Use this turn's reading results; further questions belong to the next discussion turn")
            revised_memory(store, value['memory_updates'], supplied)
        followup = controller.task(stage, {**context, **memory, 'discussion_kind': kind,
            'problem_model': working, 'current_user_message': message, 'source_work_done': True,
            'reading_result': reading_result_view(work), 'previous_discussion': result,
            'research_intent': effective_intent,
            'saved_research_intent': store.get('research_intent'),
            'memory_instruction': 'Return the final complete memory_updates and reasoning_updates for this turn against active_memory and reasoning_notes. Replace the preliminary suggestions; do not concatenate them. research_intent is provisional for this reading, not yet saved. Return updated_intent as the final complete revision against saved_research_intent; [] means keep the saved intent.'}, checked_followup, publish=False)
        working = apply_discussion(controller, working_checkpoint, followup, context)
        result = followup
    intent_changes = revised_intent(controller, result, message)
    current_intent = deepcopy(intent_changes.get('research_intent', store.get('research_intent')))
    if kind == 'problem':
        if intent_changes:
            working['formulation'] = []
        working['research_intent'] = current_intent
    checkpoint.update(research_intent=current_intent, current=working, revision=checkpoint['revision'] + 1,
                      source_key=source_key(controller), state='discussing')
    checkpoint['revisions'].append({'revision': checkpoint['revision'], 'source_message_id': message['id'],
                                    'answer': result['answer'], 'current': deepcopy(working), 'time': now()})
    state = {**intent_changes, 'problem_checkpoint': checkpoint, 'pending_discussion': None,
             'reasoning_notes': revised_reasoning(store, result.get('reasoning_updates', []), message, checkpoint),
             'status': WAITING_BY_KIND[kind]}
    state['problem_exploration' if kind == 'direction' else 'problem_model'] = working
    finish_turn(store, result, supplied, model=controller.config['model'],
                reasoning_effort=controller.config['reasoning_effort'], **state)
    from .citations import Citations
    return Citations.from_store(store).text(result['answer'], compact=True)
